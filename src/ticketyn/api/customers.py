from typing import Annotated

from fastapi import APIRouter, Path, Query, Response

from ticketyn.api.crud import DBSession, delete_unreferenced, get_or_404, list_items, save_item, update_item
from ticketyn.models import Circuit, Customer, Ticket
from ticketyn.schemas.customer import CustomerCreate, CustomerResponse, CustomerUpdate

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.post("", response_model=CustomerResponse, status_code=201)
def create_customer(payload: CustomerCreate, session: DBSession):
    return save_item(session, Customer(**payload.model_dump()))


@router.get("", response_model=list[CustomerResponse])
def list_customers(
    session: DBSession,
    search: str | None = None,
    include_inactive: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return list_items(
        session, Customer, search=search, search_fields=('customer_code', 'name'),
        order_field="customer_code", include_inactive=include_inactive,
        limit=limit, offset=offset,
    )


@router.get("/{id}", response_model=CustomerResponse)
def get_customer(id: Annotated[int, Path(gt=0)], session: DBSession):
    return get_or_404(session, Customer, id)


@router.patch("/{id}", response_model=CustomerResponse)
def patch_customer(id: Annotated[int, Path(gt=0)], payload: CustomerUpdate, session: DBSession):
    item = get_or_404(session, Customer, id)
    values = payload.model_dump(exclude_unset=True)
    return update_item(session, item, values)


@router.delete("/{id}", status_code=204, response_class=Response)
def delete_customer(id: Annotated[int, Path(gt=0)], session: DBSession):
    delete_unreferenced(session, Customer, id, dependent_columns=(Circuit.customer_id, Ticket.customer_id),
        conflict_detail="No se puede eliminar el cliente porque tiene circuitos o tickets asociados. Puedes desactivarlo en lugar de eliminarlo.")
    return Response(status_code=204)
