from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session, contains_eager

from ticketyn.api.crud import save_item
from ticketyn.api.ticket_numbers import format_reference, locked_number_config
from ticketyn.models import Circuit, Customer, Department, IncidentType, Sector, Ticket, Node, Responsible, TicketUpdate
from ticketyn.schemas.ticket import TicketListResponse, TicketResponse

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
    if "responsible_id" in changed_relations and values.get("responsible_id") is not None:
        responsible = session.scalar(select(Responsible).where(Responsible.id == values["responsible_id"]).with_for_update(read=True))
        if responsible is None:
            raise HTTPException(404, "El responsable indicado no existe")
        if not responsible.active:
            raise HTTPException(422, "El responsable indicado está inactivo")
    active_fields = set(changed_relations)
    if changed_relations & {"customer_id", "circuit_id"}:
        active_fields.update({"customer_id", "circuit_id"})
    validate_fields = active_fields | {"customer_id", "circuit_id"}
    selected = {}
    for field, model in RELATED_MODELS.items():
        if field not in validate_fields:
            continue
        # FOR SHARE mantiene activo y pertenencia estables durante la operación.
        item = session.scalar(select(model).where(model.id == values[field]).with_for_update(read=True, of=model))
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
        validate_ticket_values(session, values, set(RELATED_MODELS) | {"responsible_id"})
        if config.next_number >= 2147483647:
            raise HTTPException(status_code=409, detail="Se agotó el rango de numeración")
        ticket = Ticket(
            **values, ticket_number=config.next_number,
            reference=format_reference(config.prefix, config.separator, config.next_number, config.padding),
        )
        if ticket.resolution is not None:
            record_resolution_change(session, ticket, None, ticket.resolution)
        config.next_number += 1
        # save_item confirma tanto el ticket como el contador en una transacción.
        return save_item(session, ticket)
    except Exception:
        session.rollback()
        raise


def patch_ticket(session: Session, id: int, changes: dict) -> Ticket:
    try:
        ticket = session.scalar(select(Ticket).where(Ticket.id == id).with_for_update(of=Ticket))
        if ticket is None:
            raise HTTPException(status_code=404, detail=f"Ticket con id {id} no encontrado")
        current = {field: getattr(ticket, field) for field in (
            "title", "description", "responsible_id", *RELATED_MODELS, "start_at", "end_at", "status"
        )}
        changed_relations = {
            field for field in (*RELATED_MODELS, "responsible_id") if field in changes and changes[field] != current[field]
        }
        validate_ticket_values(session, {**current, **changes}, changed_relations)
        if "resolution" in changes and changes["resolution"] != ticket.resolution:
            record_resolution_change(session, ticket, ticket.resolution, changes["resolution"])
        for field, value in changes.items():
            setattr(ticket, field, value)
        return save_item(session, ticket)
    except Exception:
        session.rollback()
        raise


def ticket_statement(filters: dict, *, time_field: str = "start_at"):
    """Filtros y orden compartidos, sin paginación ni límite para futuros reportes."""
    if time_field not in {"start_at", "end_at"}:
        raise ValueError("Campo temporal no soportado")
    timestamp = getattr(Ticket, time_field)
    statement = select(Ticket)
    for field in ("status", "responsible_id", *RELATED_MODELS):
        if filters.get(field) is not None:
            statement = statement.where(getattr(Ticket, field) == filters[field])
    if filters.get("node_id") is not None:
        statement = statement.where(Ticket.circuit_id.in_(select(Circuit.id).where(Circuit.node_id == filters["node_id"])))
    if filters.get("search"):
        statement = statement.where(or_(
            *(getattr(Ticket, field).icontains(filters["search"], autoescape=True)
              for field in ("reference", "title", "description")),
            cast(Ticket.ticket_number, String).icontains(filters["search"], autoescape=True),
        ))
    if filters.get("from_at") is not None:
        statement = statement.where(timestamp >= filters["from_at"])
    if filters.get("to_at") is not None:
        statement = statement.where(timestamp < filters["to_at"])
    return statement.order_by(Ticket.created_at.desc(), Ticket.id.desc())


def joined_ticket_statement(filters: dict):
    statement = ticket_statement(filters).add_columns(*RELATED_MODELS.values())
    for field, model in RELATED_MODELS.items():
        statement = statement.join(model, getattr(Ticket, field) == model.id)
    # Reutilizar los joins existentes también para las relaciones ORM evita
    # consultas lazy y joins duplicados durante schemas/exportaciones.
    return statement.outerjoin(Node, Circuit.node_id == Node.id).outerjoin(
        Responsible, Ticket.responsible_id == Responsible.id
    ).options(
        contains_eager(Ticket.circuit).contains_eager(Circuit.node),
        contains_eager(Ticket.responsible), contains_eager(Circuit.node),
    )


def ticket_rows(session: Session, filters: dict):
    """Todos los resultados, sin paginación y sin lazy loading de catálogos."""
    return session.execute(joined_ticket_statement(filters).execution_options(yield_per=200))


def list_tickets(session: Session, filters: dict) -> list[TicketListResponse]:
    statement = joined_ticket_statement(filters)
    rows = session.execute(statement.limit(filters["limit"]).offset(filters["offset"]))
    return [ticket_response(row) for row in rows]


def ticket_response(row) -> TicketListResponse:
    ticket, customer, circuit, sector, department, incident_type = row
    return TicketListResponse(
        **TicketResponse.model_validate(ticket).model_dump(),
        customer=customer, circuit=circuit, sector=sector, department=department, incident_type=incident_type,
    )


def get_ticket(session: Session, id: int) -> TicketListResponse:
    row = session.execute(joined_ticket_statement({}).where(Ticket.id == id)).one_or_none()
    if row is None:
        raise HTTPException(404, f"Ticket con id {id} no encontrado")
    return ticket_response(row)


def record_resolution_change(session: Session, ticket: Ticket, previous: str | None, current: str | None):
    # Evidencia de cambios, no identidad del editor: todavía no hay usuarios/auth.
    # Se confirma en la misma transacción que el ticket. Siempre INTERNAL.
    session.add(TicketUpdate(ticket=ticket, visibility="INTERNAL", responsible_id=None,
        occurred_at=datetime.now(timezone.utc),
        content=f"Cambio de resolución documentada.\nAnterior: {previous if previous is not None else 'Sin resolución'}\nNueva: {current if current is not None else 'Sin resolución'}"))
