from datetime import timedelta
from zoneinfo import ZoneInfo
from typing import Annotated
from fastapi import APIRouter, Query
from sqlalchemy import func, select
from ticketyn.api.crud import DBSession, get_or_404
from ticketyn.api.ticket_data import ticket_statement
from ticketyn.api.report_data import trend, granularity
from ticketyn.models import Ticket, TicketEscalation, Responsible, Sector, Node, Department, EscalationReason
from ticketyn.schemas.escalation_stats import EscalationFilters, EscalationSummary, EscalationTicketFilters
from ticketyn.schemas.report import ReportFilters

router = APIRouter(prefix='/api/escalations', tags=['escalation-statistics'])


def scope(session, filters):
    for id, model in [(filters.recipient_id, Responsible), (filters.responsible_id, Responsible), (filters.sector_id, Sector), (filters.node_id, Node), (filters.department_id, Department), (filters.reason_id, EscalationReason)]:
        if id is not None:
            get_or_404(session, model, id)
    context = ticket_statement({key: getattr(filters, key) for key in ('sector_id', 'node_id', 'responsible_id')}).order_by(None).subquery()
    events = select(TicketEscalation).where(TicketEscalation.ticket_id.in_(select(context.c.id)))
    if filters.from_at is not None:
        events = events.where(TicketEscalation.started_at >= filters.from_at, TicketEscalation.started_at < filters.to_at)
    if filters.recipient_id is not None:
        events = events.where(TicketEscalation.recipient_id == filters.recipient_id)
    for field in ('department_id', 'reason_id', 'status'):
        value = getattr(filters, field, None)
        if value is not None:
            events = events.where(getattr(TicketEscalation, field) == value)
    tickets = select(context)
    if filters.from_at is not None:
        tickets = tickets.where(context.c.start_at >= filters.from_at, context.c.start_at < filters.to_at)
    return tickets.subquery(), events.order_by(None).subquery()


def escalation_summary(session, filters):
    tickets, events = scope(session, filters)
    counts = session.execute(select(func.count(), func.count(func.distinct(events.c.ticket_id)),
        func.count().filter(events.c.status == 'ACTIVE'), func.count().filter(events.c.status == 'FINISHED'),
        func.avg(func.extract('epoch', events.c.finished_at - events.c.started_at)).filter(events.c.status == 'FINISHED'),
        func.min(events.c.started_at), func.max(events.c.started_at)).select_from(events)).one()
    denominator, coverage = session.execute(select(func.count(),
        func.count().filter(tickets.c.id.in_(select(events.c.ticket_id)))).select_from(tickets)).one()
    count = func.count().label('count')
    recipients = [dict(row._mapping) for row in session.execute(select(Responsible.id, func.coalesce(Responsible.name, 'Sin responsable asignado').label('label'), count)
        .select_from(events).outerjoin(Responsible, events.c.recipient_id == Responsible.id)
        .group_by(Responsible.id, Responsible.name).order_by(count.desc(), Responsible.id))]
    department_label = func.coalesce(Department.name, events.c.recipient_department_name, 'Departamento histórico desconocido')
    departments = [dict(row._mapping) for row in session.execute(select(Department.id,
        department_label.label('label'), count)
        .select_from(events).outerjoin(Department, events.c.department_id == Department.id)
        .group_by(Department.id, department_label).order_by(count.desc(), Department.id))]
    grain = 'day'
    if filters.from_at is not None:
        period = ReportFilters.model_validate({'from': filters.from_at, 'to': filters.to_at, 'timezone': filters.timezone, 'granularity': filters.granularity})
        grain = granularity(period)
        buckets = trend(session, events, period, grain, 'started_at')
    elif counts[5] is not None:
        # Bounds derived from SQL, not a second event filter. Reuse the existing
        # timezone-aware buckets/automatic granularity, including empty buckets.
        zone = ZoneInfo(filters.timezone)
        begin = counts[5].astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)
        end = counts[6].astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        # Trusted database bounds: Todos is not subject to the ten-year limit
        # for explicitly supplied report periods. No event rows are loaded.
        period = ReportFilters.model_construct(from_at=begin, to_at=end, timezone=filters.timezone, granularity='auto')
        grain = granularity(period)
        buckets = trend(session, events, period, grain, 'started_at')
    else:
        buckets = []
    return EscalationSummary(total_tickets=denominator, escalated_tickets=coverage, events=counts[0], active=counts[2], finished=counts[3],
        average_duration_seconds=counts[4], escalated_percentage=100 * coverage / denominator if denominator else 0,
        granularity=grain, trend=buckets, recipients=recipients, departments=departments, event_tickets=counts[1])


@router.get('/summary', response_model=EscalationSummary)
def summary(session: DBSession, filters: Annotated[EscalationFilters, Query()]):
    from ticketyn.api.reports import read_snapshot
    read_snapshot(session)
    return escalation_summary(session, filters)


@router.get('/tickets')
def related_tickets(session: DBSession, filters: Annotated[EscalationTicketFilters, Query()]):
    from ticketyn.api.reports import read_snapshot
    read_snapshot(session)
    _, events = scope(session, filters)
    return [dict(row._mapping) for row in session.execute(select(Ticket.id, Ticket.reference, Ticket.title, Ticket.status)
        .where(Ticket.id.in_(select(events.c.ticket_id))).order_by(Ticket.id.desc()).limit(filters.limit).offset(filters.offset))]
