from fastapi import HTTPException
from sqlalchemy import func, select
from ticketyn.api.crud import save_item
from ticketyn.models import Ticket, Responsible, EscalationReason, TicketEscalation, Position, Department


def create_escalation(session, ticket_id, values):
    try:
        if session.scalar(select(Ticket.id).where(Ticket.id == ticket_id).with_for_update(read=True)) is None:
            raise HTTPException(404, 'Ticket no encontrado')
        people = {}
        # Stable lock order also when two requests reverse requester/recipient.
        for id in sorted({id for id in (values.get('requester_id'), values['recipient_id']) if id is not None}):
            item = session.scalar(select(Responsible).where(Responsible.id == id).with_for_update(read=True, of=Responsible))
            if item is None:
                raise HTTPException(404, 'Responsable no encontrado')
            if not item.active:
                raise HTTPException(422, 'El responsable está inactivo')
            people[id] = item
        reason = session.scalar(select(EscalationReason).where(EscalationReason.id == values['reason_id']).with_for_update(read=True))
        if reason is None:
            raise HTTPException(404, 'Motivo no encontrado')
        if not reason.active:
            raise HTTPException(422, 'El motivo está inactivo')
        recipient = people[values['recipient_id']]
        # Lock snapshot sources so a concurrent catalogue edit cannot mix names.
        position = session.scalar(select(Position).where(Position.id == recipient.position_id).with_for_update(read=True, of=Position).execution_options(populate_existing=True)) if recipient.position_id else None
        department = session.scalar(select(Department).where(Department.id == recipient.department_id).with_for_update(read=True).execution_options(populate_existing=True)) if recipient.department_id else None
        return save_item(session, TicketEscalation(ticket_id=ticket_id,
            recipient_position_name=position.name if position else None,
            recipient_department_name=department.name if department else None, **values))
    except Exception:
        session.rollback()
        raise


def finish_escalation(session, ticket_id, id):
    try:
        item = session.scalar(select(TicketEscalation).where(TicketEscalation.id == id,
            TicketEscalation.ticket_id == ticket_id).with_for_update(of=TicketEscalation))
        if item is None:
            raise HTTPException(404, 'Escalamiento no encontrado en este ticket')
        if item.status == 'ACTIVE':
            item.status = 'FINISHED'
            item.finished_at = func.clock_timestamp()
            return save_item(session, item)
        return item  # Idempotent; never rewrite the original completion timestamp.
    except Exception:
        session.rollback()
        raise


def list_escalations(session, ticket_id, *, newest_first=False, limit=None, offset=0):
    ordering = (TicketEscalation.created_at.desc(), TicketEscalation.id.desc()) if newest_first else (TicketEscalation.created_at, TicketEscalation.id)
    statement = select(TicketEscalation).where(TicketEscalation.ticket_id == ticket_id).order_by(*ordering)
    if limit is not None:
        statement = statement.limit(limit).offset(offset)
    return list(session.scalars(statement))
