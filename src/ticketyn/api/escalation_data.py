from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from ticketyn.models import Ticket, Responsible, EscalationReason, TicketEscalation, Position, Department, EscalationAudit


def snapshot_destination(session, values, item=None):
    recipient_id = values.get('recipient_id', item.recipient_id if item else None)
    department_id = values.get('department_id', item.department_id if item else None)
    recipient = None
    if recipient_id is not None:
        recipient = session.scalar(select(Responsible).where(Responsible.id == recipient_id).with_for_update(read=True, of=Responsible).execution_options(populate_existing=True))
        if recipient is None:
            raise HTTPException(404, 'Responsable no encontrado')
        if not recipient.active:
            raise HTTPException(422, 'El responsable está inactivo')
        if department_id is None and item is None:
            department_id = recipient.department_id
    if department_id is None:
        raise HTTPException(422, 'Selecciona un departamento de destino')
    department = session.scalar(select(Department).where(Department.id == department_id).with_for_update(read=True))
    if department is None:
        raise HTTPException(404, 'Departamento no encontrado')
    if not department.active:
        raise HTTPException(422, 'El departamento está inactivo')
    if recipient and recipient.department_id != department_id:
        raise HTTPException(422, 'El destinatario no pertenece al departamento seleccionado')
    position = session.scalar(select(Position).where(Position.id == recipient.position_id).with_for_update(read=True, of=Position)) if recipient and recipient.position_id else None
    return dict(legacy_destination=False, recipient_id=recipient_id, department_id=department_id,
        recipient_department_name=department.name, recipient_position_name=position.name if position else None, recipient_level=None)


def audit(session, item, event, previous, model=EscalationAudit):
    def serial(value):
        return value.isoformat() if isinstance(value, datetime) else value
    fields = ('started_at', 'finished_at', 'department_id', 'recipient_id', 'recipient_department_name', 'recipient_position_name', 'recipient_level', 'status')
    changes = {key: {'before': serial(previous.get(key)), 'after': serial(getattr(item, key))}
               for key in fields if previous.get(key) != getattr(item, key)}
    session.add(model(escalation_id=item.id, event=event, actor=None, changes=changes))


def create_escalation(session, ticket_id, values, *, Ticket=Ticket, TicketEscalation=TicketEscalation, audit_model=EscalationAudit):
    try:
        if session.scalar(select(Ticket.id).where(Ticket.id == ticket_id).with_for_update(read=True)) is None:
            raise HTTPException(404, 'Ticket no encontrado')
        requester_id = values.get('requester_id')
        if requester_id is not None:
            requester = session.scalar(select(Responsible).where(Responsible.id == requester_id).with_for_update(read=True, of=Responsible))
            if requester is None:
                raise HTTPException(404, 'Responsable no encontrado')
            if not requester.active:
                raise HTTPException(422, 'El responsable está inactivo')
        destination = snapshot_destination(session, values)
        reason = session.scalar(select(EscalationReason).where(EscalationReason.id == values['reason_id']).with_for_update(read=True))
        if reason is None:
            raise HTTPException(404, 'Motivo no encontrado')
        if not reason.active:
            raise HTTPException(422, 'El motivo está inactivo')
        values = {**values, **destination}
        values['started_at'] = values.get('started_at') or datetime.now(timezone.utc)
        item = TicketEscalation(ticket_id=ticket_id, **values)
        session.add(item); session.flush()
        item.updated_at = item.created_at
        audit(session, item, 'created', {}, model=audit_model)
        session.commit(); session.refresh(item)
        return item
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Los datos del escalamiento incumplen una restricción de integridad') from None
    except Exception:
        session.rollback()
        raise


def change_escalation(session, ticket_id, id, values, *, finish=False, TicketEscalation=TicketEscalation, audit_model=EscalationAudit):
    try:
        item = session.scalar(select(TicketEscalation).where(TicketEscalation.id == id,
            TicketEscalation.ticket_id == ticket_id).with_for_update(of=TicketEscalation))
        if item is None:
            raise HTTPException(404, 'Escalamiento no encontrado en este ticket')
        if finish and item.status == 'FINISHED':
            return item
        fields = ('started_at', 'finished_at', 'department_id', 'recipient_id', 'recipient_department_name', 'recipient_position_name', 'recipient_level', 'status')
        previous = {key: getattr(item, key) for key in fields}
        if any(key in values and values[key] != getattr(item, key) for key in ('recipient_id', 'department_id')):
            values = {**values, **snapshot_destination(session, values, item)}
        if finish:
            values = {**values, 'finished_at': values.get('finished_at') or datetime.now(timezone.utc), 'status': 'FINISHED'}
        for key, value in values.items():
            setattr(item, key, value)
        if (item.status == 'ACTIVE' and item.finished_at is not None) or (item.status == 'FINISHED' and (item.finished_at is None or item.finished_at < item.started_at)):
            raise HTTPException(422, 'La finalización debe ser igual o posterior al inicio y solo corresponde a escalamientos finalizados')
        if any(previous[key] != getattr(item, key) for key in fields):
            item.updated_at = datetime.now(timezone.utc)
            audit(session, item, 'finished' if finish else 'updated', previous, model=audit_model)
            session.commit(); session.refresh(item)
        return item
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'Los datos del escalamiento incumplen una restricción de integridad') from None
    except Exception:
        session.rollback()
        raise


def finish_escalation(session, ticket_id, id, values=None, **context):
    return change_escalation(session, ticket_id, id, values or {}, finish=True, **context)


def list_escalations(session, ticket_id, *, newest_first=False, limit=None, offset=0, TicketEscalation=TicketEscalation):
    ordering = (TicketEscalation.started_at.desc(), TicketEscalation.id.desc()) if newest_first else (TicketEscalation.started_at, TicketEscalation.id)
    statement = select(TicketEscalation).where(TicketEscalation.ticket_id == ticket_id).order_by(*ordering)
    if limit is not None:
        statement = statement.limit(limit).offset(offset)
    return list(session.scalars(statement))
