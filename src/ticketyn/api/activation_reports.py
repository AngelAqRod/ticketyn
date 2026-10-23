"""PDF individual de activación, independiente de los listados FMS."""
from datetime import datetime, timezone
from tempfile import SpooledTemporaryFile
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import select
from starlette.background import BackgroundTask

from ticketyn.api.documents import (
    EMERALD, MUTED, ModularHeading, build_pdf, fonts, identification,
    metadata_modules, paragraph, timeline_entry,
)
from ticketyn.api.fms_exports import capacity_text
from ticketyn.api.fms_data import operation_query, distribution_labels
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
    device_name, port_name = distribution_labels(activation)
    title = f'{circuit.customer.name} · {circuit.circuit_code}'
    story = [
        identification(
            activation.reference,
            title,
            'ACTIVA',
            'Reporte individual de activación',
            f'Generado: {date_text(issued, zone)}',
            accent=EMERALD,
            capsule_label='Activa',
            capsule_color=EMERALD,
        ),
        ModularHeading('Información general', accent=EMERALD),
        metadata_modules([
            ['Cliente', f'{circuit.customer.name} · {circuit.customer.customer_code}'],
            ['Código del circuito', circuit.circuit_code],
            ['Descripción del circuito', circuit.description or 'Sin descripción'],
            ['Sector', activation.sector.name if activation.sector else 'Sin registrar'],
            ['Nodo', activation.node.name if activation.node else 'Sin registrar'],
            ['Equipo de distribución', device_name],
            ['Puerto', port_name],
            ['Tipo de servicio histórico', activation.service_type_name or 'Sin registrar'],
            ['CPE de activación', activation.cpe_activation or 'Sin registrar'],
            ['Capacidad inicial histórica', capacity_text(activation.initial_capacity, activation.initial_capacity_unit)],
            ['Fecha y hora efectiva de activación', date_text(activation.effective_at, zone)],
            ['Responsable', activation.responsible.name],
        ]),
    ]
    story.extend(intervention_block(
        ModularHeading('Notas internas de activación', accent=EMERALD),
        paragraph(activation.activation_notes or 'Sin notas registradas', size=10),
        modular=True,
    ))
    story.extend(intervention_block(
        ModularHeading('Información para el cliente', accent=EMERALD),
        paragraph(activation.customer_activation_notes or 'Sin notas para cliente registradas', size=10),
        modular=True,
    ))
    interventions = list(session.scalars(select(ActivationIntervention)
        .where(ActivationIntervention.activation_id == activation_id)
        .order_by(ActivationIntervention.occurred_at, ActivationIntervention.id)
        .execution_options(yield_per=200)))
    heading = ModularHeading('Bitácora de activación · Cronológica', accent=EMERALD, keep=False)
    if interventions:
        for index, update in enumerate(interventions):
            story.append(timeline_entry(
                date_text(update.occurred_at, zone),
                update.content,
                responsible=update.responsible.name if update.responsible else 'Sin asignar',
                accent=EMERALD,
                section_heading=heading if index == 0 else None,
            ))
    else:
        heading.style.keepWithNext = True
        story.extend([heading, paragraph('Sin intervenciones registradas.', size=10)])
    story.extend([
        ModularHeading('Metadatos', accent=EMERALD),
        paragraph(f'Fecha de creación: {date_text(activation.created_at, zone)}', size=8.5, color=MUTED),
    ])
    build_pdf(
        output,
        f'Activación · {activation.reference}',
        str(zone),
        story,
        issued_at=date_text(issued, zone),
        subtitle='GESTIÓN DE SERVICIOS · OPERACIONES FMS',
        modular=True,
        reference=activation.reference,
        accent=EMERALD,
    )


def activation_report_response(session, activation_id, options, *, customer=False):
    output = SpooledTemporaryFile(max_size=2 * 1024 * 1024)
    try:
        read_snapshot(session)
        if customer:
            from ticketyn.api.customer_activation_reports import customer_activation_report, customer_activation_pdf
            customer_activation_pdf(customer_activation_report(session, activation_id), output,
                ZoneInfo(options.timezone), datetime.now(timezone.utc))
        else:
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
    filename = f'ticketyn-activacion-{activation_id}-cliente.pdf' if customer else f'ticketyn-activacion-{activation_id}.pdf'
    return StreamingResponse(chunks(), media_type='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="{filename}"',
        'Cache-Control': 'no-store',
    }, background=BackgroundTask(output.close))
