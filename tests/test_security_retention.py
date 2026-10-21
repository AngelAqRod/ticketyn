"""Retention writes run only on the existing ephemeral PostgreSQL fixtures."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from threading import Event
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ticketyn.models import Responsible, Ticket, TicketUpdate
from ticketyn.models.security import SecurityAudit, SecurityConfig
from ticketyn.security import retention
from ticketyn.security.service import seed_foundation
from test_security_audit import ready, entries
from test_security_foundation import security_client
from test_security_authorization import account_role
from test_ticket_concurrency import concurrent_database


URL = '/api/security/audit/retention'
NOW = datetime(2026, 10, 20, 18, tzinfo=timezone.utc)


def change(client, days, expected=365, confirm=False):
    return client.patch(URL, json={'retention_days': days, 'expected_days': expected, 'confirm_reduction': confirm})


def test_default_persistence_no_inline_cleanup_and_transactional_event(security_client):
    client, app, factory, id = ready(security_client)
    token = client.headers['Authorization'][7:]
    activity = app.state.security.get(token).last_activity
    with factory() as session:
        old = SecurityAudit(event='LOGIN_FAILED_GROUP', occurred_at=NOW-timedelta(days=400))
        session.add(old); session.flush(); old_id = old.id; session.commit()
        before = (session.get(SecurityConfig, 1).idle_minutes, session.get(SecurityConfig, 1).failure_retention_days,
                  session.get(Responsible, id).access_revision)
    assert client.get(URL).json() == {'retention_days': 365}
    with patch.object(retention, 'clean_batch', side_effect=AssertionError('No HTTP cleanup')):
        assert change(client, 30, confirm=True).json() == {'retention_days': 30}
    assert client.get(URL).json() == {'retention_days': 30}
    row = entries(factory, 'AUDIT_RETENTION_CHANGED')[0]
    assert row.actor_id == id and row.target_id is None and row.details == {'before_days': 365, 'after_days': 30}
    assert client.get('/api/security/audit?event=AUDIT_RETENTION_CHANGED').json()['total'] == 1
    assert change(client, 30, expected=30).status_code == 200
    assert len(entries(factory, 'AUDIT_RETENTION_CHANGED')) == 1
    with factory() as session:
        assert session.get(SecurityAudit, old_id) is not None
        assert (session.get(SecurityConfig, 1).idle_minutes, session.get(SecurityConfig, 1).failure_retention_days,
                session.get(Responsible, id).access_revision) == before
    assert app.state.security.get(token).last_activity == activity


@pytest.mark.parametrize('value', [0, -1, 3651, 1.5, True, '365', None])
def test_strict_range_and_types(security_client, value):
    client, _, _, _ = ready(security_client)
    assert change(client, value).status_code == 422
    assert client.get(URL).json()['retention_days'] == 365


def test_limits_confirmation_stale_writes_and_unknown_fields(security_client):
    client, _, factory, _ = ready(security_client)
    assert change(client, 1).status_code == 422
    assert change(client, 1, confirm=True).status_code == 200
    assert change(client, 3650).status_code == 409
    assert change(client, 3650, expected=1).status_code == 200
    assert client.patch(URL, json={'retention_days': 365, 'expected_days': 3650, 'idle_minutes': 3}).status_code == 422
    assert len(entries(factory, 'AUDIT_RETENTION_CHANGED')) == 2


@pytest.mark.parametrize('role', ['ADMIN', 'OPERATOR', 'AUDITOR', 'CUSTOM'])
def test_only_superadmin_can_read_or_write_retention(security_client, role):
    client, _, factory, id = ready(security_client, role)
    if role == 'CUSTOM':
        account_role(factory, id, grants=['audit.view'])
    assert client.get(URL).status_code == 403
    assert change(client, 30, confirm=True).status_code == 403
    if role in {'ADMIN', 'CUSTOM'}:
        assert client.get('/api/security/audit').status_code == 200
    client.headers.pop('Authorization')
    assert client.get(URL).status_code == 401
    assert change(client, 30, confirm=True).status_code == 401


def test_audit_failure_rolls_back_retention_and_sanitizes_error(security_client, caplog):
    client, _, factory, _ = ready(security_client)
    with patch.object(retention, 'audit', side_effect=SQLAlchemyError('hidden-sensitive-value')):
        response = change(client, 30, confirm=True)
    assert response.status_code == 503
    assert 'hidden-sensitive-value' not in response.text + caplog.text
    assert client.get(URL).json()['retention_days'] == 365
    assert not entries(factory, 'AUDIT_RETENTION_CHANGED')


@pytest.fixture
def retention_db(concurrent_database):
    engine, payload = concurrent_database
    with Session(engine) as session:
        seed_foundation(session); session.commit()
    return engine, payload


def old_event(instant, event='LOGIN_SUCCEEDED'):
    return SecurityAudit(event=event, occurred_at=instant, source='HTTP', details={})


def test_expiry_strict_boundary_and_one_policy_for_failed_groups(retention_db):
    engine, _ = retention_db
    cutoff = NOW - timedelta(days=365)
    with Session(engine) as session:
        session.add_all([old_event(cutoff-timedelta(microseconds=1)), old_event(cutoff),
                         old_event(cutoff+timedelta(microseconds=1)), old_event(NOW-timedelta(days=8), 'LOGIN_FAILED_GROUP')])
        session.commit()
    assert retention.clean_batch(lambda: Session(engine), now=NOW) == 1
    with Session(engine) as session:
        remaining = list(session.scalars(select(SecurityAudit.occurred_at).order_by(SecurityAudit.occurred_at)))
        assert remaining == [cutoff, cutoff+timedelta(microseconds=1), NOW-timedelta(days=8)]


def test_batches_restart_and_operational_histories_untouched(retention_db):
    engine, payload = retention_db
    from ticketyn.api.ticket_data import create_ticket
    with Session(engine) as session:
        ticket = create_ticket(session, payload.copy())
        ticket_id = ticket.id
        session.add(TicketUpdate(ticket_id=ticket_id, content='Histórico intacto', occurred_at=NOW-timedelta(days=500)))
        session.add_all([old_event(NOW-timedelta(days=400)) for _ in range(1001)])
        session.commit()
        before = {table.name: session.scalar(select(func.count()).select_from(table)) for table in
                  SecurityAudit.metadata.sorted_tables if table.name != 'security_audit'}
    factory = lambda: Session(engine)
    assert retention.clean_batch(factory, now=NOW) == 500
    # New session/process can resume committed remaining batches after interruption.
    assert retention.clean_batch(factory, now=NOW) == 500
    assert retention.clean_batch(factory, now=NOW) == 1
    assert retention.clean_batch(factory, now=NOW) == 0
    with Session(engine) as session:
        assert session.get(Ticket, ticket_id) is not None
        assert session.scalars(select(TicketUpdate.content)).one() == 'Histórico intacto'
        assert before == {table.name: session.scalar(select(func.count()).select_from(table)) for table in
                          SecurityAudit.metadata.sorted_tables if table.name != 'security_audit'}


def test_advisory_lock_excludes_another_connection_and_recovers(retention_db):
    engine, _ = retention_db
    with Session(engine) as session:
        session.add(old_event(NOW-timedelta(days=400))); session.commit()
    with engine.begin() as owner:
        owner.execute(select(func.pg_advisory_xact_lock(retention.LOCK_KEY)))
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(retention.clean_batch, lambda: Session(engine), now=NOW).result(timeout=5) is None
    assert retention.clean_batch(lambda: Session(engine), now=NOW) == 1


def test_config_lock_prevents_deleting_with_obsolete_policy(retention_db):
    engine, _ = retention_db
    with Session(engine) as session:
        session.get(SecurityConfig, 1).audit_retention_days = 30
        session.add(old_event(NOW-timedelta(days=100))); session.commit()
    with Session(engine) as changing:
        config = changing.scalar(select(SecurityConfig).where(SecurityConfig.id == 1).with_for_update())
        config.audit_retention_days = 365
        # Cleaner times out rather than reading the old 30-day policy.
        with ThreadPoolExecutor(max_workers=1) as pool:
            with pytest.raises(SQLAlchemyError):
                pool.submit(retention.clean_batch, lambda: Session(engine), now=NOW).result(timeout=5)
        changing.commit()
    assert retention.clean_batch(lambda: Session(engine), now=NOW) == 0
    assert engine.pool.checkedout() == 0


def test_invalid_or_missing_config_fails_closed(retention_db, caplog):
    engine, _ = retention_db
    with Session(engine) as session:
        session.get(SecurityConfig, 1).audit_retention_days = 0
        session.add(old_event(NOW-timedelta(days=500))); session.commit()
    maintenance = retention.AuditRetentionMaintenance(lambda: Session(engine))
    assert maintenance.run_pass() == 300
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(SecurityAudit)) == 1
        session.delete(session.get(SecurityConfig, 1)); session.commit()
    assert maintenance.run_pass() == 300
    assert 'SELECT' not in caplog.text
    assert engine.pool.checkedout() == 0


def test_failed_batch_rolls_back_and_restart_retries_only_expired_rows(retention_db):
    engine, _ = retention_db
    with Session(engine) as session:
        session.add(old_event(NOW-timedelta(days=400))); session.commit()
    @contextmanager
    def failing_factory():
        with Session(engine) as session:
            with patch.object(session, 'commit', side_effect=SQLAlchemyError('private-secret')):
                yield session
    with pytest.raises(SQLAlchemyError):
        retention.clean_batch(failing_factory, now=NOW)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(SecurityAudit)) == 1
    assert retention.clean_batch(lambda: Session(engine), now=NOW) == 1
    assert engine.pool.checkedout() == 0


def test_simultaneous_cleaners_delete_each_row_only_once(retention_db):
    from threading import Barrier
    engine, _ = retention_db
    with Session(engine) as session:
        session.add_all(old_event(NOW-timedelta(days=400)) for _ in range(501)); session.commit()
    start = Barrier(2)
    def clean(_):
        start.wait(timeout=5)
        return retention.clean_batch(lambda: Session(engine), now=NOW)
    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(clean, range(2)))
    final = retention.clean_batch(lambda: Session(engine), now=NOW)
    assert sum(count or 0 for count in counts) + final == 501
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(SecurityAudit)) == 0


def test_retention_survives_application_restart(retention_db, monkeypatch):
    from ticketyn.core.config import get_settings
    from security_helpers import authenticate_test_client
    engine, _ = retention_db
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://unused:unused@127.0.0.1:1/unused')
    get_settings.cache_clear()
    from ticketyn.main import create_app
    try:
        for first in (True, False):
            app = create_app(start_notifications=False)
            with TestClient(app) as client:
                authenticate_test_client(app, client, engine)
                if first:
                    assert change(client, 730).status_code == 200
                assert client.get(URL).json() == {'retention_days': 730}
    finally:
        get_settings.cache_clear()


def test_scheduler_daily_continuations_failures_and_cancellation(monkeypatch, caplog):
    clock = [100.0]
    maintenance = retention.AuditRetentionMaintenance(lambda: None, clock=lambda: clock[0])
    calls = []
    def batch(_):
        calls.append(1)
        return 0
    monkeypatch.setattr(retention, 'clean_batch', batch)
    asyncio.run(maintenance.tick())
    assert calls == [1] and maintenance.next_due == 86500
    asyncio.run(maintenance.tick()); assert calls == [1]
    clock[0] = 86500
    asyncio.run(maintenance.tick()); assert len(calls) == 2
    monkeypatch.setattr(retention, 'clean_batch', lambda _: 500)
    assert maintenance.run_pass() == 60  # 60-batch secondary budget with fixed clock.
    monkeypatch.setattr(retention, 'clean_batch', lambda _: None)
    assert maintenance.run_pass() == 300
    monkeypatch.setattr(retention, 'clean_batch', lambda _: (_ for _ in ()).throw(RuntimeError('private-secret')))
    assert maintenance.run_pass() == 300 and 'private-secret' not in caplog.text
    maintenance.stopping.set(); assert maintenance.run_pass() == 60


def test_shutdown_waits_for_current_batch_and_no_second_pass(monkeypatch):
    entered, release, stopped = Event(), Event(), Event()
    def batch(_):
        entered.set(); assert release.wait(3); stopped.set(); return 500
    monkeypatch.setattr(retention, 'clean_batch', batch)
    maintenance = retention.AuditRetentionMaintenance(lambda: None)
    async def scenario():
        task = asyncio.create_task(maintenance.tick())
        assert await asyncio.to_thread(entered.wait, 2)
        await maintenance.tick()  # Concurrent tick cannot start another worker.
        task.cancel(); release.set()
        with pytest.raises(asyncio.CancelledError): await task
    asyncio.run(scenario())
    assert stopped.is_set() and maintenance.stopping.is_set() and not maintenance.running


def test_lifespan_injects_ephemeral_factory_and_stops_task(retention_db, monkeypatch):
    engine, _ = retention_db
    from ticketyn.core.config import get_settings
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://unused:unused@127.0.0.1:1/unused')
    get_settings.cache_clear()
    from ticketyn.main import create_app
    seen = []
    async def loop(app, cleaner):
        seen.append(cleaner)
        await cleaner.tick()
        await asyncio.Event().wait()
    monkeypatch.setattr('ticketyn.security.http.cleanup_loop', loop)
    with Session(engine) as session:
        session.add(old_event(datetime.now(timezone.utc)-timedelta(days=400))); session.commit()
    try:
        factory = lambda: Session(engine)
        with TestClient(create_app(start_notifications=False, start_audit_retention=True,
                                   audit_retention_session_factory=factory)) as client:
            assert client.get('/health').status_code == 200
        assert seen[0].session_factory is factory
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(SecurityAudit)) == 0
    finally:
        get_settings.cache_clear()
