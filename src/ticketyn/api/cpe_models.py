from typing import Annotated

from fastapi import APIRouter, Path, Query

from ticketyn.api.crud import DBSession, get_or_404, list_items, save_item, update_item
from ticketyn.models import CpeModel
from ticketyn.schemas.cpe_model import CpeModelCreate, CpeModelResponse, CpeModelUpdate

router = APIRouter(prefix="/api/cpe-models", tags=["cpe-models"])


@router.post("", response_model=CpeModelResponse, status_code=201)
def create_cpe_model(payload: CpeModelCreate, session: DBSession):
    return save_item(session, CpeModel(**payload.model_dump()))


@router.get("", response_model=list[CpeModelResponse])
def list_cpe_models(
    session: DBSession,
    search: str | None = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return list_items(
        session, CpeModel, search=search, search_fields=('name',),
        order_field="name", include_inactive=include_inactive,
        limit=limit, offset=offset,
    )


@router.get("/{id}", response_model=CpeModelResponse)
def get_cpe_model(id: Annotated[int, Path(gt=0)], session: DBSession):
    return get_or_404(session, CpeModel, id)


@router.patch("/{id}", response_model=CpeModelResponse)
def patch_cpe_model(id: Annotated[int, Path(gt=0)], payload: CpeModelUpdate, session: DBSession):
    item = get_or_404(session, CpeModel, id)
    values = payload.model_dump(exclude_unset=True)
    return update_item(session, item, values)
