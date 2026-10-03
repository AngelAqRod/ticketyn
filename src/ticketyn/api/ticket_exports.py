from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import Spacer
from sqlalchemy import func, select

from ticketyn.models import Node, Responsible
from ticketyn.api.documents import build_pdf, duration_text, fonts, paragraph, section, ticket_pdf_table
from ticketyn.api.ticket_data import RELATED_MODELS, ticket_rows, ticket_statement


def friendly_filters(session, filters):
    values = []
    if filters.status:
        values.append(f"Estado: {'Abierto' if filters.status == 'OPEN' else 'Cerrado'}")
    if filters.search:
        values.append(f'Búsqueda: {filters.search}')
    labels = ['Cliente', 'Circuito', 'Sector', 'Departamento', 'Tipo de incidencia']
    for (field, model), label in zip(RELATED_MODELS.items(), labels):
        id = getattr(filters, field)
        if id is None: continue
        item = session.get(model, id)
        if item is None:
            value = 'No disponible'
        elif field == 'customer_id':
            value = f'{item.customer_code} — {item.name}'
        elif field == 'circuit_id':
            value = f'{item.circuit_code} — {item.description}'
        else:
            value = item.name
        values.append(f'{label}: {value}')
    for field, model, label in [("node_id", Node, "Nodo"), ("responsible_id", Responsible, "Responsable")]:
        if getattr(filters, field):
            item = session.get(model, getattr(filters, field))
            values.append(f"{label}: {item.name if item else 'No disponible'}")
    zone = ZoneInfo(filters.timezone)
    if filters.from_at:
        values.append(f'Desde (incluido): {filters.from_at.astimezone(zone):%d/%m/%Y %H:%M}')
    if filters.to_at:
        # Mostrar el límite real evita perder precisión en filtros API intradía.
        values.append(f'Hasta (excluido): {filters.to_at.astimezone(zone):%d/%m/%Y %H:%M}')
    return values or ['Todos los tickets']


def export_ticket_pdf(session, filters, output):
    fonts()
    zone = ZoneInfo(filters.timezone)
    values = filters.model_dump()
    total = session.scalar(select(func.count()).select_from(ticket_statement(values).order_by(None).subquery()))
    generated = datetime.now(timezone.utc).astimezone(zone)
    story = [paragraph('Listado de tickets', size=21, bold=True),
        paragraph(f'Generado: {generated:%d/%m/%Y %H:%M} · Total encontrado: {total}', size=9),
        paragraph(' · '.join(friendly_filters(session, filters)), size=8), Spacer(1, 10),
        section('Tickets', 1, keep=False), ticket_pdf_table(ticket_rows(session, values), zone, landscape(A4)[0] - 60)]
    build_pdf(output, 'Listado de tickets', filters.timezone, story)


def export_ticket_xlsx(session, filters, output):
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet('Tickets')
    sheet.freeze_panes = 'A2'
    headers = ['Referencia', 'Estado', 'Cliente', 'Código cliente', 'Circuito', 'Código circuito',
        'Sector', 'Departamento', 'Tipo de incidencia', 'Título', 'Descripción', 'Inicio', 'Fin',
        'Duración', 'Duración (segundos)', 'Nodo', 'Responsable']
    widths = [22, 14, 32, 24, 38, 28, 26, 26, 28, 45, 65, 34, 34, 22, 22, 28, 28]
    for index, width in enumerate(widths, 1): sheet.column_dimensions[get_column_letter(index)].width = width
    cells = []
    for title in headers:
        cell = WriteOnlyCell(sheet, value=title)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='102744')
        cells.append(cell)
    sheet.append(cells)
    zone = ZoneInfo(filters.timezone)
    count = 1
    for ticket, customer, circuit, sector, department, kind in ticket_rows(session, filters.model_dump()):
        # ISO incluye offset: conserva incluso las horas repetidas al cambiar DST.
        date = lambda value: value.astimezone(zone).isoformat() if value else None
        values = [ticket.reference, 'Abierto' if ticket.status == 'OPEN' else 'Cerrado', customer.name,
            customer.customer_code, circuit.description, circuit.circuit_code, sector.name, department.name,
            kind.name, ticket.title, ticket.description, date(ticket.start_at), date(ticket.end_at),
            'En curso' if ticket.duration_seconds is None else duration_text(ticket.duration_seconds), ticket.duration_seconds, circuit.node.name if circuit.node else None, ticket.responsible.name if ticket.responsible else None]
        cells = []
        for value in values:
            cell = WriteOnlyCell(sheet, value=value)
            if isinstance(value, str): cell.data_type = 's'  # Nunca ejecutar texto de usuario como fórmula.
            cell.alignment = Alignment(vertical='top', wrap_text=True)
            cells.append(cell)
        sheet.append(cells)
        count += 1
    sheet.auto_filter.ref = f'A1:Q{count}'
    workbook.save(output)
