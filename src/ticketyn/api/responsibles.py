from typing import Annotated

from fastapi import APIRouter, Path, Query, HTTPException
from sqlalchemy import select

from ticketyn.api.crud import DBSession, get_or_404, list_items, save_item, update_item
from ticketyn.models import Responsible, Department, Position
from ticketyn.schemas.responsible import ResponsibleCreate, ResponsibleResponse, ResponsibleUpdate

router = APIRouter(prefix="/api/responsibles", tags=["responsibles"])


def validate_assignment(session, values, item=None):
    department_id = values.get('department_id', item.department_id if item else None)
    position_id = values.get('position_id', item.position_id if item else None)
    if department_id is not None and (item is None or department_id != item.department_id):
        department = session.scalar(select(Department).where(Department.id == department_id).with_for_update(read=True))
        if department is None:
            raise HTTPException(404, 'Departamento no encontrado')
        if not department.active:
            raise HTTPException(422, 'El departamento está inactivo')
    if position_id is not None:
        position = session.scalar(select(Position).where(Position.id == position_id).with_for_update(read=True, of=Position))
        if position is None:
            raise HTTPException(404, 'Puesto no encontrado')
        if position.department_id != department_id:
            raise HTTPException(422, 'El puesto no pertenece al departamento seleccionado')
        if (item is None or position_id != item.position_id) and not position.active:
            raise HTTPException(422, 'El puesto está inactivo')


@router.post("", response_model=ResponsibleResponse, status_code=201)
def create_responsible(payload: ResponsibleCreate, session: DBSession):
    values = payload.model_dump()
    validate_assignment(session, values)
    return save_item(session, Responsible(**values))


@router.get("", response_model=list[ResponsibleResponse])
def list_responsibles(
    session: DBSession,
    search: str | None = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return list_items(
        session, Responsible, search=search, search_fields=('name',),
        order_field="name", include_inactive=include_inactive,
        limit=limit, offset=offset,
    )


@router.get("/{id}", response_model=ResponsibleResponse)
def get_responsible(id: Annotated[int, Path(gt=0)], session: DBSession):
    return get_or_404(session, Responsible, id)


@router.patch("/{id}", response_model=ResponsibleResponse)
def patch_responsible(id: Annotated[int, Path(gt=0)], payload: ResponsibleUpdate, session: DBSession):
    item = session.scalar(select(Responsible).where(Responsible.id == id).with_for_update(of=Responsible))
    if item is None:
        raise HTTPException(404, 'Responsable no encontrado')
    values = payload.model_dump(exclude_unset=True)
    validate_assignment(session, values, item)
    return update_item(session, item, values)
