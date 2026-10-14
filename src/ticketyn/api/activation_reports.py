"""PDF individual de activación, independiente de los listados FMS."""
from datetime import datetime, timezone
from tempfile import SpooledTemporaryFile
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import select
from starlette.background import BackgroundTask

from ticketyn.api.documents import build_pdf, fonts, modern_table, paragraph, section, MUTED
from ticketyn.api.fms_data import operation_query
from ticketyn.api.reports import read_snapshot
from ticketyn.api.ticket_reports import TicketReportOptions, date_text, intervention_block
from ticketyn.models.fms import Activation, ActivationIntervention


class ActivationReportOptions(TicketReportOptions):
    timezone: str = Field(default='America/Guatemala', max_length=100)


def activation_pdf(session, activation_id, output, zone, issued):
    activation = session.scalar(operation_query(Activation).where(Activation.id == activation_id))
    if activation is None:
        raise HTTPException(404, 'Activación no encontrada')
    fonts()
    circuit = activation.circuit
    story = [paragraph(activation.reference, size=18, bold=True, keep=True),
             paragraph('Reporte individual de activación', size=12, color=MUTED),
             paragraph(f'Generado: {date_text(issued, zone)}', size=9),
             section('Información general'), modern_table(['Dato', 'Valor'], [
                 ['Cliente', f'{circuit.customer.name} · {circuit.customer.customer_code}'],
                 ['Código del circuito', circuit.circuit_code],
                 ['Descripción del circuito', circuit.description or 'Sin descripción'],
                 ['Sector', activation.sector.name if activation.sector else 'Sin registrar'],
                 ['Nodo', activation.node.name if activation.node else 'Sin registrar'],
                 ['Tipo de servicio (actual del circuito)', circuit.service_type.name if circuit.service_type else 'Sin registrar'],
                 ['Fecha y hora efectiva de activación', date_text(activation.effective_at, zone)],
                 ['Responsable', activation.responsible.name],
             ], [250, 530], compact=True)]
    interventions = session.scalars(select(ActivationIntervention)
        .where(ActivationIntervention.activation_id == activation_id)
        .order_by(ActivationIntervention.occurred_at, ActivationIntervention.id)
        .execution_options(yield_per=200))
    heading = section('Bitácora de activación · Cronológica', keep=False)
    any_interventions = False
    for update in interventions:
        title = paragraph(f'{date_text(update.occurred_at, zone)} · {update.responsible.name}', bold=True, size=9)
        story.extend(intervention_block(title, paragraph(update.content, size=10), heading if not any_interventions else None))
        any_interventions = True
    if not any_interventions:
        heading.style.keepWithNext = True
        story.extend([heading, paragraph('Sin intervenciones registradas.', size=10)])
    story.extend([section('Metadatos'), paragraph(f'Fecha de creación: {date_text(activation.created_at, zone)}', size=9)])
    build_pdf(output, f'Activación · {activation.reference}', str(zone), story, issued_at=date_text(issued, zone))


def activation_report_response(session, activation_id, options):
    output = SpooledTemporaryFile(max_size=2 * 1024 * 1024)
    try:
        read_snapshot(session)
        activation_pdf(session, activation_id, output, ZoneInfo(options.timezone), datetime.now(timezone.utc))
        output.seek(0)
    except HTTPException:
        output.close()
        raise
    except Exception:
        output.close()
        raise HTTPException(500, 'No se pudo generar el reporte de la activación.') from None
    def chunks():
        try:
            while chunk := output.read(65536): yield chunk
        finally:
            output.close()
    return StreamingResponse(chunks(), media_type='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="ticketyn-activacion-{activation_id}.pdf"',
        'Cache-Control': 'no-store',
    }, background=BackgroundTask(output.close))
