import base64
import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from ticketyn.api.crud import get_or_404, save_item
from ticketyn.models import Responsible, Ticket, TicketUpdate


def list_updates(session: Session, ticket_id: int) -> list[TicketUpdate]:
    get_or_404(session, Ticket, ticket_id)
    return list(session.scalars(select(TicketUpdate).where(TicketUpdate.ticket_id == ticket_id)
                               .order_by(TicketUpdate.occurred_at, TicketUpdate.id)))


def create_update(session: Session, ticket_id: int, values: dict) -> TicketUpdate:
    try:
        # FOR SHARE conserva relaciones estables; no modifica el ticket.
        ticket = session.scalar(select(Ticket).where(Ticket.id == ticket_id)
                                .with_for_update(read=True, of=Ticket))
        if ticket is None:
            raise HTTPException(404, "El ticket indicado no existe")
        if values.get("responsible_id") is not None:
            responsible = session.scalar(select(Responsible).where(Responsible.id == values["responsible_id"])
                                         .with_for_update(read=True))
            if responsible is None:
                raise HTTPException(404, "El responsable indicado no existe")
            if not responsible.active:
                raise HTTPException(422, "El responsable indicado está inactivo")
        return save_item(session, TicketUpdate(ticket_id=ticket_id, **values))
    except Exception:
        session.rollback()
        raise


def page_updates(session: Session, ticket_id: int, limit: int, cursor: str | None):
    get_or_404(session, Ticket, ticket_id)
    statement = select(TicketUpdate).where(TicketUpdate.ticket_id == ticket_id)
    if cursor is not None:
        try:
            data = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
            if not isinstance(data, dict) or set(data) != {"ticket", "at", "id"}:
                raise ValueError()
            if type(data["ticket"]) is not int or data["ticket"] != ticket_id:
                raise ValueError()
            if type(data["id"]) is not int or data["id"] <= 0 or not isinstance(data["at"], str):
                raise ValueError()
            at = datetime.fromisoformat(data["at"])
            if at.tzinfo is None or at.utcoffset() is None:
                raise ValueError()
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise HTTPException(422, "Cursor de seguimiento inválido") from None
        statement = statement.where(tuple_(TicketUpdate.occurred_at, TicketUpdate.id) < tuple_(at, data["id"]))
    rows = list(session.scalars(statement.order_by(TicketUpdate.occurred_at.desc(), TicketUpdate.id.desc()).limit(limit + 1)))
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = base64.urlsafe_b64encode(json.dumps({"ticket": ticket_id, "at": last.occurred_at.isoformat(), "id": last.id}).encode()).decode()
    return {"items": rows[:limit], "next_cursor": next_cursor}
