"""Análisis FMS exclusivamente de consulta: fecha efectiva y asignaciones históricas."""
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Query
from sqlalchemy import case, func, select

from ticketyn.api.crud import DBSession, get_or_404
from ticketyn.api.fms_data import operation_query
from ticketyn.api.report_data import trend
from ticketyn.api.reports import read_snapshot
from ticketyn.models import Circuit, Customer, Sector, Node, Responsible
from ticketyn.models.fms import Activation, CapacityChange, CircuitLifecycleOperation, DeactivationReason
from ticketyn.schemas.fms import ActivationResponse, CapacityChangeResponse, LifecycleResponse
from ticketyn.schemas.fms_report import FmsReportFilters, FmsReportDetailFilters, FmsReportSummary

router = APIRouter(prefix='/api/fms/reports', tags=['fms-reports'])
Kind = Literal['activations', 'capacity-changes', 'circuit-lifecycle']
MODELS = {'activations': Activation, 'capacity-changes': CapacityChange, 'circuit-lifecycle': CircuitLifecycleOperation}


def report_query(model, filters):
    statement = operation_query(model, from_at=filters.from_at, to_at=filters.to_at)
    for field in ('sector_id', 'node_id', 'responsible_id'):
        value = getattr(filters, field)
        if value is not None: statement = statement.where(getattr(model, field) == value)
    return statement


def selections(session, filters):
    return {field: get_or_404(session, model, getattr(filters, field + '_id')) if getattr(filters, field + '_id') is not None else None for field, model in [('sector',Sector),('node',Node),('responsible',Responsible)]}


def temporal_context(session, base, filters):
    begin, end = filters.from_at, filters.to_at
    if begin is None:
        oldest, newest = session.execute(select(func.min(base.c.effective_at), func.max(base.c.effective_at))).one()
        if oldest is None: return None, None, 'day'
        zone = ZoneInfo(filters.timezone)
        begin = oldest.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)
        end = newest.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    grain = filters.granularity if filters.granularity != 'auto' else 'day' if (end - begin).total_seconds() <= 120 * 86400 else 'month'
    return begin, end, grain


def summary_data(session, kind, filters):
    selected = selections(session, filters)
    model = MODELS[kind]
    base = report_query(model, filters).order_by(None).subquery()
    customers, reasons = [], []
    if model is Activation:
        statement = select(func.count(), func.count(func.distinct(Circuit.customer_id)), func.count(func.distinct(base.c.circuit_id))).select_from(base).join(Circuit, Circuit.id == base.c.circuit_id)
        total, clients, circuits = session.execute(statement).one()
        kpis = dict(total=total, distinct_customers=clients, distinct_circuits=circuits)
        if not any(selected.values()):
            count = func.count(func.distinct(base.c.circuit_id)).label('count')
            customers = [dict(row._mapping) for row in session.execute(select(Customer.id, (Customer.customer_code + ' — ' + Customer.name).label('label'), count).select_from(base).join(Circuit, Circuit.id == base.c.circuit_id).join(Customer, Customer.id == Circuit.customer_id).group_by(Customer.id).order_by(count.desc(),Customer.id).limit(10))]
    else:
        first = base.c.operation_type == ('INCREASE' if model is CapacityChange else 'DEACTIVATE')
        second = base.c.operation_type == ('DECREASE' if model is CapacityChange else 'REACTIVATE')
        if model is CapacityChange:
            old = base.c.previous_capacity * case((base.c.previous_unit == 'Gbps',1000),else_=1)
            new = base.c.new_capacity * case((base.c.new_unit == 'Gbps',1000),else_=1)
            delta = new - old
            row = session.execute(select(func.count().filter(first), func.count().filter(second), func.coalesce(func.sum(delta).filter(first),0), func.coalesce(func.sum(-delta).filter(second),0), func.count().filter(base.c.previous_capacity.is_(None))).select_from(base)).one()
            kpis = dict(increases=row[0],decreases=row[1],known_added_mbps=row[2],known_reduced_mbps=row[3],known_net_mbps=row[2]-row[3],unknown_variations=row[4])
        else:
            row = session.execute(select(func.count().filter(first),func.count().filter(second),func.count(func.distinct(base.c.circuit_id)).filter(first),func.count(func.distinct(base.c.circuit_id)).filter(second)).select_from(base)).one()
            kpis = dict(deactivations=row[0],reactivations=row[1],distinct_deactivated_circuits=row[2],distinct_reactivated_circuits=row[3])
            count = func.count().label('count')
            reasons = [dict(row._mapping) for row in session.execute(select(func.coalesce(DeactivationReason.id,0).label('id'),func.coalesce(DeactivationReason.name,'Sin motivo registrado').label('label'),count).select_from(base).outerjoin(DeactivationReason,DeactivationReason.id == base.c.reason_id).where(first).group_by(DeactivationReason.id,DeactivationReason.name).order_by(count.desc(),DeactivationReason.id))]
    begin, end, grain = temporal_context(session,base,filters)
    buckets = []
    if begin is not None:
        options = filters.model_copy(update={'from_at':begin,'to_at':end})
        if model is Activation:
            buckets = [{**bucket,'first':bucket['count'],'second':0} for bucket in trend(session,base,options,grain,time_field='effective_at')]
        else:
            a = trend(session,select(base).where(first).subquery(),options,grain,time_field='effective_at')
            b = trend(session,select(base).where(second).subquery(),options,grain,time_field='effective_at')
            buckets = [dict(start_at=x['start_at'],count=x['count']+y['count'],first=x['count'],second=y['count']) for x,y in zip(a,b)]
    return dict(generated_at=datetime.now(timezone.utc),period={'from_at':filters.from_at,'to_exclusive':filters.to_at,'timezone':filters.timezone,'granularity':grain},**selected,kpis=kpis,trend=buckets,customers=customers,reasons=reasons)


@router.get('/{kind}/summary', response_model=FmsReportSummary)
def summary(kind: Kind, session: DBSession, filters: Annotated[FmsReportFilters,Query()]):
    read_snapshot(session)
    return summary_data(session,kind,filters)


@router.get('/{kind}/details', response_model=list[ActivationResponse | CapacityChangeResponse | LifecycleResponse])
def details(kind: Kind, session: DBSession, filters: Annotated[FmsReportDetailFilters,Query()]):
    selections(session,filters)
    return list(session.scalars(report_query(MODELS[kind],filters).limit(filters.limit).offset(filters.offset)))


@router.get('/{kind}/export/pdf')
def export_pdf(kind: Kind, session: DBSession, filters: Annotated[FmsReportFilters, Query()]):
    from ticketyn.api.fms_report_exports import report_pdf_response
    return report_pdf_response(session, kind, filters)
