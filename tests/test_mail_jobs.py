"""Persistent jobs: committed data in disposable schemas, mocked SMTP only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier, Event
import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ticketyn.core.config import get_settings
from ticketyn.models import Activation, Responsible
from ticketyn.models.mail_jobs import MailNotificationRequest as Job, MailProcessorControl as Control
from ticketyn.models.mail_notifications import MailEventConfig, MailTransportConfig
from ticketyn.notifications.fields import ACTIVATION_EVENT
from ticketyn.notifications import processor as worker
from ticketyn.notifications.requests import request_notification, control_row, transition, ACTIVE, TERMINAL
from ticketyn.notifications.smtp import SendResult, MailFailure
from ticketyn.db.session import get_session
from test_ticket_concurrency import concurrent_database  # noqa: F401
from test_e2e_update_migration import cli
from test_fms import operation_payload, create  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
BASE = '/api/mail-notifications'
EVENT_URL = BASE + '/events/' + ACTIVATION_EVENT
TEMPLATE = {'version': 1, 'subject': [{'type': 'text', 'text': 'Activación'}, {'type': 'field', 'field_id': 'activation.reference'}], 'body': [
    {'type': 'introduction', 'text': 'Estimados,'}, {'type': 'field', 'field_id': 'activation.reference'},
    {'type': 'field', 'field_id': 'activation.activation_notes'}, {'type': 'signature', 'text': 'NOC'}]}


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    import smtplib
    from ticketyn.notifications import oauth
    def forbidden(*args, **kwargs): raise AssertionError('External SMTP/OAuth is forbidden in job tests')
    monkeypatch.setattr(smtplib, 'SMTP', forbidden); monkeypatch.setattr(smtplib, 'SMTP_SSL', forbidden)
    monkeypatch.setattr(oauth, 'token_request', forbidden)


@pytest.fixture
def jobs_env(concurrent_database):
    engine, payload = concurrent_database
    with Session(engine) as session:
        person = Responsible(name='Operador de prueba'); session.add(person); session.flush()
        activation = Activation(circuit_id=payload['circuit_id'], responsible_id=person.id, effective_at=datetime(2020, 1, 1, tzinfo=timezone.utc), activation_number=1, reference='ACT-0000001', activation_notes='Notas\n  históricas')
        session.add_all([activation, MailTransportConfig(id=1, host='smtp.example.com', sender_email='noc@example.com'), MailEventConfig(event_key=ACTIVATION_EVENT, mode='AUTOMATIC', to_recipients=['to@example.com'], cc_recipients=['cc@example.com'], bcc_recipients=['hidden@example.com'], template=TEMPLATE)])
        session.flush(); activation_id = activation.id
        control = control_row(session); control.paused = False; control.reason = 'AUTHORIZED'; session.commit()
    return engine, activation_id


@pytest.fixture
def jobs_client(jobs_env, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test'); get_settings.cache_clear()
    from ticketyn.main import create_app
    engine, _ = jobs_env
    app = create_app(start_notifications=False)
    def session_override():
        with Session(engine) as session: yield session
    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client: yield client
    get_settings.cache_clear()


def enqueue(env, *, manual=False, revision=None):
    engine, id = env
    with Session(engine) as session:
        job = request_notification(session, ACTIVATION_EVENT, id, automatic=not manual, expected_revision=revision)
        session.commit()
        return job.id, job.revision


def state(env):
    with Session(env[0]) as session:
        job = session.scalar(select(Job))
        return job.state, job.revision, job.error_code


@pytest.fixture
def sent(monkeypatch):
    calls = []
    def send(settings, credentials, message, sender, recipients):
        calls.append((settings, message, sender, recipients)); return SendResult('ACCEPTED')
    monkeypatch.setattr(worker, 'send_message', send)
    return calls


def test_persist_unique_transaction_and_no_message_columns(jobs_env):
    engine, activation_id = jobs_env
    with Session(engine) as session:
        first = request_notification(session, ACTIVATION_EVENT, activation_id, automatic=True)
        assert first.state == 'PENDING' and first.revision == 1
        session.rollback()
    with Session(engine) as session: assert session.scalar(select(func.count()).select_from(Job)) == 0
    first = enqueue(jobs_env)
    assert enqueue(jobs_env) == first
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1
        session.add(Job(event_key=ACTIVATION_EVENT, activation_id=activation_id, source='MANUAL'))
        with pytest.raises(IntegrityError): session.commit()
    names = {column.name for column in Job.__table__.columns}
    assert not {'subject', 'body', 'eml', 'password', 'token', 'recipients', 'attachments'} & names
    assert 'owner_token' in names  # opaque coordination, never an OAuth credential


def test_invalid_reference_event_and_disabled_mode(jobs_env):
    engine, activation_id = jobs_env
    with Session(engine) as session:
        for key, id in [('unknown', activation_id), (ACTIVATION_EVENT, 2147483647)]:
            with pytest.raises(HTTPException): request_notification(session, key, id, automatic=True)
            session.rollback()
        event = session.get(MailEventConfig, ACTIVATION_EVENT); event.mode = 'DISABLED'; session.commit()
        assert request_notification(session, ACTIVATION_EVENT, activation_id, automatic=True) is None
        with pytest.raises(HTTPException, match='desactivado'): request_notification(session, ACTIVATION_EVENT, activation_id, automatic=False, expected_revision=0)


@pytest.mark.parametrize('terminal', sorted(TERMINAL))
def test_reuse_row_manual_generation_and_stale_double_click(jobs_env, terminal):
    id, revision = enqueue(jobs_env)
    with Session(jobs_env[0]) as session:
        row = session.get(Job, id); row.state = terminal; row.finished_at = func.clock_timestamp(); session.commit()
    # Another automatic call must never retry a completed/failed/ambiguous request.
    assert enqueue(jobs_env) == (id, revision) and state(jobs_env)[0] == terminal
    assert enqueue(jobs_env, manual=True, revision=revision) == (id, revision + 1)
    assert enqueue(jobs_env, manual=True, revision=revision) == (id, revision + 1)  # coalesced while active
    with Session(jobs_env[0]) as session:
        row = session.get(Job, id); row.state = 'ACCEPTED'; session.commit()
    with pytest.raises(HTTPException, match='cambió'): enqueue(jobs_env, manual=True, revision=revision)
    assert enqueue(jobs_env, manual=True, revision=revision + 1) == (id, revision + 2)


def test_manual_request_survives_automatic_to_manual(jobs_env, jobs_client):
    enqueue(jobs_env)
    enqueue(jobs_env, manual=True, revision=1)
    assert jobs_client.patch(EVENT_URL, json={'mode': 'MANUAL'}).status_code == 200
    with Session(jobs_env[0]) as session:
        job = session.scalar(select(Job)); assert job.source == 'MANUAL' and job.state == 'PENDING'


@pytest.mark.parametrize(('old', 'new'), [('PENDING','SENDING'), ('ACCEPTED','SENDING'), ('SENDING','PENDING'), ('FAILED','ACCEPTED')])
def test_invalid_transitions_rejected(old, new):
    with pytest.raises(ValueError): transition(Job(state=old), new)


def test_process_current_configuration_body_and_no_open_transaction(jobs_env, jobs_client, sent, monkeypatch):
    enqueue(jobs_env)
    # Changes made after enqueue must be resolved at processing time.
    with Session(jobs_env[0]) as session:
        event = session.get(MailEventConfig, ACTIVATION_EVENT)
        event.to_recipients = ['current@example.com']; session.commit()
    preview = jobs_client.post(EVENT_URL + '/preview', json={
        'activation_id': jobs_env[1], 'template': TEMPLATE,
    })
    assert preview.status_code == 200
    original = worker.send_message
    def checked(*args):
        with Session(jobs_env[0]) as session:
            row = session.scalar(select(Job)); assert row.state == 'SENDING' and row.sending_at
            # The advisory lock owner remains alive but AUTOCOMMIT, without xact.
            assert session.scalar(text("SELECT bool_and(a.xact_start IS NULL) FROM pg_locks l JOIN pg_stat_activity a ON a.pid=l.pid WHERE l.locktype='advisory' AND l.objid=:key"), {'key': worker.LOCK_KEY}) is True
        return original(*args)
    monkeypatch.setattr(worker, 'send_message', checked)
    assert worker.NotificationProcessor(jobs_env[0]).run_once()
    assert state(jobs_env) == ('ACCEPTED', 4, None)
    assert len(sent) == 1
    _, message, _, recipients = sent[0]
    assert recipients == ['current@example.com', 'cc@example.com', 'hidden@example.com']
    assert message['Bcc'] is None and 'hidden@example.com' not in message.as_string()
    assert str(message['Subject']) == 'Activación ACT-0000001'
    body = message.get_content().replace('\r\n', '\n')
    assert body == 'Estimados,\n\nCORRELATIVO: ACT-0000001\nNOTAS DE ACTIVACIÓN:\nNotas\n  históricas\n\nNOC\n'
    assert body.removesuffix('\n') == preview.json()['body']
    assert not worker.NotificationProcessor(jobs_env[0]).run_once() and len(sent) == 1


@pytest.mark.parametrize(('result', 'expected'), [('PARTIAL_ACCEPTED','PARTIAL'), ('UNCERTAIN','UNCERTAIN'), ('AUTH_ERROR','FAILED'), ('RECIPIENT_REJECTED','FAILED'), ('CONNECTION_ERROR','FAILED')])
def test_terminal_outcomes_are_not_retried(jobs_env, monkeypatch, result, expected):
    enqueue(jobs_env); calls = []
    monkeypatch.setattr(worker, 'send_message', lambda *args: calls.append(1) or SendResult(result))
    processor = worker.NotificationProcessor(jobs_env[0]); assert processor.run_once()
    assert state(jobs_env) == (expected, 4, result)
    assert not worker.NotificationProcessor(jobs_env[0]).run_once() and calls == [1]


def test_unexpected_exception_after_sending_is_uncertain_and_sanitized(jobs_env, monkeypatch, caplog):
    enqueue(jobs_env)
    def broken(*args): raise RuntimeError('DO-NOT-LOG credential, notes, SMTP server response')
    monkeypatch.setattr(worker, 'send_message', broken)
    assert worker.NotificationProcessor(jobs_env[0]).run_once()
    assert state(jobs_env) == ('UNCERTAIN', 4, 'SMTP_INTERRUPTED')
    assert 'DO-NOT-LOG' not in caplog.text


@pytest.mark.parametrize(('interrupted', 'expected'), [('PREPARING','ACCEPTED'), ('SENDING','UNCERTAIN')])
def test_restart_recovery(jobs_env, sent, interrupted, expected):
    id, _ = enqueue(jobs_env)
    with Session(jobs_env[0]) as session:
        row = session.get(Job, id); row.state = interrupted; row.owner_token = 'interrupted'; session.commit()
    worker.NotificationProcessor(jobs_env[0]).run_once()
    assert state(jobs_env)[0] == expected
    assert len(sent) == (1 if interrupted == 'PREPARING' else 0)


def test_missing_control_after_restore_pauses_and_quarantines(jobs_env, jobs_client, sent):
    id, _ = enqueue(jobs_env)
    with Session(jobs_env[0]) as session:
        row = session.get(Job, id); row.state = 'SENDING'; row.owner_token = 'old-process'
        session.delete(session.get(Control, 1)); session.commit()
    assert not worker.NotificationProcessor(jobs_env[0]).run_once()
    assert state(jobs_env) == ('UNCERTAIN', 2, 'RESTORED_INTERRUPTED') and not sent
    status = jobs_client.get(BASE + '/processor').json(); assert status['paused']
    assert jobs_client.post(BASE + '/processor/resume', json={'revision': status['revision'], 'confirmation': 'REANUDAR'}).status_code == 200
    assert not worker.NotificationProcessor(jobs_env[0]).run_once() and not sent


def test_pause_review_revision_and_resume_only_pending(jobs_env, jobs_client, sent):
    enqueue(jobs_env)
    paused = jobs_client.post(BASE + '/processor/pause').json()
    assert paused['paused'] and paused['counts']['PENDING'] == 1
    assert not worker.NotificationProcessor(jobs_env[0]).run_once() and not sent
    rows = jobs_client.get(BASE + '/requests', params={'state':'PENDING', 'limit':1}).json()
    assert len(rows) == 1 and 'owner_token' not in rows[0] and 'body' not in rows[0]
    assert jobs_client.get(BASE + '/requests', params={'limit':101}).status_code == 422
    assert jobs_client.post(BASE + '/processor/resume', json={'revision':paused['revision'], 'confirmation':'YES'}).status_code == 422
    changed = jobs_client.post(BASE + '/processor/pause').json()
    assert jobs_client.post(BASE + '/processor/resume', json={'revision':paused['revision'], 'confirmation':'REANUDAR'}).status_code == 409
    assert jobs_client.post(BASE + '/processor/resume', json={'revision':changed['revision'], 'confirmation':'REANUDAR'}).status_code == 200
    assert worker.NotificationProcessor(jobs_env[0]).run_once() and len(sent) == 1


@pytest.mark.parametrize('source', ['AUTOMATIC','MANUAL'])
@pytest.mark.parametrize('initial', ['PENDING','PREPARING'])
def test_disabled_cancels_all_unstarted(jobs_env, jobs_client, sent, source, initial):
    id, _ = enqueue(jobs_env)
    with Session(jobs_env[0]) as session:
        row = session.get(Job, id); row.source = source; row.state = initial; session.commit()
    assert jobs_client.patch(EVENT_URL, json={'mode':'DISABLED'}).status_code == 200
    assert state(jobs_env)[0] == 'CANCELLED'
    assert not worker.NotificationProcessor(jobs_env[0]).run_once() and not sent


def test_mode_changed_during_preparation_cancels_before_smtp(jobs_env, jobs_client, sent, monkeypatch):
    enqueue(jobs_env)
    original = worker.NotificationProcessor.render
    def render(self, identity):
        content = original(self, identity)
        assert jobs_client.patch(EVENT_URL, json={'mode':'MANUAL'}).status_code == 200
        return content
    monkeypatch.setattr(worker.NotificationProcessor, 'render', render)
    worker.NotificationProcessor(jobs_env[0]).run_once()
    assert state(jobs_env)[0] == 'CANCELLED' and not sent


def test_mode_change_allows_smtp_already_started(jobs_env, jobs_client, monkeypatch):
    enqueue(jobs_env)
    def send(*args):
        assert jobs_client.patch(EVENT_URL, json={'mode':'DISABLED'}).status_code == 200
        assert state(jobs_env)[0] == 'SENDING'
        return SendResult('ACCEPTED')
    monkeypatch.setattr(worker, 'send_message', send)
    worker.NotificationProcessor(jobs_env[0]).run_once()
    assert state(jobs_env)[0] == 'ACCEPTED'


def test_concurrent_requests_and_processors_never_duplicate(jobs_env, sent):
    barrier = Barrier(4)
    def request(_): barrier.wait(timeout=10); return enqueue(jobs_env, manual=True, revision=0)
    with ThreadPoolExecutor(max_workers=4) as pool: results = list(pool.map(request, range(4)))
    assert len(set(results)) == 1
    barrier = Barrier(2)
    def tick(_): barrier.wait(timeout=10); return worker.NotificationProcessor(jobs_env[0]).run_once()
    with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(tick, range(2)))
    assert state(jobs_env)[0] == 'ACCEPTED' and len(sent) == 1


def test_busy_transport_defers_without_smtp_failure(jobs_env, sent):
    enqueue(jobs_env)
    with Session(jobs_env[0]) as session:
        from datetime import timedelta
        row = session.get(MailTransportConfig, 1); row.test_lease_until = datetime.now(timezone.utc) + timedelta(minutes=10); session.commit()
    assert not worker.NotificationProcessor(jobs_env[0]).run_once()
    assert state(jobs_env) == ('PENDING', 3, None) and not sent


def test_lifespan_recovers_pending_on_own_sessions(jobs_env, sent, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test'); get_settings.cache_clear()
    from ticketyn.main import create_app
    enqueue(jobs_env)
    with TestClient(create_app(notification_engine=jobs_env[0])):
        deadline = time.monotonic() + 5
        while state(jobs_env)[0] != 'ACCEPTED' and time.monotonic() < deadline: time.sleep(.02)
        assert state(jobs_env)[0] == 'ACCEPTED'
    assert len(sent) == 1
    get_settings.cache_clear()


def test_fms_creates_automatic_intent_and_exposes_only_scoped_manual_requests(api_client, operation_payload, db_session):
    api_client.patch(EVENT_URL, json={'mode':'AUTOMATIC', 'to':['noc@example.com']})
    activation = create(api_client, '/api/activations', operation_payload)
    job = db_session.scalars(select(Job)).one()
    assert job.activation_id == activation['id'] and job.state == 'PENDING'
    assert job.source == 'AUTOMATIC' and job.event_key == ACTIVATION_EVENT
    paths = api_client.get('/openapi.json').json()['paths']
    assert not any('/activations/' in path and '/send' in path for path in paths)
    assert {'get', 'post'} <= paths['/api/activations/{id}/notification'].keys()
    assert BASE + '/requests' in paths and 'post' not in paths[BASE + '/requests']


def test_jobs_migration_upgrade_downgrade_preserves_previous_data(postgres_engine):
    database = 'mail_jobs_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin: admin.execute(text('CREATE DATABASE ' + database))
    engine = create_engine(postgres_engine.url.set(database=database))
    try:
        cli(engine.url, 'upgrade', '0028_mail_transport')
        with engine.begin() as conn:
            conn.execute(text("UPDATE mail_transport_config SET host='smtp.example.com',smtp_password_encrypted='opaque',oauth_status='CONFIGURED'"))
            smtp = conn.scalar(text('SELECT to_jsonb(s) FROM mail_transport_config s'))
            event = conn.scalar(text('SELECT to_jsonb(e) FROM mail_event_config e'))
        cli(engine.url, 'upgrade', '0029_mail_requests')
        with engine.connect() as conn:
            assert conn.scalar(text('SELECT paused FROM mail_processor_control')) is True
            assert conn.scalar(text('SELECT to_jsonb(s) FROM mail_transport_config s')) == smtp
            assert conn.scalar(text('SELECT to_jsonb(e) FROM mail_event_config e')) == event
        cli(engine.url, 'downgrade', '0028_mail_transport')
        assert 'mail_notification_requests' not in inspect(engine).get_table_names()
        cli(engine.url, 'upgrade', '0029_mail_requests')
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO customers(id,customer_code,name) VALUES(1,'C','Cliente')"))
            conn.execute(text("INSERT INTO responsibles(id,name) VALUES(1,'Operador')"))
            conn.execute(text("INSERT INTO circuits(id,customer_id,circuit_code,description) VALUES(1,1,'C-1','Conservar')"))
            conn.execute(text("INSERT INTO activations(id,circuit_id,responsible_id,effective_at,activation_number,reference) VALUES(1,1,1,now(),1,'ACT-1')"))
            conn.execute(text("INSERT INTO mail_notification_requests(event_key,activation_id,source) VALUES('fms.activation.created',1,'AUTOMATIC')"))
        with pytest.raises(AssertionError, match='solicitudes de notificación'): cli(engine.url, 'downgrade', '0028_mail_transport')
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin: admin.execute(text('DROP DATABASE ' + database))


def test_real_dump_restore_pauses_before_restart(postgres_engine, tmp_path, sent, monkeypatch):
    import os
    source, target = 'mail_dump_' + uuid4().hex, 'mail_restore_' + uuid4().hex
    admin = postgres_engine
    engines = []
    try:
        with admin.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
            for name in (source, target): conn.execute(text('CREATE DATABASE ' + name))
        original = create_engine(admin.url.set(database=source)); restored = create_engine(admin.url.set(database=target)); engines = [original, restored]
        cli(original.url, 'upgrade', '0029_mail_requests')
        with original.begin() as conn:
            conn.execute(text("UPDATE mail_transport_config SET host='smtp.example.com',sender_email='noc@example.com'"))
            conn.execute(text("UPDATE mail_event_config SET mode='AUTOMATIC',to_recipients='[\"to@example.com\"]'::jsonb,template=CAST(:template AS jsonb)"), {'template':json.dumps(TEMPLATE)})
            conn.execute(text("INSERT INTO customers(id,customer_code,name) VALUES(1,'C','Cliente')"))
            conn.execute(text("INSERT INTO responsibles(id,name) VALUES(1,'Operador')"))
            conn.execute(text("INSERT INTO circuits(id,customer_id,circuit_code,description) VALUES(1,1,'C-1','Conservar')"))
            for id, state in [(1, 'PENDING'), (2, 'PREPARING'), (3, 'SENDING')]:
                conn.execute(text("INSERT INTO activations(id,circuit_id,responsible_id,effective_at,activation_number,reference) VALUES(:id,1,1,now(),:id,:reference)"), {'id': id, 'reference': f'ACT-{id}'})
                conn.execute(text("INSERT INTO mail_notification_requests(event_key,activation_id,source,state) VALUES('fms.activation.created',:id,'AUTOMATIC',:state)"), {'id':id, 'state':state})
            conn.execute(text("UPDATE mail_processor_control SET paused=false,reason='AUTHORIZED',database_oid=(SELECT oid FROM pg_database WHERE datname=current_database())"))
        dump = tmp_path/'database.dump'
        pg_args = ['--host', admin.url.query['host'], '--port', admin.url.query['port'], '--username', admin.url.username, '--no-password']
        environment = {key: value for key, value in os.environ.items() if not key.startswith('PG')}
        environment['PGPASSFILE'] = '/dev/null'
        with dump.open('wb') as output:
            subprocess.run(['pg_dump', *pg_args, '--dbname', source, '--format=custom', '--exclude-table-data=public.mail_processor_control'], env=environment, stdout=output, stderr=subprocess.PIPE, check=True, timeout=30)
        subprocess.run(['pg_restore', *pg_args, '--dbname', target, '--no-owner', '--no-privileges', '--single-transaction', '--exit-on-error', str(dump)], env=environment, check=True, capture_output=True, timeout=30)
        with restored.connect() as conn:
            assert conn.scalar(text('SELECT count(*) FROM mail_processor_control')) == 0
        # Execute the actual non-destructive restore pause hook, before cutover/start.
        script = '''source "$1"
STAGE=$2
STATE=$3
restore_pg() {
    local tool=$1; shift
    "$tool" --host="$MAIL_TEST_HOST" --port="$MAIL_TEST_PORT" --username="$MAIL_TEST_USER" --no-password "$@"
}
restore_fail() { printf '%s\\n' "$1" >&2; exit 1; }
restore_pause_mail
'''
        subprocess.run(['bash', '-c', script, 'test', str(ROOT/'restore.sh'), target, str(tmp_path)], env={**environment, 'MAIL_TEST_HOST': admin.url.query['host'], 'MAIL_TEST_PORT': admin.url.query['port'], 'MAIL_TEST_USER': admin.url.username}, check=True, capture_output=True, timeout=30)
        with restored.connect() as conn:
            assert conn.scalar(text('SELECT paused FROM mail_processor_control')) is True
            assert conn.scalar(text('SELECT reason FROM mail_processor_control')) == 'RESTORED'
            assert conn.execute(text('SELECT state FROM mail_notification_requests ORDER BY activation_id')).scalars().all() == ['PENDING', 'UNCERTAIN', 'UNCERTAIN']
            assert conn.execute(text('SELECT revision FROM mail_notification_requests ORDER BY activation_id')).scalars().all() == [1, 2, 2]
        assert not worker.NotificationProcessor(restored).run_once() and not sent
        monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test'); get_settings.cache_clear()
        from ticketyn.main import create_app
        app = create_app(start_notifications=False)
        def override():
            with Session(restored) as session: yield session
        app.dependency_overrides[get_session] = override
        with TestClient(app) as client:
            review = client.get(BASE + '/processor').json()
            assert review['counts']['UNCERTAIN'] == 2 and review['counts']['PENDING'] == 1
            assert client.post(BASE + '/processor/resume', json={'revision':review['revision'], 'confirmation':'REANUDAR'}).status_code == 200
        assert worker.NotificationProcessor(restored).run_once() and len(sent) == 1
        with restored.connect() as conn:
            assert conn.execute(text('SELECT state FROM mail_notification_requests ORDER BY activation_id')).scalars().all() == ['ACCEPTED', 'UNCERTAIN', 'UNCERTAIN']
        get_settings.cache_clear()
    finally:
        for engine in engines: engine.dispose()
        with admin.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
            for name in (source, target): conn.execute(text('DROP DATABASE IF EXISTS ' + name))


def test_database_identity_change_pauses_processor(jobs_env, sent):
    enqueue(jobs_env)
    with Session(jobs_env[0]) as session:
        control = session.get(Control, 1); control.database_oid = 0; session.commit()
    assert not worker.NotificationProcessor(jobs_env[0]).run_once()
    with Session(jobs_env[0]) as session: assert session.get(Control, 1).paused is True
    assert state(jobs_env)[0] == 'PENDING' and not sent


def test_preparation_failure_is_sanitized_and_never_retried(jobs_env, sent, monkeypatch, caplog):
    enqueue(jobs_env)
    def invalid(*args): raise RuntimeError('SECRET-RAW-MESSAGE-AND-CREDENTIAL')
    monkeypatch.setattr(worker.NotificationProcessor, 'render', invalid)
    assert worker.NotificationProcessor(jobs_env[0]).run_once()
    assert state(jobs_env) == ('FAILED', 3, 'PREPARATION_ERROR')
    assert not worker.NotificationProcessor(jobs_env[0]).run_once()
    assert not sent and 'SECRET-RAW-MESSAGE-AND-CREDENTIAL' not in caplog.text


def test_fencing_does_not_overwrite_new_generation(jobs_env, monkeypatch):
    id, _ = enqueue(jobs_env)
    def send(*args):
        with Session(jobs_env[0]) as session:
            row = session.get(Job, id); row.revision += 1; row.owner_token = None; row.state = 'PENDING'; session.commit()
        return SendResult('ACCEPTED')
    monkeypatch.setattr(worker, 'send_message', send)
    worker.NotificationProcessor(jobs_env[0]).run_once()
    assert state(jobs_env) == ('PENDING', 4, None)


def test_worker_reuses_oauth_credentials_without_storing_them_in_job(jobs_env, monkeypatch):
    from ticketyn.notifications.smtp import Credentials
    enqueue(jobs_env)
    with Session(jobs_env[0]) as session:
        row = session.get(MailTransportConfig, 1); row.auth_method = 'OAUTH2_DELEGATED'; row.provider = 'GMAIL'; row.username = 'noc@example.com'; session.commit()
    monkeypatch.setattr(worker, 'transport_credentials', lambda row: Credentials(access_token='SYNTHETIC-OAUTH-ACCESS'))
    def send(settings, credentials, *args):
        assert settings.auth_method == 'OAUTH2_DELEGATED' and credentials.access_token == 'SYNTHETIC-OAUTH-ACCESS'
        return SendResult('ACCEPTED')
    monkeypatch.setattr(worker, 'send_message', send)
    assert worker.NotificationProcessor(jobs_env[0]).run_once()
    assert state(jobs_env)[0] == 'ACCEPTED'
    with Session(jobs_env[0]) as session:
        row = session.scalar(select(Job))
        assert 'SYNTHETIC-OAUTH-ACCESS' not in str({column.name: getattr(row, column.name) for column in Job.__table__.columns})


def test_in_flight_lease_prevents_another_worker_recovery(jobs_env, sent, monkeypatch):
    enqueue(jobs_env)
    def send(*args):
        assert not worker.NotificationProcessor(jobs_env[0]).run_once()
        assert state(jobs_env)[0] == 'SENDING'
        return SendResult('ACCEPTED')
    monkeypatch.setattr(worker, 'send_message', send)
    worker.NotificationProcessor(jobs_env[0]).run_once()
    assert state(jobs_env)[0] == 'ACCEPTED'


@pytest.mark.parametrize('failure', ['storage_once', 'storage_unavailable', 'process_exit'])
def test_interruption_after_smtp_acceptance_is_never_automatically_resent(jobs_env, sent, monkeypatch, caplog, failure):
    from sqlalchemy.exc import SQLAlchemyError
    enqueue(jobs_env)
    processor = worker.NotificationProcessor(jobs_env[0])
    original = processor.finish
    attempts = []
    def interrupted_finish(*args):
        attempts.append(True)
        if failure == 'process_exit':
            raise SystemExit()
        if failure == 'storage_unavailable' or len(attempts) == 1:
            raise SQLAlchemyError('synthetic-private-storage-error')
        return original(*args)
    with monkeypatch.context() as scoped:
        scoped.setattr(processor, 'finish', interrupted_finish)
        if failure == 'storage_once':
            assert processor.run_once()
            assert state(jobs_env)[0] == 'UNCERTAIN'
        else:
            with pytest.raises(SystemExit if failure == 'process_exit' else SQLAlchemyError):
                processor.run_once()
            assert state(jobs_env)[0] == 'SENDING'
    # A new worker recovers an interrupted SMTP boundary; it never repeats DATA.
    assert not worker.NotificationProcessor(jobs_env[0]).run_once()
    assert state(jobs_env)[0] == 'UNCERTAIN' and len(sent) == 1
    assert 'synthetic-private-storage-error' not in caplog.text


def test_lost_postgres_advisory_connection_before_smtp_never_sends(jobs_env, sent, monkeypatch):
    enqueue(jobs_env)
    processor = worker.NotificationProcessor(jobs_env[0])
    original = processor.render
    def lose_lock(identity):
        content = original(identity)
        # Terminate only this worker's connection inside this disposable cluster.
        with Session(jobs_env[0]) as session:
            pid = session.scalar(text("SELECT pid FROM pg_locks WHERE locktype='advisory' AND classid=0 AND objid=:key AND granted"), {'key': worker.LOCK_KEY})
            assert pid is not None
            assert session.scalar(text('SELECT pg_terminate_backend(:pid)'), {'pid': pid})
        return content
    monkeypatch.setattr(processor, 'render', lose_lock)
    assert processor.run_once()
    assert state(jobs_env)[0] == 'FAILED' and not sent
    assert not worker.NotificationProcessor(jobs_env[0]).run_once()


def test_orderly_shutdown_during_preparation_preserves_pending_without_smtp(jobs_env, sent, monkeypatch):
    enqueue(jobs_env)
    processor = worker.NotificationProcessor(jobs_env[0])
    original = processor.render
    def stop_preparing(identity):
        content = original(identity)
        processor.stop()
        return content
    monkeypatch.setattr(processor, 'render', stop_preparing)
    assert not processor.run_once()
    assert state(jobs_env)[0] == 'PENDING' and not sent
    assert worker.NotificationProcessor(jobs_env[0]).run_once()
    assert state(jobs_env)[0] == 'ACCEPTED' and len(sent) == 1


def test_late_duplicate_of_coalesced_request_is_rejected(jobs_env, sent):
    enqueue(jobs_env)
    id, observed = enqueue(jobs_env, manual=True, revision=1)
    assert worker.NotificationProcessor(jobs_env[0]).run_once() and len(sent) == 1
    # The first click joined an already pending automatic job. A delayed second
    # click must not be mistaken for deliberate resend after SMTP completes.
    with pytest.raises(HTTPException, match='cambió'):
        enqueue(jobs_env, manual=True, revision=observed)
    current = state(jobs_env)[1]
    assert enqueue(jobs_env, manual=True, revision=current) == (id, current + 1)
