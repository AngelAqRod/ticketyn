"""One controlled worker across processes, with independent short transactions.

The advisory lock is session-scoped on an AUTOCOMMIT connection: no database
transaction spans SMTP. Losing the lock never authorizes retrying ambiguous mail.
"""
from contextlib import contextmanager
from threading import Event, Thread
import logging
import secrets
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text, func
from sqlalchemy.orm import Session
from ticketyn.core.secret_store import SecretError
from ticketyn.models.mail_jobs import MailNotificationRequest
from ticketyn.models.mail_notifications import MailEventConfig
from ticketyn.models.fms import Activation
from ticketyn.api.fms_data import operation_query
from ticketyn.api.reports import read_snapshot
from ticketyn.notifications.coordination import reserve_transport, release_test, locked_transport
from ticketyn.notifications.delivery import transport_settings, transport_credentials
from ticketyn.notifications.requests import control_row, recover_interrupted, transition
from ticketyn.notifications.smtp import build_message, send_message, MailFailure
from ticketyn.notifications.templates import render_template
from ticketyn.schemas.mail_templates import MailTemplate

LOCK_KEY = 7806001
logger = logging.getLogger(__name__)


@contextmanager
def processor_lock(engine):
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        acquired = connection.scalar(text('SELECT pg_try_advisory_lock(:key)'), {'key': LOCK_KEY})
        try:
            yield connection if acquired else None
        finally:
            if acquired:
                try: connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': LOCK_KEY})
                except Exception: connection.invalidate()


def owns_lock(connection):
    return connection.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE locktype='advisory' AND pid=pg_backend_pid() AND classid=0 AND objid=:key AND granted)"), {'key': LOCK_KEY})


def permitted(job, event):
    return event is not None and event.mode != 'DISABLED' and (job.source == 'MANUAL' or event.mode == 'AUTOMATIC')


