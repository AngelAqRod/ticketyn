"""Documentos por ticket; la proyección de cliente nunca recibe textos internos."""
from dataclasses import dataclass
from datetime import datetime, timezone
from tempfile import SpooledTemporaryFile
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import KeepTogether
from starlette.background import BackgroundTask

from ticketyn.api.crud import DBSession
from ticketyn.api.documents import build_pdf, duration_text, fonts, modern_table, paragraph, section, MUTED
from ticketyn.api.reports import read_snapshot
from ticketyn.api.ticket_data import get_ticket
from ticketyn.api.ticket_update_data import list_updates
from ticketyn.models import Circuit, Customer, Ticket, TicketUpdate
from ticketyn.schemas.report import ReportFilters

router = APIRouter(prefix='/api/tickets', tags=['ticket-reports'])


class TicketReportOptions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    timezone: str = Field(default='UTC', max_length=100)

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        return ReportFilters.valid_timezone(value)


@dataclass(frozen=True)
class PublicIntervention:
    occurred_at: datetime
    content: str


@dataclass(frozen=True)
class CustomerReport:
    reference: str
    title: str
    customer_name: str
    circuit_code: str
    start_at: datetime
    end_at: datetime | None
    status: str
    customer_description: str | None
    customer_resolution: str | None
    interventions: list[PublicIntervention]


def customer_report(session, ticket_id):
    # Lista positiva de columnas: ni ORM Ticket ni un documento interno se
    # pasan al render de cliente. Solo el título solicitado para identificar el incidente; no IP, catálogos o personal.
    row = session.execute(select(Ticket.reference, Ticket.title, Customer.name.label('customer_name'), Circuit.circuit_code,
        Ticket.start_at, Ticket.end_at, Ticket.status, Ticket.customer_description, Ticket.customer_resolution)
        .join(Customer, Ticket.customer_id == Customer.id).join(Circuit, Ticket.circuit_id == Circuit.id)
        .where(Ticket.id == ticket_id)).one_or_none()
    if row is None:
        raise HTTPException(404, 'Ticket no encontrado')
    interventions = [PublicIntervention(*entry) for entry in session.execute(
        select(TicketUpdate.occurred_at, TicketUpdate.content)
        .where(TicketUpdate.ticket_id == ticket_id, TicketUpdate.visibility == 'PUBLIC')
        .order_by(TicketUpdate.occurred_at, TicketUpdate.id))]
    return CustomerReport(**row._mapping, interventions=interventions)


def date_text(value, zone):
    return value.astimezone(zone).strftime('%d/%m/%Y %H:%M:%S %z') if value else 'Sin fecha de cierre'


def timing_rows(ticket, zone, issued):
    rows = [['Estado', 'Abierto · En curso' if ticket.status == 'OPEN' else 'Cerrado'],
            ['Inicio', date_text(ticket.start_at, zone)], ['Cierre', date_text(ticket.end_at, zone)]]
    if ticket.status == 'OPEN':
        rows.append(['Tiempo transcurrido al emitir (no es tiempo de resolución)', duration_text(max(0, (issued - ticket.start_at).total_seconds()))])
    else:
        duration = (ticket.end_at - ticket.start_at).total_seconds() if ticket.end_at else None
        rows.append(['Duración del incidente', duration_text(duration) if duration is not None else 'No disponible · Sin fecha de cierre'])
    return rows


def intervention_block(heading, content, section_heading=None):
    """Small interventions travel together; large text starts here and can split.

    Match build_pdf's landscape frame/margins. Never bind an entire lengthy
    intervention to its section heading: bind only its first two lines instead.
    """
    width = landscape(A4)[0] - 60 - 12
    frame_height = landscape(A4)[1] - 90 - 43 - 12
    headings = [*([section_heading] if section_heading is not None else []), heading]
    items = [*headings, content]
    height = sum(item.wrap(width, frame_height)[1] + item.getSpaceBefore() + item.getSpaceAfter() for item in items)
    if height <= frame_height / 2:
        return [KeepTogether(items)]
    # The first two lines anchor the intervention without forcing the rest onto
    # a new page. ReportLab's Paragraph.split preserves escaped text and breaks.
    fragments = content.split(width, content.style.leading * 2)
    if len(fragments) > 1:
        fragments[0].spaceAfter = 0
        prefix = [*headings, fragments[0]]
        prefix_height = sum(item.wrap(width, frame_height)[1] + item.getSpaceAfter() for item in prefix)
        if prefix_height <= frame_height:
            for item in headings:
                item.style.keepWithNext = True
        return [*headings, *fragments]
    # A very long heading must itself remain splittable.
    if section_heading is not None:
        section_heading.style.keepWithNext = True
    return items


