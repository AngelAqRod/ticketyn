"""Scoped manual requests: real PostgreSQL transactions, mocked mail only."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_ticket_concurrency import concurrent_database  # noqa: F401
from test_activation_notifications import (activation_env, activation_client, no_external_mail,
                                         create_activation, operation_snapshot)  # noqa: F401
from ticketyn.models.fms import Activation, ActivationIntervention
from ticketyn.models.mail_jobs import MailNotificationRequest as Job, MailProcessorControl
from ticketyn.models.mail_notifications import MailEventConfig, MailTransportConfig
from ticketyn.notifications import processor
from ticketyn.notifications.fields import ACTIVATION_EVENT
from ticketyn.notifications.smtp import SendResult


def make_activation(env, client, mode='MANUAL'):
    with Session(env[0]) as session:
        session.get(MailEventConfig, ACTIVATION_EVENT).mode = mode
        session.commit()
    activation = create_activation(client, env[1])
    return activation, f"/api/activations/{activation['id']}/notification"


def accepted_transport(monkeypatch):
    calls = []
    def send(*args):
        calls.append(args)
        return SendResult('ACCEPTED')
    monkeypatch.setattr(processor, 'send_message', send)
    return calls


@pytest.mark.parametrize('mode', ['AUTOMATIC', 'MANUAL'])
def test_first_send_and_unlimited_deliberate_resends(activation_env, activation_client, monkeypatch, mode):
    engine = activation_env[0]
    activation, path = make_activation(activation_env, activation_client, mode)
    sent = accepted_transport(monkeypatch)
    if mode == 'AUTOMATIC':
        assert processor.NotificationProcessor(engine).run_once()
    else:
        initial = activation_client.get(path).json()
        assert initial['state'] is None and initial['revision'] == 0 and initial['can_request']
    with Session(engine) as session:
        before = operation_snapshot(session, activation['id'])
    ids = set()
    for _ in range(4):
        current = activation_client.get(path).json()
        response = activation_client.post(path, json={'revision': current['revision']})
        assert response.status_code == 202, response.text
        queued = response.json()
        assert queued['state'] == 'PENDING' and not queued['can_request']
        assert 'solicitada' in queued['message'] and 'entreg' not in queued['message']
        assert processor.NotificationProcessor(engine).run_once()
        current = activation_client.get(path).json()
        assert current['state'] == 'ACCEPTED' and current['can_request']
        with Session(engine) as session:
            job = session.scalars(select(Job)).one()
            ids.add(job.id)
            assert job.source == 'MANUAL'
            assert operation_snapshot(session, activation['id']) == before
            assert session.scalar(select(func.count()).select_from(ActivationIntervention)) == 0
    assert len(ids) == 1 and len(sent) == 4 + (mode == 'AUTOMATIC')
    assert activation_client.get(f"/api/activations/{activation['id']}").json() == activation


@pytest.mark.parametrize('state', ['PENDING', 'PREPARING', 'SENDING'])
def test_active_request_is_rejected_without_promoting_automatic_source(activation_env, activation_client, state):
    engine = activation_env[0]
    _, path = make_activation(activation_env, activation_client, 'AUTOMATIC')
    with Session(engine) as session:
        job = session.scalars(select(Job)).one()
        job.state = state
        session.commit()
        before = {c.key: getattr(job, c.key) for c in Job.__table__.columns}
    current = activation_client.get(path).json()
    assert current['state'] == state and not current['can_request']
    assert activation_client.post(path, json={'revision': current['revision']}).status_code == 409
    with Session(engine) as session:
        job = session.scalars(select(Job)).one()
        assert {c.key: getattr(job, c.key) for c in Job.__table__.columns} == before


@pytest.mark.parametrize('state', ['FAILED', 'PARTIAL', 'UNCERTAIN', 'CANCELLED'])
def test_terminal_retry_requires_deliberate_current_revision(activation_env, activation_client, state):
    engine = activation_env[0]
    _, path = make_activation(activation_env, activation_client, 'AUTOMATIC')
    with Session(engine) as session:
        job = session.scalars(select(Job)).one()
        job.state = state
        job.revision = 7
        session.commit()
        original_id = job.id
    current = activation_client.get(path).json()
    assert current['state'] == state and current['can_request']
    assert activation_client.post(path, json={'revision': 6, 'confirm_uncertain': True}).status_code == 409
    if state == 'UNCERTAIN':
        denied = activation_client.post(path, json={'revision': 7})
        assert denied.status_code == 422 and 'duplicar' in denied.json()['detail']
    response = activation_client.post(path, json={'revision': 7, 'confirm_uncertain': state == 'UNCERTAIN'})
    assert response.status_code == 202
    assert response.json()['revision'] == 8 and response.json()['state'] == 'PENDING'
    with Session(engine) as session:
        assert session.scalars(select(Job)).one().id == original_id


@pytest.mark.parametrize('missing_event', [False, True])
def test_disabled_and_nonexistent_activation(activation_env, activation_client, missing_event):
    activation, path = make_activation(activation_env, activation_client, 'DISABLED')
    with Session(activation_env[0]) as session:
        if missing_event:
            session.delete(session.get(MailEventConfig, ACTIVATION_EVENT))
            session.commit()
    status = activation_client.get(path).json()
    assert status['mode'] == 'DISABLED' and not status['can_request']
    assert activation_client.post(path, json={'revision': 0}).status_code == 422
    for method in ('get', 'post'):
        kwargs = {'json': {'revision': 0}} if method == 'post' else {}
        assert getattr(activation_client, method)('/api/activations/2147483647/notification', **kwargs).status_code == 404
    with Session(activation_env[0]) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0
        assert session.get(Activation, activation['id']) is not None


@pytest.mark.parametrize('prior_send', [False, True])
def test_concurrent_clicks_create_only_one_intent(activation_env, activation_client, monkeypatch, prior_send):
    engine = activation_env[0]
    _, path = make_activation(activation_env, activation_client)
    sent = accepted_transport(monkeypatch)
    if prior_send:
        assert activation_client.post(path, json={'revision': 0}).status_code == 202
        assert processor.NotificationProcessor(engine).run_once()
    revision = activation_client.get(path).json()['revision']
    barrier = Barrier(6)
    def request(_):
        barrier.wait(timeout=10)
        return activation_client.post(path, json={'revision': revision}).status_code
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(request, range(6)))
    assert responses.count(202) == 1 and responses.count(409) == 5
    assert processor.NotificationProcessor(engine).run_once()
    assert activation_client.post(path, json={'revision': revision}).status_code == 409
    assert len(sent) == 1 + prior_send
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 1


def test_paused_processor_queues_without_authorizing_resume(activation_env, activation_client):
    engine = activation_env[0]
    _, path = make_activation(activation_env, activation_client)
    with Session(engine) as session:
        control = session.get(MailProcessorControl, 1)
        control.paused = True
        session.commit()
    assert activation_client.get(path).json()['can_request']
    response = activation_client.post(path, json={'revision': 0})
    assert response.status_code == 202 and response.json()['processor_paused']
    assert 'pausado' in response.json()['message']
    assert not processor.NotificationProcessor(engine).run_once()
    with Session(engine) as session:
        assert session.get(MailProcessorControl, 1).paused
        assert session.scalars(select(Job)).one().state == 'PENDING'


@pytest.mark.parametrize('problem', ['host', 'sender', 'password', 'plaintext_auth', 'recipients', 'invalid_address',
                                    'template', 'empty_template', 'unknown_field', 'oauth_authorization'])
def test_invalid_configuration_is_readable_and_rejected_without_job(activation_env, activation_client, problem):
    engine = activation_env[0]
    _, path = make_activation(activation_env, activation_client)
    with Session(engine) as session:
        event = session.get(MailEventConfig, ACTIVATION_EVENT)
        row = session.get(MailTransportConfig, 1)
        if problem == 'host': row.host = None
        elif problem == 'sender': row.sender_email = None
        elif problem == 'password': row.auth_method = 'PASSWORD'; row.username = 'smtp-user'
        elif problem == 'plaintext_auth':
            row.security = 'NONE'; row.allow_unencrypted = True; row.auth_method = 'PASSWORD'
            row.username = 'smtp-user'; row.smtp_password_encrypted = 'opaque-secret'
        elif problem == 'recipients': event.to_recipients = []
        elif problem == 'invalid_address': event.to_recipients = ['not-an-email']
        elif problem == 'template': event.template = None
        elif problem == 'empty_template': event.template = {'subject': [], 'body': []}
        elif problem == 'unknown_field': event.template = {'body': [{'type': 'field', 'field_id': 'password'}]}
        elif problem == 'oauth_authorization':
            row.auth_method = 'OAUTH2_DELEGATED'; row.provider = 'GMAIL'; row.username = 'noc@example.com'
            row.oauth_settings = {'client_id': 'client', 'client_secret_configured': True}
            row.oauth_credentials_encrypted = 'opaque-secret'; row.oauth_status = 'REQUIRES_AUTHORIZATION'
        session.commit()
    status = activation_client.get(path)
    assert status.status_code == 200 and status.json()['configuration_error'] and not status.json()['can_request']
    response = activation_client.post(path, json={'revision': 0})
    assert response.status_code == 422
    assert 'opaque-secret' not in status.text + response.text
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0


@pytest.mark.parametrize('method,provider', [
    ('OAUTH2_DELEGATED', 'GMAIL'), ('OAUTH2_DELEGATED', 'OUTLOOK_COM'),
    ('OAUTH2_DELEGATED', 'MICROSOFT_365'), ('OAUTH2_APPLICATION', 'GOOGLE_WORKSPACE'),
    ('OAUTH2_APPLICATION', 'MICROSOFT_365'), ('PASSWORD', None),
])
def test_preflight_does_not_decrypt_or_refresh_credentials(activation_env, activation_client, monkeypatch, tmp_path, method, provider):
    monkeypatch.setenv('MAIL_KEYS_PATH', str(tmp_path/'missing-keys.json'))
    from ticketyn.core.config import get_settings
    get_settings.cache_clear()
    engine = activation_env[0]
    _, path = make_activation(activation_env, activation_client)
    with Session(engine) as session:
        row = session.get(MailTransportConfig, 1)
        row.auth_method = method; row.provider = provider; row.username = 'noc@example.com'
        row.smtp_password_encrypted = 'encrypted-placeholder'
        row.oauth_credentials_encrypted = 'encrypted-placeholder'
        row.oauth_settings = {'client_id': 'client', 'tenant_id': 'tenant',
                              'client_secret_configured': True, 'service_account_configured': True}
        row.oauth_status = 'CONNECTED'
        session.commit()
    status = activation_client.get(path)
    assert status.json()['can_request']
    response = activation_client.post(path, json={'revision': 0})
    assert response.status_code == 202 and 'encrypted-placeholder' not in status.text + response.text


def test_historical_activation_uses_current_template_and_recipients(activation_env, activation_client, monkeypatch):
    engine = activation_env[0]
    activation, path = make_activation(activation_env, activation_client)
    with Session(engine) as session:
        session.get(MailEventConfig, ACTIVATION_EVENT).mode = 'AUTOMATIC'
        session.commit()
    assert activation_client.get(path).json()['state'] is None
    assert activation_client.post(path, json={'revision': 0}).status_code == 202
    with Session(engine) as session:
        event = session.get(MailEventConfig, ACTIVATION_EVENT)
        event.template = {'subject': [{'type': 'text', 'text': 'Plantilla vigente'}],
                          'body': [{'type': 'field', 'field_id': 'activation.activation_notes'}]}
        event.to_recipients = ['current@example.com']; event.bcc_recipients = ['hidden@example.com']
        session.get(MailTransportConfig, 1).sender_name = 'Noc actual'
        session.commit()
    sent = accepted_transport(monkeypatch)
    assert processor.NotificationProcessor(engine).run_once()
    _, _, message, sender, recipients = sent[0]
    assert str(message['Subject']) == 'Plantilla vigente'
    assert 'NOTAS DE ACTIVACIÓN:\n' in message.get_body(preferencelist=('plain',)).get_content().replace('\r\n', '\n')
    assert recipients == ['current@example.com', 'hidden@example.com'] and message['Bcc'] is None
    assert str(message['From']).startswith('Noc actual')
    assert activation_client.get(f"/api/activations/{activation['id']}").json() == activation


@pytest.mark.parametrize('body', [{'revision': -1}, {'revision': True}, {'revision': '0'}, {},
                                  {'revision': 0, 'confirm_uncertain': 'yes'},
                                  {'revision': 0, 'to': ['arbitrary@example.com'], 'subject': 'private-input'}])
def test_request_contract_is_strict_and_secret_safe(activation_env, activation_client, body):
    _, path = make_activation(activation_env, activation_client)
    response = activation_client.post(path, json=body)
    assert response.status_code == 422 and 'private-input' not in response.text


@pytest.mark.parametrize('prior_send', [False, True])
def test_failed_persistence_rolls_back_intent_without_changing_fms(activation_env, activation_client, monkeypatch, prior_send):
    from sqlalchemy.exc import SQLAlchemyError
    from ticketyn.api import activation_notifications as api
    engine = activation_env[0]
    activation, path = make_activation(activation_env, activation_client)
    accepted_transport(monkeypatch)
    if prior_send:
        assert activation_client.post(path, json={'revision': 0}).status_code == 202
        assert processor.NotificationProcessor(engine).run_once()
    revision = activation_client.get(path).json()['revision']
    with Session(engine) as session:
        before = operation_snapshot(session, activation['id'])
        job = session.scalars(select(Job)).one_or_none()
        previous_job = {c.key: getattr(job, c.key) for c in Job.__table__.columns} if job else None
    original = api.request_notification
    def failing_request(*args, **kwargs):
        original(*args, **kwargs)
        raise SQLAlchemyError('private-database-diagnostic')
    monkeypatch.setattr(api, 'request_notification', failing_request)
    response = activation_client.post(path, json={'revision': revision})
    assert response.status_code == 503 and 'private-database-diagnostic' not in response.text
    with Session(engine) as session:
        job = session.scalars(select(Job)).one_or_none()
        assert ({c.key: getattr(job, c.key) for c in Job.__table__.columns} if job else None) == previous_job
        assert operation_snapshot(session, activation['id']) == before
