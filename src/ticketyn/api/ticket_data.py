from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ticketyn.api.crud import save_item
from ticketyn.api.ticket_numbers import format_reference, locked_number_config
from ticketyn.models import Circuit, Customer, Department, IncidentType, Sector, Ticket

RELATED_MODELS = {
    "customer_id": Customer,
    "circuit_id": Circuit,
    "sector_id": Sector,
    "department_id": Department,
    "incident_type_id": IncidentType,
}


def ticket_stats(session: Session) -> dict[str, int]:
    row = session.execute(select(
        func.count(Ticket.id).label("total"),
        func.count(Ticket.id).filter(Ticket.status == "OPEN").label("open"),
        func.count(Ticket.id).filter(Ticket.status == "CLOSED").label("closed"),
    )).one()
    return dict(row._mapping)


def validate_ticket_values(session: Session, values: dict, changed_relations: set[str]) -> None:
    if values["end_at"] is not None and values["end_at"] < values["start_at"]:
        raise HTTPException(status_code=422, detail="end_at debe ser igual o posterior a start_at")
    active_fields = set(changed_relations)
    if changed_relations & {"customer_id", "circuit_id"}:
        active_fields.update({"customer_id", "circuit_id"})
    validate_fields = active_fields | {"customer_id", "circuit_id"}
    selected = {}
    for field, model in RELATED_MODELS.items():
        if field not in validate_fields:
            continue
        # FOR SHARE mantiene activo y pertenencia estables durante la operación.
        item = session.scalar(select(model).where(model.id == values[field]).with_for_update(read=True))
        if item is None:
            raise HTTPException(status_code=404, detail=f"{model.__name__} con id {values[field]} no encontrado")
        if field in active_fields and not item.active:
            raise HTTPException(status_code=422, detail=f"{model.__name__} con id {values[field]} está inactivo")
        selected[field] = item
    if "circuit_id" in selected and selected["circuit_id"].customer_id != values["customer_id"]:
        raise HTTPException(status_code=422, detail="El circuito no pertenece al cliente seleccionado")


def create_ticket(session: Session, values: dict) -> Ticket:
    try:
        config = locked_number_config(session)
        validate_ticket_values(session, values, set(RELATED_MODELS))
        if config.next_number >= 2147483647:
            raise HTTPException(status_code=409, detail="Se agotó el rango de numeración")
        ticket = Ticket(
            **values, ticket_number=config.next_number,
            reference=format_reference(config.prefix, config.separator, config.next_number, config.padding),
        )
        config.next_number += 1
        # save_item confirma tanto el ticket como el contador en una transacción.
        return save_item(session, ticket)
    except Exception:
        session.rollback()
        raise


def patch_ticket(session: Session, id: int, changes: dict) -> Ticket:
    try:
        ticket = session.scalar(select(Ticket).where(Ticket.id == id).with_for_update())
        if ticket is None:
            raise HTTPException(status_code=404, detail=f"Ticket con id {id} no encontrado")
        current = {field: getattr(ticket, field) for field in (
            "title", "description", *RELATED_MODELS, "start_at", "end_at", "status"
        )}
        changed_relations = {
            field for field in RELATED_MODELS if field in changes and changes[field] != current[field]
        }
        validate_ticket_values(session, {**current, **changes}, changed_relations)
        for field, value in changes.items():
            setattr(ticket, field, value)
        return save_item(session, ticket)
    except Exception:
        session.rollback()
        raise


def list_tickets(session: Session, filters: dict) -> list[Ticket]:
    statement = select(Ticket)
    for field in ("status", *RELATED_MODELS):
        if filters[field] is not None:
            statement = statement.where(getattr(Ticket, field) == filters[field])
    if filters["search"]:
        statement = statement.where(or_(
            *(getattr(Ticket, field).icontains(filters["search"], autoescape=True)
              for field in ("reference", "title", "description"))
        ))
    statement = statement.order_by(Ticket.created_at.desc(), Ticket.id.desc())
    return list(session.scalars(statement.limit(filters["limit"]).offset(filters["offset"])))
