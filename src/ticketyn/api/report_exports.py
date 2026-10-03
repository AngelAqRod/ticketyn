"""PDF de lectura y XLSX de análisis a partir del mismo motor de reportes."""
from datetime import datetime
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from ticketyn.api.documents import duration_text
from ticketyn.api.report_data import report_tickets


def metadata(summary):
    zone = ZoneInfo(summary.period.timezone)
    return [
        ['Ticketyn', report_title(summary)],
        ['Sector', summary.sector['name'] if summary.sector else 'Todos'],
        ['Nodo', summary.node['name'] if summary.node else 'Todos'],
        ['Responsable', summary.responsible['name'] if summary.responsible else 'Todos'],
        ['Zona horaria', summary.period.timezone],
        ['Desde (incluido)', summary.period.from_at.astimezone(zone).isoformat()],
        ['Hasta (excluido)', summary.period.to_exclusive.astimezone(zone).isoformat()],
        ['Generado', summary.generated_at.astimezone(zone).isoformat()],
        ['Incidencias iniciadas', summary.kpis.started], ['Incidencias cerradas', summary.kpis.closed],
        ['Duración promedio (segundos)', summary.kpis.average_duration_seconds],
        ['Duración acumulada (segundos)', summary.kpis.total_duration_seconds],
        ['Universo detalle/rankings', 'Inicio en el período.'],
        ['Rankings Nodo/Responsable', 'Solo tickets con asignación; NULL continúa incluido en los KPI correspondientes.'],
        ['Universo cierres/duración', 'Estado CLOSED y Fin en el período, aunque Inicio sea anterior.'],
    ]


def export_xlsx(session, filters, summary, output):
    workbook = Workbook(write_only=True)
    zone = ZoneInfo(filters.timezone)

    def sheet(name, headers, rows, widths):
        page = workbook.create_sheet(name)
        page.freeze_panes = 'A2'
        for index, width in enumerate(widths, 1):
            page.column_dimensions[get_column_letter(index)].width = width
        header = []
        for value in headers:
            cell = WriteOnlyCell(page, value=value)
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='166534')
            header.append(cell)
        page.append(header)
        count = 1
        for row in rows:
            cells = []
            for value in row:
                cell = WriteOnlyCell(page, value=value)
                if isinstance(value, str):
                    # Los datos introducidos por el usuario nunca se convierten en fórmulas.
                    cell.data_type = 's'
                elif isinstance(value, datetime):
                    cell.number_format = 'yyyy-mm-dd hh:mm:ss'
                cells.append(cell)
            page.append(cells)
            count += 1
        page.auto_filter.ref = f'A1:{get_column_letter(len(headers))}{count}'
    sheet('Resumen', ['Concepto', 'Valor'], metadata(summary), [38, 95])
    def ticket_rows():
        for ticket, customer, circuit, sector, department, incident_type in report_tickets(session, filters):
            local = lambda value: value.astimezone(zone).replace(tzinfo=None) if value else None
            yield [ticket.reference, ticket.status, customer.customer_code, customer.name,
                   circuit.circuit_code, circuit.description, sector.name, department.name,
                   incident_type.name, ticket.title, ticket.description, local(ticket.start_at),
                   local(ticket.end_at), ticket.duration_seconds, ('En curso' if ticket.duration_seconds is None else duration_text(ticket.duration_seconds)),
                   ticket.start_at.astimezone(zone).isoformat(), ticket.end_at.astimezone(zone).isoformat() if ticket.end_at else None, circuit.node.name if circuit.node else None, ticket.responsible.name if ticket.responsible else None]
    sheet('Tickets', ['Referencia', 'Estado', 'Cliente código', 'Cliente nombre', 'Circuito código',
                     'Circuito descripción', 'Sector', 'Departamento', 'Tipo de incidencia', 'Título',
                     'Descripción', 'Inicio', 'Fin', 'Duración (segundos)', 'Duración', 'Inicio ISO (con offset)', 'Fin ISO (con offset)', 'Nodo', 'Responsable'],
          ticket_rows(), [22, 12, 22, 30, 25, 35, 24, 24, 25, 40, 65, 23, 23, 23, 22, 32, 32, 28, 28])
    sheet('Evolución', ['Inicio del bucket (local)', 'Incidencias', 'Inicio ISO (con offset)'],
          ([bucket.start_at.astimezone(zone).replace(tzinfo=None), bucket.count, bucket.start_at.isoformat()] for bucket in summary.trend), [28, 20, 32])
    for key, title in [('sectors', 'Sectores'), ('customers', 'Clientes'), ('circuits', 'Circuitos'), ('incident_types', 'Tipos'), ('nodes', 'Nodos'), ('responsibles', 'Responsables')]:
        if (key == 'sectors' and summary.sector) or (key == 'nodes' and summary.node) or (key == 'responsibles' and summary.responsible):
            continue
        rows = getattr(summary, key)
        sheet(title, ['ID', 'Nombre / código', 'Incidencias', 'Cliente código', 'Cliente nombre'],
              ([row.id, row.label, row.count, row.customer_code, row.customer_name] for row in rows), [12, 65, 20, 25, 35])
    sheet('Iniciadas y cerradas', ['Bucket ISO', 'Iniciadas', 'Cerradas'], ([row.start_at.isoformat(), row.started, row.closed] for row in summary.activity), [32, 18, 18])
    for key, name in [('hours', 'Horas'), ('weekdays', 'Días')]:
        sheet(name, ['Período', 'Incidencias'], ([row.label, row.count] for row in getattr(summary, key)), [25, 18])
    sheet('Duración por sector', ['Sector', 'Cierres', 'Promedio (segundos)'], ([row.label, row.count, row.average_duration_seconds] for row in summary.sector_durations), [35, 18, 28])
    workbook.save(output)


