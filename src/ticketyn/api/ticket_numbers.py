from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ticketyn.models import Ticket, TicketNumberConfig


def locked_number_config(session: Session) -> TicketNumberConfig:
    """Inicializar sin carreras y bloquear hasta commit/rollback del llamador."""
    session.execute(
        insert(TicketNumberConfig).values(id=1).on_conflict_do_nothing(index_elements=["id"])
    )
    return session.scalars(
        select(TicketNumberConfig).where(TicketNumberConfig.id == 1)
        .with_for_update().execution_options(populate_existing=True)
    ).one()


def format_reference(prefix: str, separator: str, number: int, padding: int) -> str:
    return f"{prefix}{separator}{str(number).zfill(padding)}"


def validate_number_config(session: Session, config: TicketNumberConfig, changes: dict) -> None:
    number = changes.get("next_number", config.next_number)
    highest = session.scalar(select(func.max(Ticket.ticket_number)))
    if highest is not None and number <= highest:
        raise HTTPException(status_code=409, detail="next_number debe ser mayor que todos los números ya asignados")
    reference = format_reference(
        changes.get("prefix", config.prefix), changes.get("separator", config.separator),
        number, changes.get("padding", config.padding),
    )
    if session.scalar(select(Ticket.id).where(or_(
        Ticket.ticket_number == number, Ticket.reference == reference
    )).limit(1)) is not None:
        raise HTTPException(status_code=409, detail="La configuración produciría una referencia o número existente")
