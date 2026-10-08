from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response

from sqlalchemy import select
from sqlalchemy.orm import Session

from ticketyn.api.crud import DBSession, delete_unreferenced, get_or_404, list_items, save_item, update_item
from ticketyn.models import Circuit, Customer, Node, Ticket
from ticketyn.schemas.circuit import CircuitCreate, CircuitResponse, CircuitUpdate

router = APIRouter(prefix="/api/circuits", tags=["circuits"])


@router.post("", response_model=CircuitResponse, status_code=201)
def create_circuit(payload: CircuitCreate, session: DBSession):
    get_or_404(session, Customer, payload.customer_id)
    validate_node(session, payload.node_id)
    return save_item(session, Circuit(**payload.model_dump()))


@router.get("", response_model=list[CircuitResponse])
def list_circuits(
    session: DBSession,
    search: str | None = None,
    include_inactive: bool = False,
    active: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    node_id: Annotated[int | None, Query(gt=0)] = None,
    customer_id: Annotated[int | None, Query(gt=0)] = None,
):
    return list_items(
        session, Circuit, search=search, search_fields=('circuit_code', 'description'),
        order_field="circuit_code", include_inactive=include_inactive,
        limit=limit, offset=offset, customer_id=customer_id, active=active, node_id=node_id,
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
    if "node_id" in values and values["node_id"] != item.node_id:
        validate_node(session, values["node_id"])
    return update_item(session, item, values)


def validate_node(session: Session, node_id: int | None) -> None:
    if node_id is None:
        return
    node = session.scalar(select(Node).where(Node.id == node_id).with_for_update(read=True))
    if node is None:
        raise HTTPException(404, "El nodo indicado no existe")
    if not node.active:
        raise HTTPException(422, "El nodo indicado está inactivo")


@router.delete("/{id}", status_code=204, response_class=Response)
def delete_circuit(id: Annotated[int, Path(gt=0)], session: DBSession):
    delete_unreferenced(session, Circuit, id, dependent_columns=(Ticket.circuit_id,),
        conflict_detail="No se puede eliminar el circuito porque tiene tickets asociados. Puedes desactivarlo en lugar de eliminarlo.")
    return Response(status_code=204)
