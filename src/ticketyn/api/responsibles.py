from typing import Annotated

from fastapi import APIRouter, Path, Query

from ticketyn.api.crud import DBSession, get_or_404, list_items, save_item, update_item
from ticketyn.models import Responsible
from ticketyn.schemas.responsible import ResponsibleCreate, ResponsibleResponse, ResponsibleUpdate

router = APIRouter(prefix="/api/responsibles", tags=["responsibles"])


@router.post("", response_model=ResponsibleResponse, status_code=201)
def create_responsible(payload: ResponsibleCreate, session: DBSession):
    return save_item(session, Responsible(**payload.model_dump()))


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
    item = get_or_404(session, Responsible, id)
    values = payload.model_dump(exclude_unset=True)
    return update_item(session, item, values)
