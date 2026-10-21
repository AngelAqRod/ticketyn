from typing import Annotated

from fastapi import APIRouter, Path, Query, HTTPException, Request
from sqlalchemy import select

from ticketyn.api.crud import DBSession, get_or_404, filtered_items, save_item, update_item
from ticketyn.models import Responsible, Department, Position
from ticketyn.schemas.responsible import ResponsibleCreate, ResponsibleResponse, ResponsibleUpdate

router = APIRouter(prefix="/api/responsibles", tags=["responsibles"])


def operational_view(session, item, actor):
    """Expose an action capability without exposing account metadata to selectors."""
    from ticketyn.security.roles import authorize_account_change
    allowed = 'catalogs.responsibles.edit' in actor.permissions
    if allowed and item.username:
        try:
            authorize_account_change(session, actor, item)
        except HTTPException as error:
            if error.status_code != 403:
                raise
            allowed = False
    data = ResponsibleResponse.model_validate(item).model_dump()
    data['can_change_active'] = allowed
    return data


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
def create_responsible(payload: ResponsibleCreate, session: DBSession, request: Request):
    values = payload.model_dump()
    validate_assignment(session, values)
    item = save_item(session, Responsible(**values))
    return operational_view(session, item, request.state.principal)


@router.get("", response_model=list[ResponsibleResponse])
def list_responsibles(
    session: DBSession,
    request: Request,
    search: str | None = None,
    include_inactive: bool = False,
    operational_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    query = filtered_items(
        Responsible, search=search, search_fields=('name',),
        order_field="name", include_inactive=include_inactive,
    )
    if operational_only:
        query = query.where(Responsible.operational_selectable.is_(True), Responsible.active.is_(True))
    return [operational_view(session, item, request.state.principal)
            for item in session.scalars(query.limit(limit).offset(offset))]


@router.get("/{id}", response_model=ResponsibleResponse)
def get_responsible(id: Annotated[int, Path(gt=0)], session: DBSession, request: Request):
    return operational_view(session, get_or_404(session, Responsible, id), request.state.principal)


@router.patch("/{id}", response_model=ResponsibleResponse)
def patch_responsible(id: Annotated[int, Path(gt=0)], payload: ResponsibleUpdate, session: DBSession, request: Request):
    from ticketyn.security.service import lock_security, change_operational_status
    lock_security(session)
    item = session.scalar(select(Responsible).where(Responsible.id == id).with_for_update(of=Responsible))
    if item is None:
        raise HTTPException(404, 'Responsable no encontrado')
    values = payload.model_dump(exclude_unset=True)
    if 'operational_selectable' in values and values['operational_selectable'] != item.operational_selectable:
        from ticketyn.security.service import audit
        audit(session, 'RESPONSIBLE_AVAILABILITY_CHANGED', item.id, request.state.principal.id,
              details={'before': item.operational_selectable, 'after': values['operational_selectable']})
    validate_assignment(session, values, item)
    if 'active' in values:
        change_operational_status(session, item, values.pop('active'), request.state.principal.id)
    item = update_item(session, item, values)
    return operational_view(session, item, request.state.principal)
