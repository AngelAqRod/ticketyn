from typing import Annotated
from fastapi import APIRouter, Path, Query
from sqlalchemy import select
from ticketyn.api.crud import DBSession, get_or_404
from ticketyn.api.escalation_data import create_escalation, finish_escalation, list_escalations, change_escalation
from ticketyn.models import Ticket, TicketEscalation, EscalationAudit
from ticketyn.schemas.escalation import EscalationCreate, EscalationResponse, EscalationEdit, EscalationFinish, EscalationAuditResponse

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
def finish(id: Annotated[int, Path(gt=0)], escalation_id: Annotated[int, Path(gt=0)], session: DBSession, payload: EscalationFinish = EscalationFinish()):
    return finish_escalation(session, id, escalation_id, payload.model_dump(exclude_unset=True))


@router.patch('/{id}/escalations/{escalation_id}', response_model=EscalationResponse)
def edit(id: Annotated[int, Path(gt=0)], escalation_id: Annotated[int, Path(gt=0)], payload: EscalationEdit, session: DBSession):
    return change_escalation(session, id, escalation_id, payload.model_dump(exclude_unset=True))


@router.get('/{id}/escalations/{escalation_id}/audit', response_model=list[EscalationAuditResponse])
def history_audit(id: Annotated[int, Path(gt=0)], escalation_id: Annotated[int, Path(gt=0)], session: DBSession):
    item = get_or_404(session, TicketEscalation, escalation_id)
    if item.ticket_id != id:
        from fastapi import HTTPException
        raise HTTPException(404, 'Escalamiento no encontrado en este ticket')
    return list(session.scalars(select(EscalationAudit).where(EscalationAudit.escalation_id == escalation_id).order_by(EscalationAudit.id)))
