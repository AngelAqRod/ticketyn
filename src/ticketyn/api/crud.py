from typing import Annotated, TypeVar

from fastapi import Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ticketyn.db.base import Base
from ticketyn.db.session import get_session

DBSession = Annotated[Session, Depends(get_session)]
Model = TypeVar("Model", bound=Base)

UNIQUE_ERRORS = {
    "uq_customers_customer_code": "Ya existe un cliente con ese customer_code",
    "uq_circuits_circuit_code": "Ya existe un circuito con ese circuit_code",
    "uq_sectors_name": "Ya existe un sector con ese name",
}


def get_or_404(session: Session, model: type[Model], id: int) -> Model:
    item = session.get(model, id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} con id {id} no encontrado")
    return item


def list_items(
    session: Session, model: type[Model], *, search: str | None,
    search_fields: tuple[str, ...], order_field: str, include_inactive: bool,
    limit: int, offset: int, customer_id: int | None = None,
) -> list[Model]:
    statement = select(model)
    if not include_inactive:
        statement = statement.where(model.active.is_(True))
    if search:
        statement = statement.where(or_(
            *(getattr(model, field).icontains(search, autoescape=True) for field in search_fields)
        ))
    if customer_id is not None:
        statement = statement.where(model.customer_id == customer_id)
    statement = statement.order_by(getattr(model, order_field), model.id).limit(limit).offset(offset)
    return list(session.scalars(statement))


def save_item(session: Session, item: Model) -> Model:
    session.add(item)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if constraint in UNIQUE_ERRORS:
            raise HTTPException(status_code=409, detail=UNIQUE_ERRORS[constraint]) from None
        if constraint == "fk_circuits_customer_id_customers":
            raise HTTPException(status_code=404, detail="El cliente indicado no existe") from None
        raise HTTPException(status_code=409, detail="Los datos incumplen una restricción de integridad") from None
    session.refresh(item)
    return item


def update_item(session: Session, item: Model, values: dict) -> Model:
    for field, value in values.items():
        setattr(item, field, value)
    return save_item(session, item)
