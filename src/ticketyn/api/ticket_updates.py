from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from ticketyn.api.crud import DBSession
from ticketyn.api.ticket_update_data import create_update, list_updates, page_updates
from ticketyn.schemas.ticket_update import TicketUpdateCreate, TicketUpdateResponse, TicketUpdatePage

router = APIRouter(prefix="/api/tickets", tags=["ticket-updates"])


@router.get("/{id}/updates", response_model=list[TicketUpdateResponse] | TicketUpdatePage)
def get_updates(id: Annotated[int, Path(gt=0)], session: DBSession,
                limit: Annotated[int | None, Query(ge=1, le=100)] = None,
                cursor: Annotated[str | None, Query(max_length=1024)] = None,
                escalation_id: Annotated[int | None, Query(gt=0)] = None):
    # Sin parámetros se conserva la respuesta histórica (lista completa ascendente).
    if limit is None:
        if cursor is not None:
            raise HTTPException(422, "El cursor requiere limit")
        return list_updates(session, id, escalation_id)
    return page_updates(session, id, limit, cursor, escalation_id)


@router.post("/{id}/updates", response_model=TicketUpdateResponse, status_code=201)
def post_update(id: Annotated[int, Path(gt=0)], payload: TicketUpdateCreate, session: DBSession):
    return create_update(session, id, payload.model_dump())
