"""Internal-ticket operations with explicit authorization and bounded context reads."""
from typing import Annotated, Literal
from fastapi import APIRouter, Path, Query, Request, HTTPException
from ticketyn.security.mutations import ticket_mutation
from sqlalchemy import select, func, or_
from ticketyn.api.internal_ticket_exports import export_pdf, export_xlsx
from ticketyn.api.ticket_exports import stream_ticket_export
from ticketyn.api.ticket_pdf_limits import ticket_pdf_export
from ticketyn.api.ticket_reports import TicketReportOptions, report_response
from ticketyn.api.internal_ticket_reports import internal_ticket_pdf
from ticketyn.api.crud import DBSession, get_or_404, save_item, update_item
from ticketyn.api import internal_ticket_data as data, escalation_data as escalations, ticket_update_data as updates, ticket_data
from ticketyn.api.ticket_numbers import locked_number_config, validate_number_config
from ticketyn.models import InternalTicket, InternalTicketNumberConfig, InternalTicketUpdate, InternalEscalation, InternalEscalationAudit, Ticket
from ticketyn.schemas.internal_ticket import InternalTicketCreate, InternalTicketPatch, InternalTicketResponse, InternalFilters, InternalUpdateCreate, InternalExportFilters
from ticketyn.schemas.ticket_update import TicketUpdateResponse, TicketUpdatePage
from ticketyn.schemas.escalation import EscalationCreate, EscalationResponse, EscalationEdit, EscalationFinish, EscalationAuditResponse
from ticketyn.schemas.ticket_number_config import TicketNumberConfigResponse, TicketNumberConfigUpdate
from ticketyn.schemas.ticket_close import TicketClose
from ticketyn.api.ticket_close import close_ticket

from pydantic import BaseModel

class InternalLinkSummary(BaseModel):
    id: int
    reference: str
    title: str

router = APIRouter(tags=['internal-tickets'])
RootId = Annotated[int, Path(gt=0)]
CONTEXT = dict(Ticket=InternalTicket, TicketUpdate=InternalTicketUpdate)
ESC_CONTEXT = dict(TicketEscalation=InternalEscalation, audit_model=InternalEscalationAudit)

@router.get('/api/settings/internal-ticket-number', response_model=TicketNumberConfigResponse)
def number_config(session: DBSession):
    return save_item(session, locked_number_config(session, InternalTicketNumberConfig))

@router.patch('/api/settings/internal-ticket-number', response_model=TicketNumberConfigResponse)
def change_config(payload: TicketNumberConfigUpdate, session: DBSession):
    try:
        config = locked_number_config(session, InternalTicketNumberConfig)
        values = payload.model_dump(exclude_unset=True)
        validate_number_config(session, config, values, Ticket=InternalTicket)
        return update_item(session, config, values)
    except Exception:
        session.rollback(); raise

@router.post('/api/internal-tickets', response_model=InternalTicketResponse, status_code=201)
def create(payload: InternalTicketCreate, session: DBSession, request: Request):
    ticket_mutation(request.state.principal, 'internal_tickets', payload.model_dump())
    return data.response(session, data.persist(session, payload.model_dump()))

@router.get('/api/internal-tickets', response_model=list[InternalTicketResponse | InternalLinkSummary])
def listing(session: DBSession, filters: Annotated[InternalFilters, Query()], request: Request):
    values = filters.model_dump()
    rows = list(session.scalars(data.statement(values).limit(filters.limit).offset(filters.offset)))
    if not {'internal_tickets.view', 'reports.internal_tickets.view'} & request.state.principal.permissions:
        return [{'id': row.id, 'reference': row.reference, 'title': row.title} for row in rows]
    counts = dict(session.execute(select(Ticket.internal_ticket_id, func.count(Ticket.id)).where(Ticket.internal_ticket_id.in_([row.id for row in rows])).group_by(Ticket.internal_ticket_id)).all()) if rows else {}
    return [data.response(session, row, counts.get(row.id, 0)) for row in rows]

@router.get('/api/internal-tickets/export/{format}')
def export_list(session: DBSession, request: Request, format: Literal['pdf', 'xlsx'], filters: Annotated[InternalExportFilters, Query()]):
    with ticket_pdf_export(request, format):
        return stream_ticket_export(session, format, filters, 'ticketyn-tickets-internos',
                                    export_pdf if format == 'pdf' else export_xlsx)

@router.get('/api/internal-tickets/{id}', response_model=InternalTicketResponse | InternalLinkSummary)
def detail(id: RootId, session: DBSession, request: Request):
    permissions = request.state.principal.permissions
    if 'internal_tickets.view' not in permissions:
        # Candidate searches belong to link actions; read-only context must be
        # backed by a real relationship to a module the caller can consult.
        if not {'tickets.link', 'changes.link'} & permissions:
            contexts = []
            if 'tickets.view' in permissions:
                contexts.append(select(Ticket.id).where(Ticket.internal_ticket_id == id).exists())
            if 'changes.view' in permissions:
                from ticketyn.models.change import ChangeTicket
                contexts.append(select(ChangeTicket.change_id).where(ChangeTicket.internal_ticket_id == id).exists())
            if not contexts or not session.scalar(select(or_(*contexts))):
                raise HTTPException(403, 'No tienes permiso para consultar este ticket interno')
        item = get_or_404(session, InternalTicket, id)
        return {'id': item.id, 'reference': item.reference, 'title': item.title}
    return data.response(session, get_or_404(session, InternalTicket, id))

