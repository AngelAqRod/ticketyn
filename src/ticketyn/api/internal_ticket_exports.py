"""List exports use the internal-ticket predicate and the existing Tickets documents."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import Spacer
from sqlalchemy import func, select
from ticketyn.api import internal_ticket_data as data
from ticketyn.api.documents import (
    AMBER, EMERALD, PURPLE, build_pdf, duration_text, fonts,
    modern_table, modular_metric_strip, paragraph, report_identification,
)
from ticketyn.api.ticket_exports import write_export_xlsx
from ticketyn.api.ticket_pdf_limits import validate_pdf_volume
from ticketyn.models import InternalTicket, Ticket

HEADERS = ['Correlativo', 'Incidencia', 'Estado', 'Sector', 'Nodo', 'Departamento',
           'Responsable', 'Tipo de incidencia interna', 'Atribuible a proveedor',
           'Fecha y hora de inicio', 'Duración', 'Cantidad de tickets de clientes relacionados']
RELATION_LABELS = {'sector_id': 'Sector', 'node_id': 'Nodo', 'department_id': 'Departamento',
                   'responsible_id': 'Responsable', 'incident_type_id': 'Tipo de incidencia interna',
                   'provider_id': 'Atribuible a proveedor'}


def friendly_filters(session, filters):
    values = []
    if filters.search: values.append(f'Búsqueda: {filters.search}')
    if filters.status: values.append(f'Estado: {"Abierto" if filters.status == "OPEN" else "Cerrado"}')
    for field, model in data.RELATIONS.items():
        id = getattr(filters, field)
        if id is not None:
            item = session.get(model, id)
            values.append(f'{RELATION_LABELS[field]}: {item.name if item else "No disponible"}')
    if filters.without_provider: values.append('Atribuible a proveedor: Ninguno')
    zone = ZoneInfo(filters.timezone)
    if filters.from_at: values.append(f'Desde (incluido): {filters.from_at.astimezone(zone):%d/%m/%Y %H:%M}')
    if filters.to_at: values.append(f'Hasta (excluido): {filters.to_at.astimezone(zone):%d/%m/%Y %H:%M}')
    return values or ['Todos los tickets internos']


def export_rows(session, filters, *, excel=False):
    # Every catalog is already joined by the ORM query. Count via indexed FK in
    # the same SQL; no intervention/escalation join can multiply ticket rows.
    count = select(func.count(Ticket.id)).where(Ticket.internal_ticket_id == InternalTicket.id).correlate(InternalTicket).scalar_subquery()
    statement = data.statement(filters.model_dump()).add_columns(count).execution_options(yield_per=200)
    zone = ZoneInfo(filters.timezone)
    for ticket, related in session.execute(statement):
        start = ticket.start_at.astimezone(zone)
        yield [ticket.reference, ticket.title, 'Abierto' if ticket.status == 'OPEN' else 'Cerrado',
               ticket.sector.name, ticket.node.name if ticket.node else ('—' if not excel else None),
               ticket.department.name, ticket.responsible.name if ticket.responsible else 'Sin asignar',
               ticket.incident_type.name, ticket.provider.name if ticket.provider else 'Ninguno',
               start.isoformat() if excel else start.strftime('%d/%m/%Y\n%H:%M'),
               duration_text(ticket.duration_seconds) if ticket.duration_seconds is not None else ('En curso' if ticket.status == 'OPEN' else 'Sin fecha de fin'), related]


def export_pdf(session, filters, output):
    validate_pdf_volume(session, filters, internal=True)
    fonts()
    zone = ZoneInfo(filters.timezone)
    stmt = data.statement(filters.model_dump()).order_by(None).subquery()
    counts = session.execute(
        select(
            func.count().label('total'),
            func.count().filter(stmt.c.status == 'OPEN').label('open_count'),
            func.count().filter(stmt.c.status == 'CLOSED').label('closed_count'),
        ).select_from(stmt)
    ).one()
    total = counts.total or 0
    open_count = counts.open_count or 0
    closed_count = counts.closed_count or 0

    related_total = session.scalar(
        select(func.count(Ticket.id)).select_from(Ticket).join(stmt, Ticket.internal_ticket_id == stmt.c.id)
    ) or 0

    generated = datetime.now(timezone.utc).astimezone(zone)
    from_str = filters.from_at.astimezone(zone).strftime('%d/%m/%Y %H:%M') if filters.from_at else None
    to_str = filters.to_at.astimezone(zone).strftime('%d/%m/%Y %H:%M') if filters.to_at else None
    if from_str and to_str:
        period_str = f'{from_str} — {to_str}'
    elif from_str:
        period_str = f'Desde (incluido): {from_str}'
    elif to_str:
        period_str = f'Hasta (excluido): {to_str}'
    else:
        period_str = 'Sin límite temporal'

    filter_tokens = friendly_filters(session, filters)
    filters_str = ' · '.join(filter_tokens)
    width = landscape(A4)[0] - 60

    metrics = [
        ('TOTAL TICKETS INTERNOS', total, PURPLE),
        ('ABIERTOS / EN CURSO', open_count, AMBER),
        ('CERRADOS', closed_count, EMERALD),
        ('TICKETS CLIENTES VINCULADOS', related_total, PURPLE),
    ]

    fractions = [.10, .13, .06, .07, .07, .07, .09, .09, .09, .085, .065, .08]
    pdf_headers = [*HEADERS[:5], 'Depto.', HEADERS[6], 'Tipo interno',
                   'Proveedor atribuible', 'Inicio', HEADERS[10], 'Tickets de clientes']

    table = modern_table(
        pdf_headers,
        export_rows(session, filters),
        [width * fraction for fraction in fractions],
        reference=True,
        light=True,
        accent=PURPLE,
    )

    story = [
        report_identification(
            'Tickets internos',
            period=period_str,
            filters=filters_str,
            total=total,
            accent=PURPLE,
            category='Gestión de Incidencias · NOC Interno',
            width=width,
        ),
        modular_metric_strip(metrics, width, accent=PURPLE),
        table,
    ]
    build_pdf(output, 'Tickets internos', filters.timezone, story,
              issued_at=generated.strftime('%d/%m/%Y %H:%M'),
              subtitle='GESTIÓN DE INCIDENCIAS · NOC INTERNO',
              modular=True, landscape_mode=True, reference='Tickets internos', accent=PURPLE)


def export_xlsx(session, filters, output):
    generated = datetime.now(timezone.utc).astimezone(ZoneInfo(filters.timezone))
    write_export_xlsx(output, 'Tickets internos', HEADERS,
                      [24, 50, 14, 26, 26, 26, 28, 32, 30, 34, 22, 24],
                      export_rows(session, filters, excel=True),
                      metadata=['Tickets internos', f'Generado: {generated.isoformat()}',
                                f'Zona horaria: {filters.timezone}', *friendly_filters(session, filters)])
