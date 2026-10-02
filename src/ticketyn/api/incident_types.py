from typing import Annotated

from fastapi import APIRouter, Path, Query

from ticketyn.api.crud import DBSession, get_or_404, list_items, save_item, update_item
from ticketyn.models import IncidentType
from ticketyn.schemas.incident_type import IncidentTypeCreate, IncidentTypeResponse, IncidentTypeUpdate

router = APIRouter(prefix="/api/incident-types", tags=["incident-types"])


@router.post("", response_model=IncidentTypeResponse, status_code=201)
def create_incident_type(payload: IncidentTypeCreate, session: DBSession):
    return save_item(session, IncidentType(**payload.model_dump()))


@router.get("", response_model=list[IncidentTypeResponse])
def list_incident_types(
    session: DBSession,
    search: str | None = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return list_items(
        session, IncidentType, search=search, search_fields=('name',),
        order_field="name", include_inactive=include_inactive,
        limit=limit, offset=offset,
    )


@router.get("/{id}", response_model=IncidentTypeResponse)
def get_incident_type(id: Annotated[int, Path(gt=0)], session: DBSession):
    return get_or_404(session, IncidentType, id)


@router.patch("/{id}", response_model=IncidentTypeResponse)
def patch_incident_type(id: Annotated[int, Path(gt=0)], payload: IncidentTypeUpdate, session: DBSession):
    item = get_or_404(session, IncidentType, id)
    values = payload.model_dump(exclude_unset=True)
    return update_item(session, item, values)