@router.patch('/api/internal-tickets/{id}', response_model=InternalTicketResponse)
def patch(id: RootId, payload: InternalTicketPatch, session: DBSession, request: Request):
    item = session.scalar(select(InternalTicket).where(InternalTicket.id == id).with_for_update(of=InternalTicket))
    if item is not None:
        ticket_mutation(request.state.principal, 'internal_tickets', payload.model_dump(exclude_unset=True), item)
    return data.response(session, data.persist(session, payload.model_dump(exclude_unset=True), id))

@router.post('/api/internal-tickets/{id}/close', response_model=InternalTicketResponse)
def quick_close(id: RootId, payload: TicketClose, session: DBSession, request: Request):
    ticket = close_ticket(session, InternalTicket, id, payload, request.state.principal, 'internal_tickets',
                          lambda session, id, changes: data.persist(session, changes, id))
    return data.response(session, ticket)

@router.get('/api/internal-tickets/{id}/related', response_model=dict)
def related(id: RootId, session: DBSession, limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Annotated[int, Query(ge=0)] = 0, request: Request = None):
    get_or_404(session, InternalTicket, id)
    rows = session.execute(ticket_data.joined_ticket_statement({}).where(Ticket.internal_ticket_id == id).limit(limit).offset(offset))
    items = [ticket_data.ticket_response(row).model_dump(mode='json') for row in rows]
    if 'tickets.view' not in request.state.principal.permissions:
        items = [{key: row[key] for key in ('id', 'reference', 'title', 'status', 'customer')} for row in items]
    return {'total': session.scalar(select(func.count(Ticket.id)).where(Ticket.internal_ticket_id == id)), 'items': items}

@router.get('/api/internal-tickets/{id}/updates', response_model=list[TicketUpdateResponse] | TicketUpdatePage)
def history(id: RootId, session: DBSession, limit: Annotated[int | None, Query(ge=1, le=100)] = None, cursor: Annotated[str | None, Query(max_length=1024)] = None, escalation_id: Annotated[int | None, Query(gt=0)] = None):
    if limit is None:
        if cursor is not None:
            from fastapi import HTTPException
            raise HTTPException(422, 'El cursor requiere limit')
        return updates.list_updates(session, id, escalation_id, **CONTEXT)
    return updates.page_updates(session, id, limit, cursor, escalation_id, **CONTEXT)

@router.post('/api/internal-tickets/{id}/updates', response_model=TicketUpdateResponse, status_code=201)
def intervention(id: RootId, payload: InternalUpdateCreate, session: DBSession):
    return updates.create_update(session, id, payload.model_dump(), TicketEscalation=InternalEscalation, **CONTEXT)

@router.get('/api/internal-tickets/{id}/escalations', response_model=list[EscalationResponse])
def escalation_list(id: RootId, session: DBSession, limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Annotated[int, Query(ge=0)] = 0):
    get_or_404(session, InternalTicket, id)
    return escalations.list_escalations(session, id, newest_first=True, limit=limit, offset=offset, TicketEscalation=InternalEscalation)

@router.post('/api/internal-tickets/{id}/escalations', response_model=EscalationResponse, status_code=201)
def escalation_create(id: RootId, payload: EscalationCreate, session: DBSession):
    return escalations.create_escalation(session, id, payload.model_dump(), Ticket=InternalTicket, **ESC_CONTEXT)

@router.patch('/api/internal-tickets/{id}/escalations/{escalation_id}', response_model=EscalationResponse)
def escalation_patch(id: RootId, escalation_id: Annotated[int, Path(gt=0)], payload: EscalationEdit, session: DBSession):
    return escalations.change_escalation(session, id, escalation_id, payload.model_dump(exclude_unset=True), **ESC_CONTEXT)

@router.post('/api/internal-tickets/{id}/escalations/{escalation_id}/finish', response_model=EscalationResponse)
def escalation_finish(id: RootId, escalation_id: Annotated[int, Path(gt=0)], session: DBSession, payload: EscalationFinish = EscalationFinish()):
    return escalations.finish_escalation(session, id, escalation_id, payload.model_dump(exclude_unset=True), **ESC_CONTEXT)

@router.get('/api/internal-tickets/{id}/escalations/{escalation_id}/audit', response_model=list[EscalationAuditResponse])
def escalation_audit(id: RootId, escalation_id: Annotated[int, Path(gt=0)], session: DBSession):
    item = get_or_404(session, InternalEscalation, escalation_id)
    if item.ticket_id != id:
        from fastapi import HTTPException
        raise HTTPException(404, 'Escalamiento no encontrado en este ticket')
    return list(session.scalars(select(InternalEscalationAudit).where(InternalEscalationAudit.escalation_id == escalation_id).order_by(InternalEscalationAudit.id)))


@router.get('/api/internal-tickets/{id}/reports/internal/pdf')
def individual_report(id: RootId, session: DBSession, options: Annotated[TicketReportOptions, Query()]):
    return report_response(session, id, options, 'internal', renderer=internal_ticket_pdf,
                           filename=f'Ticket_Interno_{id}.pdf')
