from typing import Annotated

from fastapi import APIRouter, Path, Query

from ticketyn.api.crud import DBSession, get_or_404, list_items, save_item, update_item
from ticketyn.models import Service
from ticketyn.schemas.service import ServiceCreate, ServiceResponse, ServiceUpdate

router = APIRouter(prefix="/api/services", tags=["services"])


@router.post("", response_model=ServiceResponse, status_code=201)
def create_service(payload: ServiceCreate, session: DBSession):
    return save_item(session, Service(**payload.model_dump()))


@router.get("", response_model=list[ServiceResponse])
def list_services(
    session: DBSession,
    search: str | None = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return list_items(
        session, Service, search=search, search_fields=('name',),
        order_field="name", include_inactive=include_inactive,
        limit=limit, offset=offset,
    )


@router.get("/{id}", response_model=ServiceResponse)
def get_service(id: Annotated[int, Path(gt=0)], session: DBSession):
    return get_or_404(session, Service, id)


@router.patch("/{id}", response_model=ServiceResponse)
def patch_service(id: Annotated[int, Path(gt=0)], payload: ServiceUpdate, session: DBSession):
    item = get_or_404(session, Service, id)
    values = payload.model_dump(exclude_unset=True)
    return update_item(session, item, values)
