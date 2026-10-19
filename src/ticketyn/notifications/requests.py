"""Transactional request API. Callers own commits; no SMTP or message storage."""
from fastapi import HTTPException
from sqlalchemy import select, text, func
from sqlalchemy.dialects.postgresql import insert
from ticketyn.models.mail_jobs import MailProcessorControl, MailNotificationRequest
from ticketyn.models.mail_notifications import MailEventConfig
from ticketyn.models.fms import Activation
from ticketyn.notifications.fields import ACTIVATION_EVENT

ACTIVE = {'PENDING', 'PREPARING', 'SENDING'}
TERMINAL = {'ACCEPTED', 'FAILED', 'PARTIAL', 'UNCERTAIN', 'CANCELLED'}
TRANSITIONS = {
    'PENDING': {'PREPARING', 'CANCELLED'},
    'PREPARING': {'SENDING', 'PENDING', 'FAILED', 'CANCELLED', 'UNCERTAIN'},
    'SENDING': {'ACCEPTED', 'FAILED', 'PARTIAL', 'UNCERTAIN'},
    **{state: {'PENDING'} for state in TERMINAL},
}


def transition(job, state, error_code=None):
    if state not in TRANSITIONS[job.state]:
        raise ValueError('Transición técnica de notificación no permitida')
    job.state = state; job.error_code = error_code; job.revision += 1
    if state in TERMINAL:
        job.owner_token = None; job.finished_at = func.clock_timestamp()


def quarantine(session, control, reason):
    jobs = session.scalars(select(MailNotificationRequest).where(MailNotificationRequest.state.in_({'PREPARING', 'SENDING'})).with_for_update())
    for job in jobs:
        transition(job, 'UNCERTAIN', 'RESTORED_INTERRUPTED')
    control.paused = True; control.reason = reason; control.revision += 1


def control_row(session):
    """Missing control data (excluded from backups) is always fail-closed."""
    created = session.scalar(insert(MailProcessorControl).values(id=1, reason='RESTORE_OR_INITIAL_SETUP').on_conflict_do_nothing(index_elements=['id']).returning(MailProcessorControl.id))
    row = session.scalar(select(MailProcessorControl).where(MailProcessorControl.id == 1).with_for_update().execution_options(populate_existing=True))
    oid = session.scalar(text('SELECT oid FROM pg_database WHERE datname=current_database()'))
    if created or (row.database_oid is not None and row.database_oid != oid):
        quarantine(session, row, 'RESTORE_OR_DATABASE_CHANGED')
    row.database_oid = oid
    return row


def request_notification(session, event_key, activation_id, *, automatic, expected_revision=None):
    """Coalesce active requests. Only explicit manual intent renews terminal rows.

    Automatic calls are idempotent forever and participate in the caller's
    business transaction; no commits or network I/O occur in this function.
    """
    if event_key != ACTIVATION_EVENT:
        raise HTTPException(422, 'El evento de notificación no está admitido.')
    control = control_row(session)
    event = session.scalar(select(MailEventConfig).where(MailEventConfig.event_key == event_key).with_for_update())
    if automatic and (event is None or event.mode != 'AUTOMATIC'):
        return None
    if event is None or event.mode == 'DISABLED':
        raise HTTPException(422, 'El evento de notificación está desactivado.')
    if session.get(Activation, activation_id) is None:
        raise HTTPException(404, 'La activación no existe.')
    job = session.scalar(select(MailNotificationRequest).where(MailNotificationRequest.event_key == event_key, MailNotificationRequest.activation_id == activation_id).with_for_update().execution_options(populate_existing=True))
    if job is not None and (automatic or job.state in ACTIVE):
        if not automatic and job.state in {'PENDING', 'PREPARING'} and job.source == 'AUTOMATIC':
            # A deliberate manual request coalesces with the existing request,
            # but must survive switching the event from automatic to manual.
            job.source = 'MANUAL'; control.revision += 1
        return job
    observed = job.revision if job else 0
    if not automatic and (type(expected_revision) is not int or expected_revision != observed):
        raise HTTPException(409, 'La solicitud cambió; consulta su estado antes de solicitar otro envío.')
    if job is None:
        job = MailNotificationRequest(event_key=event_key, activation_id=activation_id, source='AUTOMATIC' if automatic else 'MANUAL', state='PENDING', revision=1)
        session.add(job)
    else:
        transition(job, 'PENDING'); job.source = 'MANUAL'
        job.requested_at = func.clock_timestamp(); job.preparing_at = None; job.sending_at = None; job.finished_at = None; job.owner_token = None
    control.revision += 1
    session.flush()
    return job


def cancel_unstarted(session, control, event_key, *, include_manual=False):
    statement = select(MailNotificationRequest).where(MailNotificationRequest.event_key == event_key, MailNotificationRequest.state.in_({'PENDING', 'PREPARING'}))
    if not include_manual:
        statement = statement.where(MailNotificationRequest.source == 'AUTOMATIC')
    jobs = session.scalars(statement.with_for_update())
    for job in jobs:
        transition(job, 'CANCELLED', 'MODE_CHANGED'); control.revision += 1


def recover_interrupted(session, control):
    """Caller MUST hold the cross-process processor lock, not just a lease."""
    jobs = session.scalars(select(MailNotificationRequest).where(MailNotificationRequest.state.in_({'PREPARING', 'SENDING'})).with_for_update())
    for job in jobs:
        if job.state == 'SENDING': transition(job, 'UNCERTAIN', 'SMTP_INTERRUPTED')
        else:
            transition(job, 'PENDING'); job.owner_token = None; job.preparing_at = None
        control.revision += 1
