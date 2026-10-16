"""List exports use the internal-ticket predicate and the existing Tickets documents."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import Spacer
from sqlalchemy import func, select
from ticketyn.api import internal_ticket_data as data
from ticketyn.api.documents import build_pdf, duration_text, fonts, modern_table, paragraph, section
from ticketyn.api.ticket_exports import write_export_xlsx
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
               duration_text(ticket.duration_seconds) if ticket.duration_seconds is not None else 'En curso', related]


def export_pdf(session, filters, output):
    fonts()
    total = session.scalar(select(func.count()).select_from(data.statement(filters.model_dump()).order_by(None).subquery()))
    generated = datetime.now(timezone.utc).astimezone(ZoneInfo(filters.timezone))
    width = landscape(A4)[0] - 60
    fractions = [.10, .13, .06, .07, .07, .07, .09, .09, .09, .085, .065, .08]
    pdf_headers = [*HEADERS[:5], 'Depto.', HEADERS[6], 'Tipo interno',
                   'Proveedor atribuible', 'Inicio', HEADERS[10], 'Tickets de clientes']
    story = [paragraph('Tickets internos', size=21, bold=True),
             paragraph(f'Generado: {generated:%d/%m/%Y %H:%M} · Total encontrado: {total}', size=9),
             paragraph(' · '.join(friendly_filters(session, filters)), size=8), Spacer(1, 10),
             section('Tickets internos', 1, keep=False),
             modern_table(pdf_headers, export_rows(session, filters), [width * fraction for fraction in fractions], reference=True)]
    build_pdf(output, 'Tickets internos', filters.timezone, story)


def export_xlsx(session, filters, output):
    generated = datetime.now(timezone.utc).astimezone(ZoneInfo(filters.timezone))
    write_export_xlsx(output, 'Tickets internos', HEADERS,
                      [24, 50, 14, 26, 26, 26, 28, 32, 30, 34, 22, 24],
                      export_rows(session, filters, excel=True),
                      metadata=['Tickets internos', f'Generado: {generated.isoformat()}',
                                f'Zona horaria: {filters.timezone}', *friendly_filters(session, filters)])
