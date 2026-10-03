from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session

from ticketyn.api.crud import get_or_404
from ticketyn.api.ticket_data import RELATED_MODELS, ticket_statement, ticket_rows
from ticketyn.models import Circuit, Customer, IncidentType, Sector, Ticket, Node, Responsible
from ticketyn.schemas.report import ReportFilters, ReportSummary


def report_tickets(session: Session, filters: ReportFilters):
    """Iterador completo, sin limit/offset ni materialización de tickets duplicados."""
    return ticket_rows(session, filters.ticket_filters())


def granularity(filters):
    if filters.granularity != 'auto':
        return filters.granularity
    days = (filters.to_at - filters.from_at).total_seconds() / 86400
    return 'hour' if days <= 1.1 else 'day' if days <= 120 else 'week' if days <= 840 else 'month'


def trend(session, started, filters, grain, time_field="start_at"):
    timestamp = getattr(started.c, time_field)
    zone = ZoneInfo(filters.timezone)
    # Horas reales desde el límite: no colapsar la hora repetida al terminar DST.
    if grain == 'hour':
        expression = func.date_bin(literal(timedelta(hours=1)), timestamp, filters.from_at)
        current = filters.from_at.astimezone(timezone.utc)
    else:
        expression = func.date_trunc(grain, func.timezone(filters.timezone, timestamp))
        current = filters.from_at.astimezone(zone).replace(hour=0, minute=0, second=0, microsecond=0)
        if grain == 'week':
            current -= timedelta(days=current.weekday())
        elif grain == 'month':
            current = current.replace(day=1)
    counts = dict(session.execute(select(expression, func.count()).select_from(started).group_by(expression)).all())
    buckets = []
    while current < filters.to_at:
        key = current if grain == 'hour' else current.replace(tzinfo=None)
        buckets.append({'start_at': current.astimezone(zone), 'count': counts.get(key, 0)})
        if grain == 'hour':
            current += timedelta(hours=1)
        elif grain == 'month':
            current = current.replace(year=current.year + (current.month == 12), month=current.month % 12 + 1)
        else:
            current += timedelta(days=7 if grain == 'week' else 1)
    return buckets


def report_summary(session: Session, filters: ReportFilters) -> ReportSummary:
    selected_sector = get_or_404(session, Sector, filters.sector_id) if filters.sector_id else None
    selected_node = get_or_404(session, Node, filters.node_id) if filters.node_id else None
    selected_responsible = get_or_404(session, Responsible, filters.responsible_id) if filters.responsible_id else None
    started = ticket_statement(filters.ticket_filters()).order_by(None).subquery()
    closed = ticket_statement({**filters.ticket_filters(), 'status': 'CLOSED'}, time_field='end_at').order_by(None).subquery()
    duration = func.extract('epoch', closed.c.end_at - closed.c.start_at)
    closed_stats = session.execute(select(func.count(), func.avg(duration), func.coalesce(func.sum(duration), 0)).select_from(closed)).one()
    started_count = session.scalar(select(func.count()).select_from(started))
    rankings = {}
    for key, field, model in [('sectors', 'sector_id', Sector), ('customers', 'customer_id', Customer), ('circuits', 'circuit_id', Circuit), ('incident_types', 'incident_type_id', IncidentType), ('nodes', 'node_id', Node), ('responsibles', 'responsible_id', Responsible)]:
        if (key == 'sectors' and selected_sector) or (key == 'nodes' and selected_node) or (key == 'responsibles' and selected_responsible):
            rankings[key] = []
            continue
        label = (model.customer_code + ' — ' + model.name) if model is Customer else model.circuit_code if model is Circuit else model.name
        count = func.count().label('count')
        statement = select(model.id, label.label('label'), count).select_from(started)
        if model is Node:
            statement = statement.join(Circuit, started.c.circuit_id == Circuit.id).join(Node, Circuit.node_id == Node.id)
        else:
            statement = statement.join(model, getattr(started.c, field) == model.id)
        groups = [model.id, label]
        if model is Circuit:
            statement = statement.join(Customer, model.customer_id == Customer.id).add_columns(Customer.id.label('customer_id'), Customer.customer_code, Customer.name.label('customer_name'))
            groups.extend([Customer.id, Customer.customer_code, Customer.name])
        rankings[key] = [dict(row._mapping) for row in session.execute(statement.group_by(*groups).order_by(count.desc(), model.id))]
    grain = granularity(filters)
    started_trend = trend(session, started, filters, grain)
    closed_trend = trend(session, closed, filters, grain, 'end_at')
    activity = [{'start_at': a['start_at'], 'started': a['count'], 'closed': b['count']} for a, b in zip(started_trend, closed_trend)]
    distributions = {}
    for key, part, labels in [
        ('hours', 'hour', [f'{hour:02}:00' for hour in range(24)]),
        ('weekdays', 'isodow', ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']),
    ]:
        expression = func.extract(part, func.timezone(filters.timezone, started.c.start_at))
        counts = dict(session.execute(select(expression, func.count()).select_from(started).group_by(expression)).all())
        distributions[key] = [{'id': i, 'label': label, 'count': counts.get(i + (part == 'isodow'), 0)} for i, label in enumerate(labels)]
    average = func.avg(duration)
    sector_durations = [dict(row._mapping) for row in session.execute(
        select(Sector.id, Sector.name.label('label'), func.count().label('count'), average.label('average_duration_seconds'))
        .select_from(closed).join(Sector, closed.c.sector_id == Sector.id)
        .group_by(Sector.id, Sector.name).order_by(average.desc(), Sector.id))]
    return ReportSummary(
        period={'from_at': filters.from_at, 'to_exclusive': filters.to_at, 'timezone': filters.timezone, 'granularity': grain},
        generated_at=datetime.now(timezone.utc),
        sector={'id': selected_sector.id, 'name': selected_sector.name} if selected_sector else None,
        kpis={'started': started_count, 'closed': closed_stats[0], 'average_duration_seconds': closed_stats[1], 'total_duration_seconds': closed_stats[2]},
        trend=started_trend, activity=activity, sector_durations=sector_durations, **distributions, **rankings,
        node={"id": selected_node.id, "name": selected_node.name} if selected_node else None,
        responsible={"id": selected_responsible.id, "name": selected_responsible.name} if selected_responsible else None,
    )
