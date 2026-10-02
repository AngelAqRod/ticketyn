from fastapi import APIRouter

from ticketyn.api.crud import DBSession, save_item, update_item
from ticketyn.api.ticket_numbers import locked_number_config, validate_number_config
from ticketyn.schemas.ticket_number_config import TicketNumberConfigResponse, TicketNumberConfigUpdate

router = APIRouter(prefix="/api/settings/ticket-number", tags=["ticket-number"])


@router.get("", response_model=TicketNumberConfigResponse)
def get_ticket_number_config(session: DBSession):
    return save_item(session, locked_number_config(session))


@router.patch("", response_model=TicketNumberConfigResponse)
def patch_ticket_number_config(payload: TicketNumberConfigUpdate, session: DBSession):
    config = locked_number_config(session)
    values = payload.model_dump(exclude_unset=True)
    try:
        validate_number_config(session, config, values)
    except Exception:
        session.rollback()
        raise
    return update_item(session, config, values)
