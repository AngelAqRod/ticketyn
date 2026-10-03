from tempfile import SpooledTemporaryFile
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from ticketyn.api.reports import read_snapshot
from ticketyn.api.ticket_exports import export_ticket_pdf, export_ticket_xlsx
from ticketyn.schemas.ticket_export import TicketExportFilters

from ticketyn.api import ticket_data
from ticketyn.api.crud import DBSession, get_or_404
from ticketyn.models import Ticket
from ticketyn.schemas.ticket import TicketCreate, TicketFilters, TicketListResponse, TicketResponse, TicketStats, TicketUpdate

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.post("", response_model=TicketListResponse, status_code=201)
def create_ticket(payload: TicketCreate, session: DBSession):
    ticket = ticket_data.create_ticket(session, payload.model_dump())
    return ticket_data.get_ticket(session, ticket.id)


@router.get("", response_model=list[TicketListResponse])
def list_tickets(session: DBSession, filters: Annotated[TicketFilters, Query()]):
    return ticket_data.list_tickets(session, filters.model_dump())


@router.get('/export/{format}')
def export_tickets(session: DBSession, format: Literal['pdf', 'xlsx'], filters: Annotated[TicketExportFilters, Query()]):
    read_snapshot(session)
    output = SpooledTemporaryFile(max_size=2 * 1024 * 1024)
    try:
        (export_ticket_pdf if format == 'pdf' else export_ticket_xlsx)(session, filters, output)
        output.seek(0)
    except Exception:
        output.close()
        raise
    def chunks():
        try:
            while chunk := output.read(65536): yield chunk
        finally:
            output.close()
    media = 'application/pdf' if format == 'pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    return StreamingResponse(chunks(), media_type=media,
        headers={'Content-Disposition': f'attachment; filename="ticketyn-tickets.{format}"'},
        background=BackgroundTask(output.close))


@router.get("/stats", response_model=TicketStats)
def get_ticket_stats(session: DBSession):
    return ticket_data.ticket_stats(session)


@router.get("/{id}", response_model=TicketListResponse)
def get_ticket(id: Annotated[int, Path(gt=0)], session: DBSession):
    return ticket_data.get_ticket(session, id)


@router.patch("/{id}", response_model=TicketListResponse)
def patch_ticket(id: Annotated[int, Path(gt=0)], payload: TicketUpdate, session: DBSession):
    ticket = ticket_data.patch_ticket(session, id, payload.model_dump(exclude_unset=True))
    return ticket_data.get_ticket(session, ticket.id)
