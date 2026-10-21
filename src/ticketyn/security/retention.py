"""Bounded security-audit retention. Never touches operational histories.

Only completed batches commit. A dedicated transaction advisory lock serializes
batches across processes; the configuration SHARE lock orders policy updates
against deletion. Neither lock is held between batches.
"""
import asyncio
import logging
import time
from datetime import timedelta, timezone
from threading import Event

from fastapi import HTTPException
from sqlalchemy import delete, func, select, text

from ticketyn.models.security import SecurityAudit, SecurityConfig
from ticketyn.security.service import audit, lock_security, principal


logger = logging.getLogger(__name__)
LOCK_KEY = 7807004  # Dedicated to audit retention; independent of SMTP locks.
BATCH_SIZE = 500
PASS_SECONDS = 30
DAILY_SECONDS = 86400
RETRY_SECONDS = 300


def require_superadmin(actor):
    if actor is None or actor.role != 'SUPERADMIN' or 'security.configure' not in actor.permissions:
        raise HTTPException(403, 'Solo el Superadministrador puede configurar la conservación')


def checked_days(config):
    if config is None or type(config.audit_retention_days) is not int or not 1 <= config.audit_retention_days <= 3650:
        # Never guess a destructive cutoff from a corrupt/unprepared setting.
        raise HTTPException(503, 'La conservación de auditoría no está disponible')
    return config.audit_retention_days


def retention_days(session, actor):
    require_superadmin(actor)
    return checked_days(session.get(SecurityConfig, 1))


def update_retention(session, actor, payload):
    require_superadmin(actor)
    config = lock_security(session)
    # Recheck authority after taking the same lock used by role/access changes.
    require_superadmin(principal(session, actor.id))
    before = checked_days(config)
    if payload.expected_days != before:
        raise HTTPException(409, 'La conservación cambió. Actualiza el valor antes de guardar')
    if payload.retention_days < before and not payload.confirm_reduction:
        raise HTTPException(422, 'Confirma la reducción del período de conservación')
    if before != payload.retention_days:
        config.audit_retention_days = payload.retention_days
        audit(session, 'AUDIT_RETENTION_CHANGED', actor_id=actor.id,
              details={'before_days': before, 'after_days': payload.retention_days})
    return config.audit_retention_days


def clean_batch(session_factory, *, now=None):
    """Return deleted count, or None if another process owns this batch.

    Production uses PostgreSQL's UTC-aware wall clock. Tests may inject a fixed
    aware instant. Exactly-at-cutoff records are retained (strictly less than).
    Each call owns and closes its session, transaction, and locks.
    """
    with session_factory() as session:
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        session.execute(text("SET LOCAL lock_timeout = '250ms'"))
        if not session.scalar(select(func.pg_try_advisory_xact_lock(LOCK_KEY))):
            return None
        config = session.scalar(select(SecurityConfig).where(SecurityConfig.id == 1).with_for_update(read=True))
        days = checked_days(config)
        instant = now if now is not None else session.scalar(select(func.clock_timestamp()))
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError('La fecha de conservación requiere zona horaria')
        cutoff = instant.astimezone(timezone.utc) - timedelta(days=days)
        expired = select(SecurityAudit.id).where(SecurityAudit.occurred_at < cutoff).order_by(
            SecurityAudit.occurred_at, SecurityAudit.id).limit(BATCH_SIZE)
        count = session.execute(delete(SecurityAudit).where(SecurityAudit.id.in_(expired)),
                                execution_options={'synchronize_session': False}).rowcount
        session.commit()
        return count


class AuditRetentionMaintenance:
    """Minute checks, daily passes; no persisted jobs or manual cleanup API.

    Restart reevaluates expiry after one minute. PostgreSQL serializes deletion,
    even if a second process is started accidentally; RAM sessions still require
    one HTTP worker. No connection or transaction survives a batch.
    """
    def __init__(self, session_factory, *, clock=time.monotonic):
        self.session_factory = session_factory
        self.clock = clock
        self.next_due = 0.0
        self.stopping = Event()
        self.running = False

    def run_pass(self):
        deadline = self.clock() + PASS_SECONDS
        try:
            # Secondary bound also prevents unlimited batches with a frozen clock.
            for _ in range(60):
                if self.stopping.is_set():
                    return 60
                count = clean_batch(self.session_factory)
                if count is None:
                    return RETRY_SECONDS
                if count < BATCH_SIZE:
                    return DAILY_SECONDS
                if self.clock() >= deadline:
                    return 60
            return 60
        except Exception:
            # Do not log SQL exceptions, parameters, identities, or metadata.
            logger.warning('No se pudo completar la conservación de auditoría; se evaluará nuevamente')
            return RETRY_SECONDS

    async def tick(self):
        if self.running or self.stopping.is_set() or self.clock() < self.next_due:
            return
        self.running = True
        worker = asyncio.create_task(asyncio.to_thread(self.run_pass))
        try:
            delay = await asyncio.shield(worker)
            self.next_due = self.clock() + delay
        except asyncio.CancelledError:
            self.stopping.set()
            # Connection/pool/SQL timeouts bound the current batch. Do not detach
            # a thread that might keep deleting after lifespan shutdown.
            await asyncio.shield(worker)
            raise
        finally:
            self.running = False
