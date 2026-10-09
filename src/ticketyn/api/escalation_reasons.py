from typing import Annotated
from fastapi import APIRouter, Path, Query
from ticketyn.api.crud import DBSession, get_or_404, list_items, save_item, update_item
from ticketyn.models import EscalationReason
from ticketyn.schemas.escalation import ReasonCreate, ReasonUpdate, ReasonResponse

router = APIRouter(prefix='/api/escalation-reasons', tags=['escalation-reasons'])


@router.post('', response_model=ReasonResponse, status_code=201)
def create_reason(payload: ReasonCreate, session: DBSession):
    return save_item(session, EscalationReason(**payload.model_dump()))


@router.get('', response_model=list[ReasonResponse])
def reasons(session: DBSession, search: str | None = None, include_inactive: bool = False,
            limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Annotated[int, Query(ge=0)] = 0):
    return list_items(session, EscalationReason, search=search, search_fields=('name',), order_field='name',
                      include_inactive=include_inactive, limit=limit, offset=offset)


@router.get('/{id}', response_model=ReasonResponse)
def reason(id: Annotated[int, Path(gt=0)], session: DBSession):
    return get_or_404(session, EscalationReason, id)


@router.patch('/{id}', response_model=ReasonResponse)
def patch_reason(id: Annotated[int, Path(gt=0)], payload: ReasonUpdate, session: DBSession):
    return update_item(session, get_or_404(session, EscalationReason, id), payload.model_dump(exclude_unset=True))
