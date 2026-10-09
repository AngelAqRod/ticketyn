from typing import Annotated
from fastapi import APIRouter, Path, Query
from ticketyn.api.crud import DBSession, get_or_404
from ticketyn.api.escalation_data import create_escalation, finish_escalation, list_escalations
from ticketyn.models import Ticket
from ticketyn.schemas.escalation import EscalationCreate, EscalationResponse

router = APIRouter(prefix='/api/tickets', tags=['escalations'])


@router.post('/{id}/escalations', response_model=EscalationResponse, status_code=201)
def create(id: Annotated[int, Path(gt=0)], payload: EscalationCreate, session: DBSession):
    return create_escalation(session, id, payload.model_dump())


@router.get('/{id}/escalations', response_model=list[EscalationResponse])
def history(id: Annotated[int, Path(gt=0)], session: DBSession,
            limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Annotated[int, Query(ge=0)] = 0):
    get_or_404(session, Ticket, id)
    return list_escalations(session, id, newest_first=True, limit=limit, offset=offset)


@router.post('/{id}/escalations/{escalation_id}/finish', response_model=EscalationResponse)
def finish(id: Annotated[int, Path(gt=0)], escalation_id: Annotated[int, Path(gt=0)], session: DBSession):
    return finish_escalation(session, id, escalation_id)