class NotificationProcessor:
    def __init__(self, engine):
        self.engine = engine
        self.stopping = Event()
        self.thread = None

    def start(self):
        self.thread = Thread(target=self.run, name='ticketyn-mail-processor', daemon=True)
        self.thread.start()

    def stop(self):
        self.stopping.set()
        if self.thread is not None: self.thread.join(timeout=30)

    def run(self):
        while not self.stopping.is_set():
            try: worked = self.run_once()
            except Exception:
                # Never log SQL parameters, SMTP/provider diagnostics or content.
                logger.warning('Notification processor unavailable; no automatic SMTP retry.')
                worked = False
            self.stopping.wait(1 if worked else 2)

    def owned_job(self, session, identity):
        id, revision, token = identity
        return session.scalar(select(MailNotificationRequest).where(MailNotificationRequest.id == id, MailNotificationRequest.revision == revision, MailNotificationRequest.owner_token == token).with_for_update().execution_options(populate_existing=True))

    def finish(self, identity, state, error=None):
        with Session(self.engine) as session:
            control = control_row(session)
            job = self.owned_job(session, identity)
            if job is not None:
                transition(job, state, error); control.revision += 1
            session.commit()
            if job is not None:
                logger.info('Notification request %s revision %s state %s code %s', identity[0], identity[1], state, error or 'NONE')

    def defer(self, identity):
        with Session(self.engine) as session:
            control = control_row(session); job = self.owned_job(session, identity)
            if job is not None and job.state == 'PREPARING':
                transition(job, 'PENDING'); job.owner_token = None; job.preparing_at = None; control.revision += 1
            session.commit()

    def render(self, identity):
        with Session(self.engine) as session:
            read_snapshot(session)
            job = session.get(MailNotificationRequest, identity[0])
            event = session.get(MailEventConfig, job.event_key)
            if event is None or event.template is None:
                raise MailFailure('CONFIGURATION_ERROR')
            template = MailTemplate.model_validate(event.template)
            activation = session.scalar(operation_query(Activation).where(Activation.id == job.activation_id))
            if activation is None: raise MailFailure('CONFIGURATION_ERROR')
            content = render_template(session, job.event_key, template, activation)
            if not content.subject.strip() and not content.body.strip():
                raise MailFailure('CONFIGURATION_ERROR')
            return content, list(event.to_recipients), list(event.cc_recipients), list(event.bcc_recipients)

    def run_once(self):
        with processor_lock(self.engine) as connection:
            if connection is None: return False
            with Session(self.engine) as session:
                control = control_row(session)
                recover_interrupted(session, control)
                if control.paused:
                    session.commit(); return False
                job = session.scalar(select(MailNotificationRequest).where(MailNotificationRequest.state == 'PENDING').order_by(MailNotificationRequest.requested_at, MailNotificationRequest.id).with_for_update(skip_locked=True).limit(1))
                if job is None:
                    session.commit(); return False
                if not permitted(job, session.get(MailEventConfig, job.event_key)):
                    transition(job, 'CANCELLED', 'MODE_CHANGED'); control.revision += 1
                    session.commit(); return True
                transition(job, 'PREPARING'); job.owner_token = secrets.token_urlsafe(32); job.preparing_at = func.clock_timestamp(); control.revision += 1
                session.flush(); identity = (job.id, job.revision, job.owner_token)
                session.commit()
            lease = None
            sending = False
            try:
                content, to, cc, bcc = self.render(identity)
                with Session(self.engine) as session:
                    try:
                        row, lease = reserve_transport(session)
                        settings = transport_settings(row)
                        message, sender, recipients = build_message(sender_email=row.sender_email, sender_name=row.sender_name, to=to, cc=cc, bcc=bcc, subject=content.subject, body=content.body)
                        credentials = transport_credentials(row)
                        session.commit()
                    except MailFailure as error:
                        if error.status == 'AUTH_ERROR' and row.auth_method.startswith('OAUTH2'):
                            row.oauth_status = 'AUTH_ERROR'; session.commit()
                        raise
                # Recheck pause/mode and ownership immediately before the durable
                # SMTP boundary. Updates can cancel PREPARING without racing this.
                with Session(self.engine) as session:
                    control = control_row(session); job = self.owned_job(session, identity)
                    if job is None:
                        session.commit(); return True
                    if not permitted(job, session.get(MailEventConfig, job.event_key)):
                        transition(job, 'CANCELLED', 'MODE_CHANGED'); control.revision += 1; session.commit(); return True
                    if control.paused or self.stopping.is_set():
                        transition(job, 'PENDING'); job.owner_token = None; job.preparing_at = None; control.revision += 1; session.commit(); return False
                    if not owns_lock(connection):
                        raise MailFailure('CONNECTION_ERROR')
                    transition(job, 'SENDING'); job.sending_at = func.clock_timestamp(); control.revision += 1
                    identity = (job.id, job.revision, job.owner_token)
                    session.commit()
                sending = True
                result = send_message(settings, credentials, message, sender, recipients)
                state = {'ACCEPTED': 'ACCEPTED', 'PARTIAL_ACCEPTED': 'PARTIAL', 'UNCERTAIN': 'UNCERTAIN'}.get(result.status, 'FAILED')
                if result.status == 'AUTH_ERROR' and settings.auth_method.startswith('OAUTH2'):
                    with Session(self.engine) as session:
                        row = locked_transport(session); row.oauth_status = 'AUTH_ERROR'; session.commit()
                self.finish(identity, state, None if state == 'ACCEPTED' else result.status)
            except HTTPException as error:
                if error.status_code == 409 and not sending:
                    self.defer(identity); return False
                self.finish(identity, 'UNCERTAIN' if sending else 'FAILED', 'VALIDATION_ERROR')
            except MailFailure as error:
                self.finish(identity, 'UNCERTAIN' if error.status == 'UNCERTAIN' else 'FAILED', error.status)
            except (SecretError, ValidationError):
                self.finish(identity, 'FAILED', 'SECRET_OR_TEMPLATE_ERROR')
            except Exception:
                self.finish(identity, 'UNCERTAIN' if sending else 'FAILED', 'SMTP_INTERRUPTED' if sending else 'PREPARATION_ERROR')
            finally:
                if lease is not None:
                    try:
                        with Session(self.engine) as session: release_test(session, lease)
                    except Exception:
                        logger.warning('Notification transport lease cleanup unavailable; lease will expire.')
            return True
