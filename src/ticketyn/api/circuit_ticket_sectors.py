"""Atomic, bounded corrections of recent customer-ticket sector snapshots."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import insert, literal, select, update, func
from sqlalchemy.orm import Session
from ticketyn.models import Sector, Ticket, TicketUpdate


def correction_time(session: Session) -> datetime:
    # Wall clock after acquiring the circuit lock, not transaction-start NOW().
    return session.scalar(select(func.clock_timestamp())).astimezone(timezone.utc)


def synchronize_recent_ticket_sectors(session: Session, circuit_id: int, sector: Sector) -> None:
    corrected_at = correction_time(session)
    tickets, sectors, history = Ticket.__table__, Sector.__table__, TicketUpdate.__table__
    eligible = (
        select(tickets.c.id, sectors.c.name.label('previous_sector'))
        .join(sectors, sectors.c.id == tickets.c.sector_id)
        .where(tickets.c.circuit_id == circuit_id,
               tickets.c.created_at >= corrected_at - timedelta(hours=168),
               tickets.c.created_at <= corrected_at,
               tickets.c.sector_id != sector.id)
        .order_by(tickets.c.id)
        # Ticket edits lock ticket before circuit; fail atomically rather than
        # wait in the opposite order or silently skip an eligible locked row.
        .with_for_update(of=tickets, nowait=True)
        .cte('eligible_ticket_sectors')
    )
    corrected = (
        update(tickets).where(tickets.c.id == eligible.c.id)
        .values(sector_id=sector.id, updated_at=tickets.c.updated_at)
        .returning(tickets.c.id.label('ticket_id'), eligible.c.previous_sector)
        .cte('corrected_ticket_sectors')
    )
    message = (literal('Sector actualizado automáticamente de «') + corrected.c.previous_sector
               + literal('» a «') + literal(sector.name)
               + literal('» por modificación del circuito asociado.'))
    # Update and evidence are one SQL statement; commit belongs to circuit save.
    session.execute(insert(history).from_select(
        ['ticket_id', 'content', 'occurred_at', 'created_at', 'responsible_id', 'escalation_id', 'visibility'],
        select(corrected.c.ticket_id, message, literal(corrected_at), literal(corrected_at),
               literal(None), literal(None), literal('INTERNAL')),
    ))