def internal_pdf(session, ticket_id, output, zone, issued):
    fonts()
    ticket = get_ticket(session, ticket_id)
    updates = list_updates(session, ticket_id)
    story = [paragraph(ticket.reference, size=18, bold=True, keep=True),
        paragraph(ticket.title, size=12, color=MUTED), section('Identificación y tiempos'),
        modern_table(['Dato', 'Valor'], [
            ['Cliente', f'{ticket.customer.name} · {ticket.customer.customer_code}'],
            ['Circuito', ticket.circuit.circuit_code], ['Nodo de distribución', ticket.node.name if ticket.node else 'Sin asignar'],
            ['Sector', ticket.sector.name], ['Departamento', ticket.department.name],
            ['Responsable', ticket.responsible.name if ticket.responsible else 'Sin asignar'],
            ['Tipo de incidencia', ticket.incident_type.name], *timing_rows(ticket, zone, issued)], [250, 530], compact=True),
        section('Descripción original'), paragraph(ticket.description, size=10)]
    story.extend([section('Resolución documentada'), paragraph(ticket.resolution or 'Sin resolución documentada.', size=10)])
    history_heading = section('Seguimiento cronológico · Uso interno', keep=False)
    if not updates:
        history_heading.style.keepWithNext = True
        story.extend([history_heading, paragraph('Sin intervenciones registradas.', size=10)])
    for index, update in enumerate(updates):
        visibility = 'Interna' if update.visibility == 'INTERNAL' else 'Pública'
        heading = paragraph(f'{date_text(update.occurred_at, zone)} · {update.responsible.name if update.responsible else "Sin asignar"} · {visibility}', bold=True, size=9)
        story.extend(intervention_block(heading, paragraph(update.content, size=10), history_heading if index == 0 else None))
    build_pdf(output, 'Reporte técnico interno', str(zone), story, issued_at=date_text(issued, zone))


def customer_pdf(session, ticket_id, output, zone, issued):
    fonts()
    ticket = customer_report(session, ticket_id)
    story = [paragraph(ticket.reference, size=18, bold=True, keep=True),
        paragraph(ticket.title, size=12, color=MUTED), section('Identificación y tiempos'),
        modern_table(['Dato', 'Valor'], [['Cliente', ticket.customer_name], ['Circuito', ticket.circuit_code],
                                        *timing_rows(ticket, zone, issued)], [250, 530]),
        section('Descripción del incidente'), paragraph(ticket.customer_description or 'Sin descripción autorizada para compartir.', size=10),
        section('Resolución'), paragraph(ticket.customer_resolution or 'Sin resolución autorizada para compartir.', size=10),
        section('Seguimiento público · Cronológico')]
    if not ticket.interventions:
        story.append(paragraph('Sin intervenciones públicas registradas.', size=10))
    for update in ticket.interventions:
        story.extend([paragraph(date_text(update.occurred_at, zone), size=9, bold=True, keep=True), paragraph(update.content, size=10)])
    build_pdf(output, 'Reporte para cliente', str(zone), story, issued_at=date_text(issued, zone))


def report_response(session, ticket_id, options, audience):
    output = SpooledTemporaryFile(max_size=2 * 1024 * 1024)
    try:
        read_snapshot(session)
        renderer = internal_pdf if audience == 'internal' else customer_pdf
        renderer(session, ticket_id, output, ZoneInfo(options.timezone), datetime.now(timezone.utc))
        output.seek(0)
    except HTTPException:
        output.close()
        raise
    except Exception:
        output.close()
        # No exponer SQL, textos del ticket ni datos personales en errores.
        raise HTTPException(500, 'No se pudo generar el reporte del ticket.') from None

    def chunks():
        try:
            while chunk := output.read(65536):
                yield chunk
        finally:
            output.close()
    name = 'interno' if audience == 'internal' else 'cliente'
    return StreamingResponse(chunks(), media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="ticketyn-ticket-{ticket_id}-{name}.pdf"',
                 'Cache-Control': 'no-store'}, background=BackgroundTask(output.close))


@router.get('/{id}/reports/internal/pdf')
def internal_report(id: Annotated[int, Path(gt=0)], session: DBSession, options: Annotated[TicketReportOptions, Query()]):
    return report_response(session, id, options, 'internal')


@router.get('/{id}/reports/customer/pdf')
def public_report(id: Annotated[int, Path(gt=0)], session: DBSession, options: Annotated[TicketReportOptions, Query()]):
    return report_response(session, id, options, 'customer')
