"""PDF estadístico FMS; motor compartido, snapshot y detalle completo acotado."""
from tempfile import SpooledTemporaryFile
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import KeepTogether, Spacer
from sqlalchemy import func, select
from starlette.background import BackgroundTask

from ticketyn.api.documents import (
    EMERALD, MUTED, ModularHeading, build_pdf, fonts, paragraph,
    modular_metric_strip, modern_table, TrendGraphic, ActivityGraphic,
    BarsGraphic, analytical_block, report_identification,
)
from ticketyn.api.fms_exports import capacity_text, headers, LABELS
from ticketyn.api.fms_data import distribution_labels
from ticketyn.api.fms_reports import MODELS, report_query, summary_data
from ticketyn.api.reports import read_snapshot
from ticketyn.schemas.fms_report import FmsReportSummary

MAX_OPERATIONS = 2000
MAX_TEXT_CHARACTERS = 2_000_000
TITLES = {'activations': 'Reportería de activaciones', 'capacity-changes': 'Reportería de cambios de capacidad', 'circuit-lifecycle': 'Reportería de bajas y reactivaciones'}


def metrics(kind, k):
    if kind == 'activations':
        return [
            ('ACTIVACIONES', k.total, EMERALD),
            ('CLIENTES DISTINTOS', k.distinct_customers, EMERALD),
            ('CIRCUITOS DISTINTOS', k.distinct_circuits, EMERALD),
        ]
    if kind == 'capacity-changes':
        net = k.known_net_mbps
        net_text = ('−' if net < 0 else '') + capacity_text(abs(net), 'Mbps')
        return [
            ('INCREMENTOS', k.increases, EMERALD),
            ('DECREMENTOS', k.decreases, colors.HexColor('#0284c7')),
            ('CAPACIDAD AGREGADA CONOCIDA', capacity_text(k.known_added_mbps, 'Mbps'), EMERALD),
            ('CAPACIDAD REDUCIDA CONOCIDA', capacity_text(k.known_reduced_mbps, 'Mbps'), colors.HexColor('#0284c7')),
            ('VARIACIÓN NETA CONOCIDA', net_text, EMERALD if net >= 0 else colors.HexColor('#0284c7')),
        ]
    return [
        ('BAJAS', k.deactivations, colors.HexColor('#475569')),
        ('REACTIVACIONES', k.reactivations, EMERALD),
        ('CIRCUITOS CON BAJAS', k.distinct_deactivated_circuits, colors.HexColor('#475569')),
        ('CIRCUITOS CON REACTIVACIONES', k.distinct_reactivated_circuits, EMERALD),
    ]


def detail_rows(session, kind, filters):
    for row in session.scalars(report_query(MODELS[kind], filters).execution_options(yield_per=200)):
        circuit = row.circuit
        values = [row.effective_at.astimezone(ZoneInfo(filters.timezone)).strftime('%d/%m/%Y\n%H:%M:%S'),
            circuit.customer.name, circuit.circuit_code, circuit.description or 'Sin descripción',
            row.sector.name if row.sector else 'Sin registrar', row.node.name if row.node else 'Sin registrar', row.responsible.name]
        if kind == 'activations': values = [row.reference, *values, *distribution_labels(row)]
        elif kind == 'capacity-changes':
            values.extend([LABELS[row.operation_type], capacity_text(row.previous_capacity, row.previous_unit), capacity_text(row.new_capacity, row.new_unit), row.description or '—'])
        else:
            values.extend([LABELS[row.operation_type], row.reason.name if row.operation_type == 'DEACTIVATE' and row.reason else '—', row.observations or '—'])
        yield values


