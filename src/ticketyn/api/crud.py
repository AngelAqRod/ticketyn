from typing import Annotated, TypeVar

from fastapi import Depends, HTTPException
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from ticketyn.db.base import Base
from ticketyn.db.session import get_session

DBSession = Annotated[Session, Depends(get_session)]
Model = TypeVar("Model", bound=Base)

UNIQUE_ERRORS = {
    "uq_nodes_name": "Ya existe un nodo con ese name",
    "uq_responsibles_name": "Ya existe un responsable con ese name",
    "uq_customers_customer_code": "Ya existe un cliente con ese customer_code",
    "uq_circuits_circuit_code": "Ya existe un circuito con ese circuit_code",
    "uq_sectors_name": "Ya existe un sector con ese name",
    "uq_departments_name": "Ya existe un departamento con ese name",
    "uq_incident_types_name": "Ya existe un tipo de incidencia con ese name",
    "uq_tickets_ticket_number": "Conflicto de numeración: ticket_number ya existe",
    "uq_tickets_reference": "Conflicto de numeración: reference ya existe",
}


def get_or_404(session: Session, model: type[Model], id: int) -> Model:
    item = session.get(model, id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} con id {id} no encontrado")
    return item


def filtered_items(
    model: type[Model], *, search: str | None, search_fields: tuple[str, ...],
    order_field: str, include_inactive: bool, customer_id: int | None = None,
    active: bool | None = None, node_id: int | None = None,
):
    """Query reutilizable antes de paginar. active explícito prevalece sobre include_inactive."""
    statement = select(model)
    if active is not None:
        statement = statement.where(model.active.is_(active))
    elif not include_inactive:
        statement = statement.where(model.active.is_(True))
    if search:
        statement = statement.where(or_(
            *(getattr(model, field).icontains(search, autoescape=True) for field in search_fields)
        ))
    if customer_id is not None:
        statement = statement.where(model.customer_id == customer_id)
    if node_id is not None:
        statement = statement.where(model.node_id == node_id)
    return statement.order_by(getattr(model, order_field), model.id)


def list_items(
    session: Session, model: type[Model], *, search: str | None,
    search_fields: tuple[str, ...], order_field: str, include_inactive: bool,
    limit: int, offset: int, customer_id: int | None = None, active: bool | None = None, node_id: int | None = None,
) -> list[Model]:
    statement = filtered_items(model, search=search, search_fields=search_fields, order_field=order_field,
                               include_inactive=include_inactive, customer_id=customer_id, active=active, node_id=node_id)
    return list(session.scalars(statement.limit(limit).offset(offset)))


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
        if constraint and constraint.startswith("fk_tickets_"):
            raise HTTPException(status_code=404, detail="Un recurso relacionado no existe") from None
        if constraint and constraint.startswith("ck_tickets_"):
            raise HTTPException(status_code=422, detail="Los datos del ticket no son válidos") from None
        raise HTTPException(status_code=409, detail="Los datos incumplen una restricción de integridad") from None
    session.refresh(item)
    return item


def update_item(session: Session, item: Model, values: dict) -> Model:
    for field, value in values.items():
        setattr(item, field, value)
    return save_item(session, item)


def delete_unreferenced(session: Session, model: type[Model], id: int, *, dependent_columns: tuple, conflict_detail: str) -> None:
    """Lock the parent, check references, and let FK constraints arbitrate races.

    A SQL DELETE deliberately avoids ORM relationship nullification or cascades.
    PostgreSQL FK writers take a conflicting parent lock: committed references
    are checked after acquiring ours, and late inserts cannot become orphans.
    """
    try:
        if session.scalar(select(model.id).where(model.id == id).with_for_update()) is None:
            raise HTTPException(404, f"{model.__name__} con id {id} no encontrado")
        if any(session.scalar(select(select(column).where(column == id).exists())) for column in dependent_columns):
            raise HTTPException(409, conflict_detail)
        session.execute(delete(model).where(model.id == id).execution_options(synchronize_session=False))
        session.commit()
    except HTTPException:
        session.rollback()
        raise
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, conflict_detail) from None
    except OperationalError as error:
        session.rollback()
        if getattr(error.orig, 'sqlstate', None) in {'40001', '40P01', '55P03'}:
            raise HTTPException(409, 'Conflicto concurrente. Vuelve a intentar la eliminación.') from None
        raise
