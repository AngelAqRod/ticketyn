from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query, Request
from sqlalchemy import select
from ticketyn.security.mutations import ticket_mutation
from ticketyn.api.ticket_exports import export_ticket_pdf, export_ticket_xlsx, stream_ticket_export
from ticketyn.schemas.ticket_export import TicketExportFilters

from ticketyn.api import ticket_data
from ticketyn.api.crud import DBSession, get_or_404
from ticketyn.models import Ticket
from ticketyn.schemas.ticket import TicketCreate, TicketFilters, TicketListResponse, TicketResponse, TicketStats, TicketUpdate
from ticketyn.schemas.ticket_close import CustomerTicketClose
from ticketyn.api.ticket_close import close_ticket
from ticketyn.api.ticket_pdf_limits import ticket_pdf_export

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.post("", response_model=TicketListResponse, status_code=201)
def create_ticket(payload: TicketCreate, session: DBSession, request: Request):
    ticket_mutation(request.state.principal, 'tickets', payload.model_dump())
    ticket = ticket_data.create_ticket(session, payload.model_dump())
    return ticket_data.get_ticket(session, ticket.id)


@router.get("", response_model=list[TicketListResponse])
def list_tickets(session: DBSession, filters: Annotated[TicketFilters, Query()]):
    return ticket_data.list_tickets(session, filters.model_dump())


@router.get('/export/{format}')
def export_tickets(session: DBSession, request: Request, format: Literal['pdf', 'xlsx'], filters: Annotated[TicketExportFilters, Query()]):
    with ticket_pdf_export(request, format):
        return stream_ticket_export(session, format, filters, 'ticketyn-tickets',
                                    export_ticket_pdf if format == 'pdf' else export_ticket_xlsx)


@router.get("/stats", response_model=TicketStats)
def get_ticket_stats(session: DBSession):
    return ticket_data.ticket_stats(session)


@router.get("/{id}", response_model=TicketListResponse)
def get_ticket(id: Annotated[int, Path(gt=0)], session: DBSession):
    return ticket_data.get_ticket(session, id)


@router.patch("/{id}", response_model=TicketListResponse)
def patch_ticket(id: Annotated[int, Path(gt=0)], payload: TicketUpdate, session: DBSession, request: Request):
    item = session.scalar(select(Ticket).where(Ticket.id == id).with_for_update(of=Ticket))
    if item is not None:
        ticket_mutation(request.state.principal, 'tickets', payload.model_dump(exclude_unset=True), item)
    ticket = ticket_data.patch_ticket(session, id, payload.model_dump(exclude_unset=True))
    return ticket_data.get_ticket(session, ticket.id)


@router.post("/{id}/close", response_model=TicketListResponse)
def quick_close(id: Annotated[int, Path(gt=0)], payload: CustomerTicketClose, session: DBSession, request: Request):
    ticket = close_ticket(session, Ticket, id, payload, request.state.principal, 'tickets', ticket_data.patch_ticket)
    return ticket_data.get_ticket(session, ticket.id)
