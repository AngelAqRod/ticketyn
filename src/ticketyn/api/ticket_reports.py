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
from ticketyn.api.escalation_data import list_escalations
from ticketyn.api.documents import build_pdf, duration_text, fonts, modern_table, paragraph, section, MUTED, BLUE, PURPLE, EMERALD, AMBER, CYAN, MODULAR_WIDTH, MODULAR_HEIGHT, ModularHeading, identification, metadata_modules, timeline_entry
from ticketyn.api.reports import read_snapshot
from ticketyn.api.ticket_data import get_ticket
from ticketyn.api.ticket_update_data import list_updates
from ticketyn.models import Circuit, Customer, Ticket, TicketUpdate, InternalTicket, Sector, Node, Provider
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


def intervention_block(heading, content, section_heading=None, *, modular=False):
    """Small interventions travel together; large text starts here and can split.

    Match the selected build_pdf frame/margins. Never bind an entire lengthy
    intervention to its section heading: bind only its first two lines instead.
    """
    width = MODULAR_WIDTH if modular else landscape(A4)[0] - 60 - 12
    frame_height = MODULAR_HEIGHT if modular else landscape(A4)[1] - 90 - 43 - 12
    headings = [*([section_heading] if section_heading is not None else []), heading]
    items = [*headings, content]
    height = sum(item.wrap(width, frame_height)[1] + item.getSpaceBefore() + item.getSpaceAfter() for item in items)
    if height <= (72 if modular else frame_height / 2):
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


def related_internal_incident(session, internal_ticket_id):
    """One bounded projection; inactive catalogs remain valid historical references."""
    row = session.execute(select(
        InternalTicket.reference, InternalTicket.title, InternalTicket.description,
        Sector.name.label('sector'), Node.name.label('node'),
        InternalTicket.status, Provider.name.label('provider'),
    ).join(Sector, InternalTicket.sector_id == Sector.id)
     .outerjoin(Node, InternalTicket.node_id == Node.id)
     .outerjoin(Provider, InternalTicket.provider_id == Provider.id)
     .where(InternalTicket.id == internal_ticket_id)).one_or_none()
    if row is None:
        # A valid FK normally guarantees this; never invent linked incident data.
        raise HTTPException(404, 'Ticket interno relacionado no encontrado')
    return row


def internal_pdf(session, ticket_id, output, zone, issued):
    fonts()
    section = ModularHeading
    ticket = get_ticket(session, ticket_id)
    updates = list_updates(session, ticket_id)
    story = [identification(ticket.reference, ticket.title, ticket.status, 'Reporte técnico interno', date_text(ticket.start_at, zone)),
        section('Identificación y tiempos'), metadata_modules([
            ['Cliente', f'{ticket.customer.name} · {ticket.customer.customer_code}'],
            ['Circuito', ticket.circuit.circuit_code], ['Nodo', ticket.node.name if ticket.node else 'Sin asignar'],
            ['Sector', ticket.sector.name], ['Departamento', ticket.department.name],
            ['Responsable', ticket.responsible.name if ticket.responsible else 'Sin asignar'],
            ['Tipo de incidencia', ticket.incident_type.name], *timing_rows(ticket, zone, issued)]),
        *intervention_block(section('Descripción original'), paragraph(ticket.description, size=10), modular=True)]
    story.extend(intervention_block(section('Resolución documentada', accent=EMERALD), paragraph(ticket.resolution or 'Sin resolución documentada.', size=10), modular=True))
    if getattr(ticket, 'internal_ticket_id', None) is not None:
        related = related_internal_incident(session, ticket.internal_ticket_id)
        rows = [['Correlativo', related.reference], ['Incidencia', related.title or related.description],
                ['Sector', related.sector]]
        if related.node is not None:
            rows.append(['Nodo', related.node])
        rows.extend([['Estado actual', 'Abierto' if related.status == 'OPEN' else 'Cerrado'],
                     ['Proveedor atribuible', related.provider or 'Ninguno']])
        story.extend([section('Incidencia interna relacionada', accent=PURPLE),
                      metadata_modules(rows)])

    history_heading = section('Seguimiento cronológico · Uso interno', accent=CYAN, keep=False)
    if not updates:
        history_heading.style.keepWithNext = True
        story.extend([history_heading, paragraph('Sin intervenciones registradas.', size=10)])
    for index, update in enumerate(updates):
        public = update.visibility == 'PUBLIC'
        story.append(timeline_entry(date_text(update.occurred_at, zone), update.content,
            responsible=update.responsible.name if update.responsible else 'Sin asignar',
            label='Pública' if public else 'Interna', accent=EMERALD if public else CYAN,
            association=f'Escalamiento #{update.escalation_id}' if update.escalation_id is not None else None,
            section_heading=history_heading if index == 0 else None))
    escalations = list_escalations(session, ticket_id)
    append_escalations(story, escalations, zone, modular=True)
    build_pdf(output, 'Reporte técnico interno', str(zone), story, issued_at=date_text(issued, zone), modular=True, reference=ticket.reference)


