"""Atomic, bounded corrections of recent customer-ticket node (HUB) snapshots."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, insert, literal, or_, select, update
from sqlalchemy.orm import Session
from ticketyn.models import Node, Ticket, TicketUpdate


def correction_time(session: Session) -> datetime:
    # Wall clock after acquiring the circuit lock, not transaction-start NOW().
    return session.scalar(select(func.clock_timestamp())).astimezone(timezone.utc)


def synchronize_recent_ticket_nodes(session: Session, circuit_id: int, node: Node) -> None:
    corrected_at = correction_time(session)
    tickets, nodes, history = Ticket.__table__, Node.__table__, TicketUpdate.__table__
    eligible = (
        select(tickets.c.id, func.coalesce(nodes.c.name, literal('Sin asignar')).label('previous_node'))
        .outerjoin(nodes, nodes.c.id == tickets.c.node_id)
        .where(
            tickets.c.circuit_id == circuit_id,
            tickets.c.created_at >= corrected_at - timedelta(hours=168),
            tickets.c.created_at <= corrected_at,
            or_(tickets.c.node_id.is_(None), tickets.c.node_id != node.id),
        )
        .order_by(tickets.c.id)
        # Ticket edits lock ticket before circuit; fail atomically rather than
        # wait in the opposite order or silently skip an eligible locked row.
        .with_for_update(of=tickets, nowait=True)
        .cte('eligible_ticket_nodes')
    )
    corrected = (
        update(tickets).where(tickets.c.id == eligible.c.id)
        .values(node_id=node.id, updated_at=tickets.c.updated_at)
        .returning(tickets.c.id.label('ticket_id'), eligible.c.previous_node)
        .cte('corrected_ticket_nodes')
    )
    message = (literal('Nodo actualizado automáticamente de «') + corrected.c.previous_node
               + literal('» a «') + literal(node.name)
               + literal('» por modificación del circuito asociado.'))
    # Update and evidence are one SQL statement; commit belongs to circuit save.
    session.execute(insert(history).from_select(
        ['ticket_id', 'content', 'occurred_at', 'created_at', 'responsible_id', 'escalation_id', 'visibility'],
        select(corrected.c.ticket_id, message, literal(corrected_at), literal(corrected_at),
               literal(None), literal(None), literal('INTERNAL')),
    ))
