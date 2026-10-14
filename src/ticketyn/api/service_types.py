from typing import Annotated

from fastapi import APIRouter, Path, Query

from ticketyn.api.crud import DBSession, get_or_404, list_items, save_item, update_item
from ticketyn.models import ServiceType
from ticketyn.schemas.service_type import ServiceTypeCreate, ServiceTypeResponse, ServiceTypeUpdate

router = APIRouter(prefix="/api/service-types", tags=["service-types"])


@router.post("", response_model=ServiceTypeResponse, status_code=201)
def create_service_type(payload: ServiceTypeCreate, session: DBSession):
    return save_item(session, ServiceType(**payload.model_dump()))


@router.get("", response_model=list[ServiceTypeResponse])
def list_service_types(
    session: DBSession,
    search: str | None = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return list_items(
        session, ServiceType, search=search, search_fields=('name',),
        order_field="name", include_inactive=include_inactive,
        limit=limit, offset=offset,
    )


@router.get("/{id}", response_model=ServiceTypeResponse)
def get_service_type(id: Annotated[int, Path(gt=0)], session: DBSession):
    return get_or_404(session, ServiceType, id)


@router.patch("/{id}", response_model=ServiceTypeResponse)
def patch_service_type(id: Annotated[int, Path(gt=0)], payload: ServiceTypeUpdate, session: DBSession):
    item = get_or_404(session, ServiceType, id)
    values = payload.model_dump(exclude_unset=True)
    return update_item(session, item, values)