def append_escalations(story, escalations, zone, *, modular=False, accent=AMBER):
    heading_style = (lambda value, **kwargs: ModularHeading(value, accent=accent, **kwargs)) if modular else section
    escalation_heading = heading_style('Historial de escalamientos', keep=False)
    if not escalations:
        escalation_heading.style.keepWithNext = True
        story.extend([escalation_heading, paragraph('Sin escalamientos registrados.', size=10)])
    for index, escalation in enumerate(escalations):
        heading = paragraph(f'Escalamiento #{escalation.id} · Destinatario: {escalation.recipient.name if escalation.recipient else "Pendiente de asignación"} · {"Activo" if escalation.status == "ACTIVE" else "Finalizado"}', bold=True, size=9)
        if modular:
            heading = ModularHeading(heading.getPlainText(), accent=AMBER if escalation.status == 'ACTIVE' else EMERALD, size=8.5, keep=False)
        details = []
        if escalation.recipient_department_name:
            details.append(f'Departamento histórico: {escalation.recipient_department_name}')
        position = escalation.recipient_position_name or escalation.recipient_level
        if position:
            details.append(f'Puesto histórico: {position}')
        details.extend([f'Motivo: {escalation.reason.name}', f'Inicio: {date_text(escalation.started_at, zone)}'])
        if escalation.finished_at:
            details.extend([f'Finalizado: {date_text(escalation.finished_at, zone)}', f'Duración: {duration_text((escalation.finished_at - escalation.started_at).total_seconds())}'])
        story.extend(intervention_block(heading, paragraph('\n'.join([*details, escalation.description]), size=10), escalation_heading if index == 0 else None, modular=modular))


def customer_pdf(session, ticket_id, output, zone, issued):
    fonts()
    ticket = customer_report(session, ticket_id)
    story = [identification(ticket.reference, ticket.title, ticket.status, 'Reporte para cliente', date_text(ticket.start_at, zone)),
        ModularHeading('Identificación y tiempos'),
        metadata_modules([['Cliente', ticket.customer_name], ['Circuito', ticket.circuit_code],
                          *timing_rows(ticket, zone, issued)]),
        *intervention_block(ModularHeading('Descripción del incidente'), paragraph(ticket.customer_description or 'Sin descripción autorizada para compartir.', size=10), modular=True),
        *intervention_block(ModularHeading('Resolución', accent=EMERALD), paragraph(ticket.customer_resolution or 'Sin resolución autorizada para compartir.', size=10), modular=True)]
    history_heading = ModularHeading('Seguimiento público · Cronológico', accent=BLUE, keep=False)
    if not ticket.interventions:
        history_heading.style.keepWithNext = True
        story.extend([history_heading, paragraph('Sin intervenciones públicas registradas.', size=10)])
    for index, update in enumerate(ticket.interventions):
        story.append(timeline_entry(date_text(update.occurred_at, zone), update.content,
            variant='customer', section_heading=history_heading if index == 0 else None))
    build_pdf(output, 'Reporte para cliente', str(zone), story, issued_at=date_text(issued, zone),
              modular=True, reference=ticket.reference)


def report_response(session, ticket_id, options, audience, *, renderer=None, filename=None):
    output = SpooledTemporaryFile(max_size=2 * 1024 * 1024)
    try:
        read_snapshot(session)
        renderer = renderer or (internal_pdf if audience == 'internal' else customer_pdf)
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
    filename = filename or f'ticketyn-ticket-{ticket_id}-{name}.pdf'
    return StreamingResponse(chunks(), media_type='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{filename}"',
                 'Cache-Control': 'no-store'}, background=BackgroundTask(output.close))


@router.get('/{id}/reports/internal/pdf')
def internal_report(id: Annotated[int, Path(gt=0)], session: DBSession, options: Annotated[TicketReportOptions, Query()]):
    return report_response(session, id, options, 'internal')


@router.get('/{id}/reports/customer/pdf')
def public_report(id: Annotated[int, Path(gt=0)], session: DBSession, options: Annotated[TicketReportOptions, Query()]):
    return report_response(session, id, options, 'customer')
