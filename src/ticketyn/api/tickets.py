from typing import Annotated

from fastapi import APIRouter, Path, Query

from ticketyn.api import ticket_data
from ticketyn.api.crud import DBSession, get_or_404
from ticketyn.models import Ticket
from ticketyn.schemas.ticket import TicketCreate, TicketFilters, TicketResponse, TicketUpdate

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.post("", response_model=TicketResponse, status_code=201)
def create_ticket(payload: TicketCreate, session: DBSession):
    return ticket_data.create_ticket(session, payload.model_dump())


@router.get("", response_model=list[TicketResponse])
def list_tickets(session: DBSession, filters: Annotated[TicketFilters, Query()]):
    return ticket_data.list_tickets(session, filters.model_dump())


@router.get("/{id}", response_model=TicketResponse)
def get_ticket(id: Annotated[int, Path(gt=0)], session: DBSession):
    return get_or_404(session, Ticket, id)


@router.patch("/{id}", response_model=TicketResponse)
def patch_ticket(id: Annotated[int, Path(gt=0)], payload: TicketUpdate, session: DBSession):
    return ticket_data.patch_ticket(session, id, payload.model_dump(exclude_unset=True))