def export_pdf(session, filters, summary, output):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import KeepTogether, PageBreak, Spacer
    from ticketyn.api.documents import (build_pdf, fonts, paragraph, section, metric_strip,
        modern_table, ticket_pdf_table, TrendGraphic, BarsGraphic, ActivityGraphic, analytical_block)
    fonts()
    zone = ZoneInfo(filters.timezone)
    width = landscape(A4)[0] - 60
    title = report_title(summary)
    context = ' · '.join(f'{label}: {value["name"]}' for label, value in [('Nodo', summary.node), ('Responsable', summary.responsible)] if value)
    story = [paragraph(title, size=21, bold=True),
        paragraph(f"Período: {summary.period.from_at.astimezone(zone):%d/%m/%Y %H:%M} — {summary.period.to_exclusive.astimezone(zone):%d/%m/%Y %H:%M} (fin exclusivo)", size=9),
        paragraph(f"Sector: {summary.sector['name'] if summary.sector else 'Todos los sectores'} · Generado: {summary.generated_at.astimezone(zone):%d/%m/%Y %H:%M}", size=8),
        paragraph(context, size=8), Spacer(1, 8), section('Resumen', 1), metric_strip([
            ('INICIADAS', summary.kpis.started), ('CERRADAS', summary.kpis.closed),
            ('DURACIÓN PROMEDIO', duration_text(summary.kpis.average_duration_seconds)),
            ('DURACIÓN ACUMULADA', duration_text(summary.kpis.total_duration_seconds))], width), Spacer(1, 8),
        paragraph('Iniciadas, evolución, rankings y detalle: Inicio en el período. Cerradas y duraciones: estado Cerrado y Fin en el período, incluso si comenzaron antes. Cerrados sin Fin no aportan duración. Rankings de Nodo/Responsable: solo asignados.', size=7),
        KeepTogether([section('Evolución de incidencias', 2), TrendGraphic(summary.trend, zone, width, summary.period.granularity)]), Spacer(1, 8)]
    story.append(KeepTogether([section('Iniciadas vs cerradas', 3), ActivityGraphic(summary.activity, zone, width, summary.period.granularity)]))
    number = 4
    for key, name in [('sectors', 'Sectores'), ('customers', 'Clientes'), ('circuits', 'Circuitos'), ('incident_types', 'Tipos de incidencia'), ('nodes', 'Nodos'), ('responsibles', 'Responsables')]:
        if (key == 'sectors' and summary.sector) or (key == 'nodes' and summary.node) or (key == 'responsibles' and summary.responsible): continue
        ranking = getattr(summary, key)
        heading = section(f'{name} · ranking completo ({len(ranking)})', number)
        number += 1
        graphic = BarsGraphic(ranking, width) if ranking else None
        if key == 'circuits':
            rows = ([index, row.label, ' — '.join(part for part in [row.customer_code, row.customer_name] if part), row.count] for index, row in enumerate(ranking, 1))
            table = modern_table(['Posición', 'Circuito', 'Cliente', 'Incidencias'], rows, [55, width * .40, width - 55 - width * .40 - 85, 85])
        else:
            table = modern_table(['Posición', 'Nombre / código', 'Incidencias'],
                ([index, row.label, row.count] for index, row in enumerate(ranking, 1)), [55, width - 140, 85])
        story.extend(analytical_block(heading, graphic, table, width))
        story.append(Spacer(1, 12))
    for key, name in [('hours', 'Distribución por hora del día'), ('weekdays', 'Distribución por día de semana')]:
        values = getattr(summary, key)
        heading, graphic = section(name, number), BarsGraphic(values, width, limit=24)
        if key == 'hours':
            story.append(KeepTogether([heading, graphic]))
        else:
            table = modern_table(['Período', 'Incidencias'], ([row.label, row.count] for row in values), [width - 85, 85])
            story.extend(analytical_block(heading, graphic, table, width))
        number += 1
    if not summary.sector:
        story.extend(analytical_block(section('Duración promedio por sector', number),
            BarsGraphic(summary.sector_durations, width, value_field='average_duration_seconds'),
            modern_table(['Sector', 'Cierres', 'Duración promedio'],
                ([row.label, row.count, duration_text(row.average_duration_seconds)] for row in summary.sector_durations), [width - 210, 85, 125]), width))
        number += 1
    story.extend([PageBreak(), section('Detalle de tickets — todos los iniciados en el período', number, keep=False),
        ticket_pdf_table(report_tickets(session, filters), zone, width)])
    build_pdf(output, title, filters.timezone, story)


def report_title(summary):
    if summary.node: return "Reporte por Nodo"
    if summary.responsible: return "Reporte por Responsable"
    return "Reporte por Sector" if summary.sector else "Reporte General"
