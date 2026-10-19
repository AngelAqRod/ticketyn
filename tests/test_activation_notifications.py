"""FMS creation and automatic intent share a real PostgreSQL transaction."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier, Event
from time import monotonic
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from test_ticket_concurrency import concurrent_database  # noqa: F401
from ticketyn.api import fms_data
from ticketyn.core.config import get_settings
from ticketyn.db.session import get_session
from ticketyn.models import Circuit, Responsible
from ticketyn.models.fms import Activation, ActivationIntervention, ActivationNumberConfig
from ticketyn.models.mail_jobs import MailNotificationRequest as Job
from ticketyn.models.mail_notifications import MailEventConfig, MailTransportConfig
from ticketyn.notifications import oauth, processor
from ticketyn.notifications.fields import ACTIVATION_EVENT
from ticketyn.notifications.requests import control_row, request_notification
from ticketyn.notifications.smtp import SendResult

EVENT_URL = '/api/mail-notifications/events/' + ACTIVATION_EVENT
TEMPLATE = {'version': 1,
            'subject': [{'type': 'field', 'field_id': 'activation.reference'}],
            'body': [{'type': 'field', 'field_id': 'activation.activation_notes'}]}


@pytest.fixture(autouse=True)
def no_external_mail(monkeypatch):
    import smtplib
    attempted = []
    def forbidden(*args, **kwargs):
        attempted.append(True)
        raise AssertionError('No external SMTP/OAuth is permitted')
    monkeypatch.setattr(smtplib, 'SMTP', forbidden)
    monkeypatch.setattr(smtplib, 'SMTP_SSL', forbidden)
    monkeypatch.setattr(oauth, 'token_request', forbidden)
    monkeypatch.setattr(processor, 'send_message', forbidden)
    yield
    # A transport error must not conceal an accidental synchronous send attempt.
    assert not attempted


@pytest.fixture
def activation_env(concurrent_database):
    engine, ticket = concurrent_database
    with Session(engine) as session:
        person = Responsible(name='Operador de activación')
        session.add(person)
        circuit = session.get(Circuit, ticket['circuit_id'])
        circuit.initial_capacity = 100
        circuit.initial_capacity_unit = 'Mbps'
        session.add_all([
            MailEventConfig(event_key=ACTIVATION_EVENT, mode='AUTOMATIC',
                            to_recipients=['noc@example.com'], template=TEMPLATE),
            MailTransportConfig(id=1, host='smtp.example.com', sender_email='sender@example.com'),
        ])
        session.flush()
        control = control_row(session)
        control.paused = False
        control.reason = 'AUTHORIZED'
        session.commit()
        payload = {'circuit_id': circuit.id, 'node_id': ticket['node_id'],
                   'sector_id': ticket['sector_id'], 'responsible_id': person.id,
                   'effective_at': '2020-01-01T12:00:00-06:00',
                   'activation_notes': '  IP pública: 192.0.2.1\nNAT configurado  '}
    return engine, payload


@pytest.fixture
def activation_client(activation_env, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')
    get_settings.cache_clear()
    from ticketyn.main import create_app
    app = create_app(start_notifications=False)
    def session_override():
        with Session(activation_env[0]) as session:
            yield session
    app.dependency_overrides[get_session] = session_override
    try:
        with TestClient(app) as client:
            yield client
    finally:
        get_settings.cache_clear()


def create_activation(client, payload):
    response = client.post('/api/activations', json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def operation_snapshot(session, activation_id):
    row = session.get(Activation, activation_id)
    return {column.key: getattr(row, column.key) for column in Activation.__table__.columns}


@pytest.mark.parametrize('mode', ['AUTOMATIC', 'MANUAL', 'DISABLED', None])
def test_creation_respects_mode_without_smtp(activation_env, activation_client, mode):
    engine, payload = activation_env
    with Session(engine) as session:
        event = session.get(MailEventConfig, ACTIVATION_EVENT)
        if mode is None:
            session.delete(event)
        else:
            event.mode = mode
        session.commit()
    row = create_activation(activation_client, payload)
    with Session(engine) as session:
        activation = session.get(Activation, row['id'])
        assert activation.activation_notes == payload['activation_notes']
        assert activation.initial_capacity == 100 and activation.initial_capacity_unit == 'Mbps'
        assert activation.reference == row['reference'] == 'ACT-000001'
        assert session.get(ActivationNumberConfig, 1).next_number == 2
        jobs = session.scalars(select(Job)).all()
        if mode == 'AUTOMATIC':
            assert len(jobs) == 1
            assert jobs[0].activation_id == activation.id
            assert jobs[0].event_key == ACTIVATION_EVENT
            assert (jobs[0].state, jobs[0].source, jobs[0].revision) == ('PENDING', 'AUTOMATIC', 1)
        else:
            assert jobs == []
        assert session.scalar(select(func.count()).select_from(ActivationIntervention)) == 0


def test_intent_and_activation_are_invisible_until_shared_commit(activation_env, activation_client, monkeypatch):
    engine, payload = activation_env
    original = fms_data.request_notification
    inspected = []
    def before_commit(session, event_key, activation_id, **kwargs):
        job = original(session, event_key, activation_id, **kwargs)
        assert session.get(Activation, activation_id) is not None and job.activation_id == activation_id
        with Session(engine) as observer:
            assert observer.scalar(select(func.count()).select_from(Activation)) == 0
            assert observer.scalar(select(func.count()).select_from(Job)) == 0
        inspected.append(True)
        return job
    monkeypatch.setattr(fms_data, 'request_notification', before_commit)
    row = create_activation(activation_client, payload)
    assert inspected == [True]
    with Session(engine) as observer:
        assert observer.get(Activation, row['id']) is not None
        assert observer.scalars(select(Job)).one().activation_id == row['id']


@pytest.mark.parametrize('failure,status', [('constraint', 409), ('storage', 503)])
def test_request_failure_rolls_back_activation_number_and_circuit(activation_env, activation_client, monkeypatch, failure, status):
    engine, payload = activation_env
    original = fms_data.request_notification
    def fail(session, event_key, activation_id, **kwargs):
        assert session.get(Activation, activation_id) is not None
        if failure == 'constraint':
            session.add(Job(event_key=event_key, activation_id=activation_id,
                            source='AUTOMATIC', state='INVALID'))
            session.flush()  # Actual PostgreSQL CHECK failure, not a fake transaction.
        else:
            original(session, event_key, activation_id, **kwargs)
            raise SQLAlchemyError('synthetic-private-storage-diagnostic')
    with monkeypatch.context() as scoped:
        scoped.setattr(fms_data, 'request_notification', fail)
        response = activation_client.post('/api/activations', json=payload)
    assert response.status_code == status
    assert 'synthetic-private-storage-diagnostic' not in response.text
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Activation)) == 0
        assert session.scalar(select(func.count()).select_from(Job)) == 0
        assert session.get(ActivationNumberConfig, 1) is None
        assert session.get(Circuit, payload['circuit_id']).sector_id is None
    row = create_activation(activation_client, payload)
    assert row['reference'] == 'ACT-000001'
    with Session(engine) as session:
        assert session.scalars(select(Job)).one().activation_id == row['id']


def test_commit_failure_rolls_back_both_records(activation_env):
    engine, payload = activation_env
    values = {**payload, 'effective_at': datetime(2020, 1, 1, tzinfo=timezone.utc)}
    with Session(engine) as session:
        def interrupted_commit():
            assert session.scalar(select(func.count()).select_from(Activation)) == 1
            assert session.scalar(select(func.count()).select_from(Job)) == 1
            raise RuntimeError('Simulated failure before commit')
        with patch.object(session, 'commit', side_effect=interrupted_commit):
            with pytest.raises(RuntimeError, match='Simulated failure'):
                fms_data.create_operation(session, Activation, values)
    with Session(engine) as observer:
        assert observer.scalar(select(func.count()).select_from(Activation)) == 0
        assert observer.scalar(select(func.count()).select_from(Job)) == 0
        assert observer.get(ActivationNumberConfig, 1) is None
        assert observer.get(Circuit, payload['circuit_id']).sector_id is None


@pytest.mark.parametrize('outcome,state', [('CONNECTION_ERROR', 'FAILED'), ('AUTH_ERROR', 'FAILED'),
                                         ('UNCERTAIN', 'UNCERTAIN'), ('PARTIAL_ACCEPTED', 'PARTIAL')])
def test_smtp_result_never_modifies_committed_activation(activation_env, activation_client, monkeypatch, outcome, state):
    engine, payload = activation_env
    row = create_activation(activation_client, payload)
    with Session(engine) as session:
        before = operation_snapshot(session, row['id'])
    sent = []
    def send(*args):
        with Session(engine) as observer:
            assert operation_snapshot(observer, row['id']) == before
            # No FMS circuit/counter locks can survive into SMTP processing.
            observer.scalar(select(Circuit).where(Circuit.id == payload['circuit_id']).with_for_update(nowait=True, of=Circuit))
            observer.scalar(select(ActivationNumberConfig).with_for_update(nowait=True))
        sent.append(True)
        return SendResult(outcome)
    monkeypatch.setattr(processor, 'send_message', send)
    assert processor.NotificationProcessor(engine).run_once()
    assert not processor.NotificationProcessor(engine).run_once()
    with Session(engine) as session:
        assert operation_snapshot(session, row['id']) == before
        assert session.scalars(select(Job)).one().state == state
        assert session.get(ActivationNumberConfig, 1).next_number == 2
    assert activation_client.get(f"/api/activations/{row['id']}").json() == row
    assert sent == [True]


def test_pending_activation_is_processed_after_restart(activation_env, activation_client, monkeypatch):
    engine, payload = activation_env
    row = create_activation(activation_client, payload)
    sent = Event()
    monkeypatch.setattr(processor, 'send_message', lambda *args: (sent.set(), SendResult('ACCEPTED'))[1])
    from ticketyn.main import create_app
    with TestClient(create_app(notification_engine=engine)):
        assert sent.wait(timeout=5)
    with Session(engine) as session:
        assert session.scalars(select(Job)).one().state == 'ACCEPTED'
        assert session.get(Activation, row['id']).reference == row['reference']
    assert not processor.NotificationProcessor(engine).run_once()


def test_repeated_http_creation_and_duplicate_intent_are_distinct(activation_env, activation_client):
    engine, payload = activation_env
    first = create_activation(activation_client, payload)
    second = create_activation(activation_client, payload)
    assert first['id'] != second['id'] and first['reference'] != second['reference']
    with Session(engine) as session:
        jobs = session.scalars(select(Job).order_by(Job.activation_id)).all()
        for job in jobs:
            repeated = request_notification(session, ACTIVATION_EVENT, job.activation_id, automatic=True)
            assert repeated.id == job.id and repeated.revision == job.revision
        session.commit()
        assert {job.activation_id for job in jobs} == {first['id'], second['id']}
        assert session.scalar(select(func.count()).select_from(Job)) == 2


@pytest.mark.parametrize('different_circuits', [False, True])
def test_concurrent_activations_have_independent_requests(activation_env, different_circuits):
    engine, payload = activation_env
    workers = 6
    with Session(engine) as session:
        original = session.get(Circuit, payload['circuit_id'])
        circuits = [original.id] * workers
        if different_circuits:
            rows = [Circuit(customer_id=original.customer_id, node_id=original.node_id,
                            circuit_code=f'PARALLEL-{i}', description='Activación simultánea')
                    for i in range(workers)]
            session.add_all(rows)
            session.flush()
            circuits = [c.id for c in rows]
        session.commit()
    barrier = Barrier(workers)
    def create_one(index):
        with Session(engine) as session:
            session.execute(text("SET LOCAL lock_timeout = '15s'"))
            barrier.wait(timeout=10)
            activation = fms_data.create_operation(session, Activation, {
                **payload, 'circuit_id': circuits[index],
                'effective_at': datetime(2020, 1, 1, tzinfo=timezone.utc),
            })
            return activation.id, activation.reference
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(create_one, range(workers)))
    assert len({reference for _, reference in results}) == workers
    with Session(engine) as session:
        jobs = session.scalars(select(Job)).all()
        assert {job.activation_id for job in jobs} == {id for id, _ in results}
        assert len(jobs) == workers and all(job.state == 'PENDING' for job in jobs)
        assert session.get(ActivationNumberConfig, 1).next_number == workers + 1


def test_history_immutable_notes_and_interventions_do_not_request_mail(activation_env, activation_client):
    engine, payload = activation_env
    assert activation_client.patch(EVENT_URL, json={'mode': 'MANUAL'}).status_code == 200
    historical = create_activation(activation_client, payload)
    assert activation_client.patch(EVENT_URL, json={'mode': 'AUTOMATIC'}).status_code == 200
    current = create_activation(activation_client, payload)
    with Session(engine) as session:
        original_job = session.scalars(select(Job)).one()
        identity = original_job.id, original_job.revision, original_job.state
    for row in (historical, current):
        path = f"/api/activations/{row['id']}"
        assert activation_client.patch(path, json={'activation_notes': 'No permitido'}).status_code == 405
        assert activation_client.patch(path + '/notes', json={'activation_notes': 'No permitido'}).status_code == 404
        response = activation_client.post(path + '/interventions', json={
            'responsible_id': payload['responsible_id'], 'occurred_at': payload['effective_at'],
            'content': 'Corrección histórica sin correo',
        })
        assert response.status_code == 201
        assert activation_client.get(path).json() == row
    with Session(engine) as session:
        job = session.scalars(select(Job)).one()
        assert (job.id, job.revision, job.state) == identity
        assert job.activation_id == current['id']


@pytest.mark.parametrize('mode', ['MANUAL', 'DISABLED'])
def test_mode_change_cancels_committed_intent_before_smtp(activation_env, activation_client, mode):
    engine, payload = activation_env
    row = create_activation(activation_client, payload)
    assert activation_client.patch(EVENT_URL, json={'mode': mode}).status_code == 200
    assert not processor.NotificationProcessor(engine).run_once()
    with Session(engine) as session:
        assert session.scalars(select(Job)).one().state == 'CANCELLED'
        assert session.get(Activation, row['id']).reference == row['reference']


@pytest.mark.parametrize('mode', ['MANUAL', 'DISABLED'])
def test_mode_update_waits_for_creation_commit(activation_env, monkeypatch, mode):
    from ticketyn.api.mail_notifications import update_event
    from ticketyn.schemas.mail_notifications import EventUpdate

    engine, payload = activation_env
    intent_ready, release_creation, mode_started = Event(), Event(), Event()
    pids = {}
    original = fms_data.request_notification
    def hold_intent(session, *args, **kwargs):
        job = original(session, *args, **kwargs)
        pids['creation'] = session.scalar(select(func.pg_backend_pid()))
        intent_ready.set()
        assert release_creation.wait(timeout=10)
        return job
    monkeypatch.setattr(fms_data, 'request_notification', hold_intent)

    def create_one():
        with Session(engine) as session:
            activation = fms_data.create_operation(session, Activation, {
                **payload, 'effective_at': datetime(2020, 1, 1, tzinfo=timezone.utc),
            })
            return activation.id

    def change_mode():
        with Session(engine) as session:
            session.execute(text("SET LOCAL lock_timeout = '10s'"))
            pids['mode'] = session.scalar(select(func.pg_backend_pid()))
            mode_started.set()
            return update_event(ACTIVATION_EVENT, EventUpdate(mode=mode), session).mode

    with ThreadPoolExecutor(max_workers=2) as pool:
        creation = pool.submit(create_one)
        try:
            assert intent_ready.wait(timeout=5)
            changing = pool.submit(change_mode)
            assert mode_started.wait(timeout=5)
            deadline = monotonic() + 5
            blocked = False
            with Session(engine) as observer:
                while monotonic() < deadline:
                    blockers = observer.scalar(select(func.pg_blocking_pids(pids['mode'])))
                    if pids['creation'] in blockers:
                        blocked = True
                        break
                    release_creation.wait(timeout=.01)
            assert blocked, 'Mode changes must serialize with activation/intent commit'
        finally:
            release_creation.set()
        activation_id = creation.result(timeout=10)
        assert changing.result(timeout=10) == mode
    with Session(engine) as session:
        job = session.scalars(select(Job)).one()
        assert job.activation_id == activation_id and job.state == 'CANCELLED'
        assert session.get(Activation, activation_id) is not None


@pytest.mark.parametrize('path,extra', [
    ('/api/capacity-changes', {'operation_type': 'INCREASE', 'new_capacity': '200', 'new_unit': 'Mbps'}),
    ('/api/circuit-lifecycle', {'operation_type': 'REACTIVATE'}),
    ('/api/circuit-lifecycle', {'operation_type': 'DEACTIVATE'}),
])
def test_other_fms_operations_never_request_notifications(activation_env, activation_client, monkeypatch, path, extra):
    engine, payload = activation_env
    def forbidden(*args, **kwargs):
        raise AssertionError('Only activation creation may request mail')
    monkeypatch.setattr(fms_data, 'request_notification', forbidden)
    values = {key: value for key, value in payload.items() if key != 'activation_notes'}
    values.update(extra)
    if values.get('operation_type') == 'DEACTIVATE':
        reason = activation_client.post('/api/deactivation-reasons', json={'name': 'Baja de prueba'}).json()
        values['reason_id'] = reason['id']
    assert activation_client.post(path, json=values).status_code == 201
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0