def statistical_pdf(session, kind, filters, output):
    summary = FmsReportSummary.model_validate(summary_data(session, kind, filters))
    count = session.scalar(select(func.count()).select_from(report_query(MODELS[kind], filters).order_by(None).subquery()))
    if count > MAX_OPERATIONS:
        raise HTTPException(413, f'El reporte supera {MAX_OPERATIONS} operaciones. Reduce el período o selecciona un Sector, Nodo o Responsable.')
    rows, characters = [], 0
    for row in detail_rows(session, kind, filters):
        characters += sum(len(str(value)) for value in row)
        if characters > MAX_TEXT_CHARACTERS:
            raise HTTPException(413, 'El contenido del reporte es demasiado extenso. Reduce el período o los filtros; no se ha truncado ningún registro.')
        rows.append(row)
    fonts()
    zone = ZoneInfo(filters.timezone)
    width = landscape(A4)[0] - 60
    title = TITLES[kind]
    scope = ' · '.join(f'Por {label}: {getattr(summary, field).name}' for field, label in [('sector', 'Sector'), ('node', 'Nodo'), ('responsible', 'Responsable')] if getattr(summary, field)) or 'General'
    period = f'{filters.from_at.astimezone(zone):%d/%m/%Y %H:%M} — {filters.to_at.astimezone(zone):%d/%m/%Y %H:%M} (fin exclusivo)' if filters.from_at else 'Todos · Sin restricción temporal'
    story = [
        report_identification(
            title,
            period=period,
            filters=scope if scope != 'General' else None,
            total=count,
            accent=EMERALD,
            category='GESTIÓN DE SERVICIOS · OPERACIONES FMS',
            width=width,
        ),
        ModularHeading('Resumen', accent=EMERALD),
        modular_metric_strip(metrics(kind, summary.kpis), width, accent=EMERALD),
        Spacer(1, 4),
        paragraph('Fecha efectiva de la operación. Sector y Nodo registrados históricamente. Responsable de la operación.', size=7.5, color=MUTED),
    ]
    if kind == 'capacity-changes':
        story.append(paragraph(f'Variaciones conocidas: 1 Gbps = 1000 Mbps. {summary.kpis.unknown_variations} operaciones sin capacidad anterior conocida cuentan como eventos, pero no aportan variación.', size=7.5, color=MUTED))
    elif kind == 'circuit-lifecycle':
        story.append(paragraph('Bajas y reactivaciones son eventos. Su diferencia no representa circuitos actualmente fuera de servicio.', size=7.5, color=MUTED))
    else:
        story.append(paragraph('Circuitos activados durante el período; no representa el estado administrativo actual.', size=7.5, color=MUTED))
    heading = 'Evolución de activaciones' if kind == 'activations' else 'Evolución de incrementos y decrementos' if kind == 'capacity-changes' else 'Evolución de bajas y reactivaciones'
    chart = TrendGraphic(summary.trend, zone, width, summary.period.granularity, accent=EMERALD) if kind == 'activations' else ActivityGraphic(
        [SimpleNamespace(start_at=x.start_at, started=x.first, closed=x.second) for x in summary.trend], zone, width, summary.period.granularity,
        labels=('Incrementos', 'Decrementos') if kind == 'capacity-changes' else ('Bajas', 'Reactivaciones'),
        accent=EMERALD,
    )
    story.extend([KeepTogether([ModularHeading(heading, accent=EMERALD), chart]), Spacer(1, 8)])
    if not summary.trend or not any(x.count for x in summary.trend):
        story.append(paragraph('Sin operaciones en el período.'))
    for values, name, count_label in [(summary.customers, 'Top 10 de clientes por circuitos distintos activados', 'Circuitos distintos')] if kind == 'activations' and scope == 'General' else [(summary.reasons, 'Distribución de bajas por motivo', 'Bajas')] if kind == 'circuit-lifecycle' else []:
        # Keep every reason legible: bounded vector charts, complete data across blocks.
        for start in range(0, max(1, len(values)), 10):
            group = values[start:start + 10]
            label = f'{name} · {start + 1}–{start + len(group)} de {len(values)}' if len(values) > 10 else name
            table = modern_table(['Nombre', count_label], ([x.label, x.count] for x in group), [width - 110, 110], word_wrap='LTR', light=True, accent=EMERALD)
            story.extend(analytical_block(ModularHeading(label, accent=EMERALD), BarsGraphic(group, width, accent=EMERALD), table, width))
            story.append(Spacer(1, 8))
    columns = headers(MODELS[kind])
    weights = [2 if x in ('Descripción del circuito', 'Descripción', 'Observaciones') else 1.3 if x in ('Cliente', 'Responsable', 'Fecha y hora efectiva') else 1.2 if x in ('Tipo de operación', 'Código del circuito', 'Capacidad anterior', 'Capacidad nueva') else 1 for x in columns]
    pdf_columns = [x.replace('Fecha y hora efectiva', 'Fecha/hora\nefectiva').replace('Capacidad anterior', 'Capacidad\nanterior').replace('Capacidad nueva', 'Capacidad\nnueva').replace('Equipo de distribución', 'Equipo de\ndistribución') for x in columns]
    story.append(ModularHeading(f'Detalle de operaciones · {count} registros', accent=EMERALD))
    story.append(modern_table(pdf_columns, rows, [width * x / sum(weights) for x in weights], compact=True, reference=kind == 'activations', word_wrap='LTR', light=True, accent=EMERALD, status_colors=True) if rows else paragraph('Sin resultados.'))
    build_pdf(
        output,
        title,
        filters.timezone,
        story,
        issued_at=summary.generated_at.astimezone(zone).strftime('%d/%m/%Y %H:%M:%S'),
        subtitle='GESTIÓN DE SERVICIOS · OPERACIONES FMS',
        modular=True,
        landscape_mode=True,
        accent=EMERALD,
    )


def report_pdf_response(session, kind, filters):
    output = SpooledTemporaryFile(max_size=2 * 1024 * 1024)
    try:
        read_snapshot(session)
        statistical_pdf(session, kind, filters, output)
        output.seek(0)
    except HTTPException:
        output.close()
        raise
    except Exception:
        output.close()
        raise HTTPException(500, 'No se pudo generar el reporte estadístico FMS.') from None
    def chunks():
        try:
            while chunk := output.read(65536): yield chunk
        finally:
            output.close()
    scope = 'sector' if filters.sector_id else 'nodo' if filters.node_id else 'responsable' if filters.responsible_id else 'general'
    return StreamingResponse(chunks(), media_type='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="ticketyn-analisis-{kind}-{scope}.pdf"',
        'Cache-Control': 'no-store',
    }, background=BackgroundTask(output.close))
