from typing import Annotated
from fastapi import APIRouter, Path, Query, HTTPException
from sqlalchemy import select
from ticketyn.api.crud import DBSession, get_or_404, list_items, save_item, update_item
from ticketyn.models import Position, Department
from ticketyn.schemas.position import PositionCreate, PositionUpdate, PositionResponse

router = APIRouter(prefix='/api/positions', tags=['positions'])


def validate_department(session, id):
    item = session.scalar(select(Department).where(Department.id == id).with_for_update(read=True))
    if item is None:
        raise HTTPException(404, 'Departamento no encontrado')
    if not item.active:
        raise HTTPException(422, 'El departamento está inactivo')


@router.post('', response_model=PositionResponse, status_code=201)
def create_position(payload: PositionCreate, session: DBSession):
    validate_department(session, payload.department_id)
    return save_item(session, Position(**payload.model_dump()))


@router.get('', response_model=list[PositionResponse])
def positions(session: DBSession, search: str | None = None, include_inactive: bool = False,
              department_id: Annotated[int | None, Query(gt=0)] = None,
              limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Annotated[int, Query(ge=0)] = 0):
    return list_items(session, Position, search=search, search_fields=('name',), order_field='name',
                      include_inactive=include_inactive, limit=limit, offset=offset, department_id=department_id)


@router.get('/{id}', response_model=PositionResponse)
def position(id: Annotated[int, Path(gt=0)], session: DBSession):
    return get_or_404(session, Position, id)


@router.patch('/{id}', response_model=PositionResponse)
def patch_position(id: Annotated[int, Path(gt=0)], payload: PositionUpdate, session: DBSession):
    item = session.scalar(select(Position).where(Position.id == id).with_for_update(of=Position))
    if item is None:
        raise HTTPException(404, 'Puesto no encontrado')
    values = payload.model_dump(exclude_unset=True)
    if 'department_id' in values and values['department_id'] != item.department_id:
        validate_department(session, values['department_id'])
    return update_item(session, item, values)
