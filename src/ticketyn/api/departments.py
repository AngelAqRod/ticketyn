from typing import Annotated

from fastapi import APIRouter, Path, Query

from ticketyn.api.crud import DBSession, get_or_404, list_items, save_item, update_item
from ticketyn.models import Department
from ticketyn.schemas.department import DepartmentCreate, DepartmentResponse, DepartmentUpdate

router = APIRouter(prefix="/api/departments", tags=["departments"])


@router.post("", response_model=DepartmentResponse, status_code=201)
def create_department(payload: DepartmentCreate, session: DBSession):
    return save_item(session, Department(**payload.model_dump()))


@router.get("", response_model=list[DepartmentResponse])
def list_departments(
    session: DBSession,
    search: str | None = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return list_items(
        session, Department, search=search, search_fields=('name',),
        order_field="name", include_inactive=include_inactive,
        limit=limit, offset=offset,
    )


@router.get("/{id}", response_model=DepartmentResponse)
def get_department(id: Annotated[int, Path(gt=0)], session: DBSession):
    return get_or_404(session, Department, id)


@router.patch("/{id}", response_model=DepartmentResponse)
def patch_department(id: Annotated[int, Path(gt=0)], payload: DepartmentUpdate, session: DBSession):
    item = get_or_404(session, Department, id)
    values = payload.model_dump(exclude_unset=True)
    return update_item(session, item, values)
