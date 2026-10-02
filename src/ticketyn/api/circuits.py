from typing import Annotated

from fastapi import APIRouter, Path, Query

from ticketyn.api.crud import DBSession, get_or_404, list_items, save_item, update_item
from ticketyn.models import Circuit, Customer
from ticketyn.schemas.circuit import CircuitCreate, CircuitResponse, CircuitUpdate

router = APIRouter(prefix="/api/circuits", tags=["circuits"])


@router.post("", response_model=CircuitResponse, status_code=201)
def create_circuit(payload: CircuitCreate, session: DBSession):
    get_or_404(session, Customer, payload.customer_id)
    return save_item(session, Circuit(**payload.model_dump()))


@router.get("", response_model=list[CircuitResponse])
def list_circuits(
    session: DBSession,
    search: str | None = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    customer_id: Annotated[int | None, Query(gt=0)] = None,
):
    return list_items(
        session, Circuit, search=search, search_fields=('circuit_code', 'description'),
        order_field="circuit_code", include_inactive=include_inactive,
        limit=limit, offset=offset, customer_id=customer_id,
    )


@router.get("/{id}", response_model=CircuitResponse)
def get_circuit(id: Annotated[int, Path(gt=0)], session: DBSession):
    return get_or_404(session, Circuit, id)


@router.patch("/{id}", response_model=CircuitResponse)
def patch_circuit(id: Annotated[int, Path(gt=0)], payload: CircuitUpdate, session: DBSession):
    item = get_or_404(session, Circuit, id)
    values = payload.model_dump(exclude_unset=True)
    if "customer_id" in values:
        get_or_404(session, Customer, values["customer_id"])
    return update_item(session, item, values)
