"""Quick-close preconditions; persistence remains in the existing ticket lifecycle."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select

from ticketyn.security.mutations import ticket_mutation


def close_ticket(session, model, id, payload, actor, module, persist):
    try:
        ticket = session.scalar(select(model).where(model.id == id).with_for_update(of=model)
                                .execution_options(populate_existing=True))
        if ticket is None:
            raise HTTPException(404, 'Ticket no encontrado')
        if ticket.status != 'OPEN' or ticket.updated_at != payload.expected_updated_at:
            raise HTTPException(409, 'El ticket cambió o ya está cerrado. Recarga la ficha antes de intentar cerrarlo.')
        now = datetime.now(timezone.utc)
        end_at = payload.end_at or now
        if end_at < ticket.start_at:
            raise HTTPException(422, 'La fecha de cierre debe ser igual o posterior a la apertura.')
        if end_at > now:
            raise HTTPException(422, 'La fecha de cierre no puede estar en el futuro.')
        changes = payload.model_dump(exclude_unset=True, exclude={'expected_updated_at', 'end_at'})
        changes.update(status='CLOSED', end_at=end_at)
        ticket_mutation(actor, module, changes, ticket)
        return persist(session, id, changes)
    except Exception:
        session.rollback()
        raise
