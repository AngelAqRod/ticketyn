"""Shared cross-process transport lease and test-only cooldown."""
from datetime import datetime, timezone, timedelta
import secrets
from fastapi import HTTPException
from sqlalchemy import select, update, func
from ticketyn.models.mail_notifications import MailTransportConfig


def locked_transport(session):
    row = session.scalar(select(MailTransportConfig).where(MailTransportConfig.id == 1).with_for_update().execution_options(populate_existing=True))
    if row is None:
        raise HTTPException(422, 'Guarda primero la configuración de correo.')
    return row


def ensure_idle(row):
    if row.test_lease_until and row.test_lease_until > datetime.now(timezone.utc):
        raise HTTPException(409, 'Ya hay una operación de correo en curso. Espera a que termine.')


def claim_test(session):
    row = locked_transport(session)
    ensure_idle(row)
    now = session.scalar(select(func.clock_timestamp()))
    if row.test_not_before and row.test_not_before > now:
        raise HTTPException(429, 'Espera 30 segundos entre pruebas de correo.', headers={'Retry-After': '30'})
    token = secrets.token_urlsafe(32)
    row.test_not_before = now + timedelta(seconds=30)
    row.test_lease_until = now + timedelta(minutes=10)
    row.test_lease_token = token
    return row, token


def release_test(session, token):
    session.execute(update(MailTransportConfig).where(MailTransportConfig.id == 1, MailTransportConfig.test_lease_token == token).values(test_lease_until=None, test_lease_token=None))
    session.commit()


def reserve_transport(session):
    """Share the test transport lease, without its test-only frequency limit."""
    row = locked_transport(session)
    ensure_idle(row)
    token = secrets.token_urlsafe(32)
    row.test_lease_until = session.scalar(select(func.clock_timestamp())) + timedelta(minutes=10)
    row.test_lease_token = token
    return row, token
