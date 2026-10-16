from typing import Annotated

from fastapi import APIRouter, Path, Query

from ticketyn.api.crud import DBSession, get_or_404, list_items, save_item, update_item
from ticketyn.models import Provider
from ticketyn.schemas.internal_ticket import ProviderCreate, ProviderResponse, ProviderPatch

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.post("", response_model=ProviderResponse, status_code=201)
def create_provider(payload: ProviderCreate, session: DBSession):
    return save_item(session, Provider(**payload.model_dump()))


@router.get("", response_model=list[ProviderResponse])
def list_providers(
    session: DBSession,
    search: str | None = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return list_items(
        session, Provider, search=search, search_fields=('name',),
        order_field="name", include_inactive=include_inactive,
        limit=limit, offset=offset,
    )


@router.get("/{id}", response_model=ProviderResponse)
def get_provider(id: Annotated[int, Path(gt=0)], session: DBSession):
    return get_or_404(session, Provider, id)


@router.patch("/{id}", response_model=ProviderResponse)
def patch_provider(id: Annotated[int, Path(gt=0)], payload: ProviderPatch, session: DBSession):
    item = get_or_404(session, Provider, id)
    values = payload.model_dump(exclude_unset=True)
    return update_item(session, item, values)
