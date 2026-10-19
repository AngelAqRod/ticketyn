"""Operational review controls, no send/requeue endpoint and no invented auth."""
from typing import Literal
from fastapi import HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func
from ticketyn.api.crud import DBSession
from ticketyn.api.mail_notifications import router
from ticketyn.models.mail_jobs import MailNotificationRequest
from ticketyn.notifications.requests import ACTIVE, TERMINAL, control_row


class ResumeProcessor(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    revision: int = Field(gt=0)
    confirmation: Literal['REANUDAR']


def processor_status(session, control):
    counts = dict(session.execute(select(MailNotificationRequest.state, func.count()).group_by(MailNotificationRequest.state)).all())
    return {'paused': control.paused, 'reason': control.reason, 'revision': control.revision,
            'counts': {state: counts.get(state, 0) for state in sorted(ACTIVE | TERMINAL)}}


@router.get('/processor')
def get_processor(session: DBSession):
    control = control_row(session)
    result = processor_status(session, control)
    session.commit()
    return result


@router.get('/requests')
def list_requests(session: DBSession, state: Literal['PENDING','PREPARING','SENDING','ACCEPTED','FAILED','PARTIAL','UNCERTAIN','CANCELLED'] | None = None,
                  limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    statement = select(MailNotificationRequest)
    if state is not None: statement = statement.where(MailNotificationRequest.state == state)
    rows = session.scalars(statement.order_by(MailNotificationRequest.requested_at, MailNotificationRequest.id).limit(limit).offset(offset))
    fields = ('id', 'event_key', 'activation_id', 'state', 'source', 'revision', 'error_code', 'created_at', 'requested_at', 'preparing_at', 'sending_at', 'finished_at')
    return [{field: getattr(row, field) for field in fields} for row in rows]


@router.post('/processor/pause')
def pause_processor(session: DBSession):
    control = control_row(session)
    control.paused = True; control.reason = 'MANUAL'; control.revision += 1
    session.flush(); result = processor_status(session, control); session.commit()
    return result


@router.post('/processor/resume')
def resume_processor(payload: ResumeProcessor, session: DBSession):
    control = control_row(session)
    if control.revision != payload.revision:
        raise HTTPException(409, 'El estado cambió; revisa las solicitudes antes de reanudar.')
    if session.scalar(select(MailNotificationRequest.id).where(MailNotificationRequest.state.in_({'PREPARING', 'SENDING'})).limit(1)):
        raise HTTPException(409, 'Hay solicitudes iniciadas; espera a su finalización o recuperación antes de reanudar.')
    control.paused = False; control.reason = 'AUTHORIZED'; control.revision += 1
    session.flush(); result = processor_status(session, control); session.commit()
    return result
