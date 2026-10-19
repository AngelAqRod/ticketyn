"""Administrative configuration only; trusted-network access, no mail delivery."""
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text

from test_e2e_update_migration import cli
from test_fms import create, operation_payload  # noqa: F401
from ticketyn.core.config import get_settings
from ticketyn.core.secret_store import SecretCipher, create_key_file
from ticketyn.models import Activation, CapacityChange
from ticketyn.models.mail_notifications import MailEventConfig, MailTransportConfig
from ticketyn.notifications.fields import ACTIVATION_EVENT, ACTIVATION_FIELDS

BASE = '/api/mail-notifications'
EVENT = BASE + '/events/' + ACTIVATION_EVENT
PASSWORD = 'Synthetic-SMTP-secret-NOT-a-real-password'
SMTP = {'host': 'smtp.example.com', 'sender_email': 'noc@example.com'}


@pytest.fixture(autouse=True)
def no_smtp_or_dns(monkeypatch):
    import smtplib
    import dns.resolver
    def forbidden(*args, **kwargs): raise AssertionError('No SMTP or DNS operation is permitted in stage 3')
    monkeypatch.setattr(smtplib, 'SMTP', forbidden)
    monkeypatch.setattr(smtplib, 'SMTP_SSL', forbidden)
    monkeypatch.setattr(dns.resolver, 'resolve', forbidden)


@pytest.fixture
def keys(tmp_path, monkeypatch):
    path = tmp_path / 'keys.json'
    create_key_file(path)
    monkeypatch.setenv('MAIL_KEYS_PATH', str(path))
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


def configure(api_client, **values):
    response = api_client.patch(BASE + '/smtp', json={**SMTP, **values})
    assert response.status_code == 200, response.text
    return response.json()


def test_defaults_without_keys_or_configuration(api_client):
    response = api_client.get(BASE + '/smtp')
    assert response.status_code == 200
    assert response.json()['configured'] is False
    assert response.json()['password_configured'] is False
    events = api_client.get(BASE + '/events').json()
    assert events == [{'event_key': ACTIVATION_EVENT, 'label': 'Registro de activación FMS', 'mode': 'DISABLED', 'to': [], 'cc': [], 'bcc': []}]
    assert api_client.get(EVENT).json() == events[0]
    assert api_client.get(EVENT + '/fields').status_code == 200


def test_create_and_patch_without_password(api_client):
    row = configure(api_client, port=465, security='IMPLICIT_TLS', sender_name='NOC')
    assert row['port'] == 465 and row['auth_method'] == 'NONE'
    response = api_client.patch(BASE + '/smtp', json={'sender_name': 'NOC actualizado'})
    assert response.status_code == 200
    assert response.json()['host'] == SMTP['host']
    assert response.json()['sender_name'] == 'NOC actualizado'
    assert api_client.get(BASE + '/smtp').json() == response.json()


def test_password_encrypted_never_returned_and_preserved_on_partial_update(api_client, db_session, keys, caplog):
    result = configure(api_client, auth_method='PASSWORD', username='smtp-user', smtp_password=PASSWORD)
    assert result['password_configured']
    stored = db_session.get(MailTransportConfig, 1).smtp_password_encrypted
    assert stored and PASSWORD not in stored
    assert SecretCipher(keys).decrypt(stored, context='mail:transport:1:smtp-password') == PASSWORD
    response = api_client.patch(BASE + '/smtp', json={'port': 2525})
    assert response.status_code == 200
    assert db_session.get(MailTransportConfig, 1).smtp_password_encrypted == stored
    for body in (result, response.json(), api_client.get(BASE + '/smtp').json()):
        assert PASSWORD not in json.dumps(body) and stored not in json.dumps(body)
        assert 'smtp_password' not in body and 'smtp_password_encrypted' not in body
    assert PASSWORD not in caplog.text
    keys.unlink()
    # Queries and metadata-only changes never need decryption, even with a saved credential.
    assert api_client.get(BASE + '/smtp').json()['password_configured']
    assert api_client.patch(BASE + '/smtp', json={'sender_name': 'Sin clave presente'}).status_code == 200
    assert db_session.get(MailTransportConfig, 1).smtp_password_encrypted == stored
    response = api_client.patch(BASE + '/smtp', json={'smtp_password': 'replacement', 'sender_name': 'No guardar'})
    assert response.status_code == 503
    assert api_client.get(BASE + '/smtp').json()['sender_name'] == 'Sin clave presente'
    assert db_session.get(MailTransportConfig, 1).smtp_password_encrypted == stored


def test_missing_key_rejects_encryption_atomically(api_client, monkeypatch, tmp_path):
    monkeypatch.setenv('MAIL_KEYS_PATH', str(tmp_path / 'missing.json')); get_settings.cache_clear()
    try:
        response = api_client.patch(BASE + '/smtp', json={**SMTP, 'auth_method': 'PASSWORD', 'username': 'user', 'smtp_password': PASSWORD})
        assert response.status_code == 503 and PASSWORD not in response.text
        assert not api_client.get(BASE + '/smtp').json()['configured']
        assert api_client.patch(EVENT, json={'mode': 'MANUAL', 'to': ['noc@example.com']}).status_code == 200
    finally: get_settings.cache_clear()


@pytest.mark.parametrize('payload', [
    {'port': 0}, {'port': 65536}, {'port': True}, {'port': '587'}, {'port': 2.5},
    {'security': 'SSL'}, {'security': None}, {'auth_method': 'LOGIN'},
    {'auth_method': 'PASSWORD'}, {'auth_method': 'PASSWORD', 'username': 'user'},
    {'host': 'smtp://example.com'}, {'host': 'host:25'}, {'host': 'bad host'}, {'host': ''},
    {'sender_email': 'not-an-email'}, {'sender_email': 'a@example.com\r\nBcc: bad@example.com'},
    {'sender_name': 'NOC\nInjected'}, {'smtp_password': PASSWORD},
    {'smtp_password': None}, {'smtp_password': ''}, {'clear_password': None},
    {'security': 'NONE'}, {'oauth_credentials_encrypted': 'forbidden'},
    {'oauth_refresh_token': PASSWORD}, {'tls_verify': False},
    {'auth_method': 'OAUTH2_DELEGATED'},
    {'auth_method': 'OAUTH2_APPLICATION', 'provider': 'GMAIL'},
    {'auth_method': 'OAUTH2_APPLICATION', 'provider': 'OUTLOOK_COM'},
])
def test_invalid_transport_input_is_rejected(api_client, payload, caplog):
    response = api_client.patch(BASE + '/smtp', json={**SMTP, **payload})
    assert response.status_code == 422, response.text
    assert PASSWORD not in response.text + caplog.text
    assert not api_client.get(BASE + '/smtp').json()['configured']


@pytest.mark.parametrize('security,port', [('STARTTLS', 587), ('IMPLICIT_TLS', 465), ('NONE', 25)])
def test_security_profiles_without_network(api_client, security, port):
    result = configure(api_client, security=security, port=port, allow_unencrypted=security == 'NONE')
    assert result['security'] == security and result['port'] == port


@pytest.mark.parametrize('method,provider', [
    ('OAUTH2_DELEGATED', 'GMAIL'), ('OAUTH2_DELEGATED', 'GOOGLE_WORKSPACE'),
    ('OAUTH2_DELEGATED', 'OUTLOOK_COM'), ('OAUTH2_DELEGATED', 'MICROSOFT_365'),
    ('OAUTH2_APPLICATION', 'GOOGLE_WORKSPACE'), ('OAUTH2_APPLICATION', 'MICROSOFT_365'),
])
def test_oauth_profile_can_be_saved_without_connecting(api_client, method, provider):
    result = configure(api_client, auth_method=method, provider=provider)
    assert result['auth_method'] == method and result['provider'] == provider
    assert not result['oauth_credentials_configured']


def test_clear_password_is_explicit_and_cannot_break_password_auth(api_client, db_session, keys):
    configure(api_client, auth_method='PASSWORD', username='user', smtp_password=PASSWORD)
    original = db_session.get(MailTransportConfig, 1).smtp_password_encrypted
    assert api_client.patch(BASE + '/smtp', json={'clear_password': True}).status_code == 422
    assert db_session.get(MailTransportConfig, 1).smtp_password_encrypted == original
    assert api_client.patch(BASE + '/smtp', json={'smtp_password': 'other', 'clear_password': True}).status_code == 422
    assert api_client.patch(BASE + '/smtp', json={'auth_method': 'NONE'}).json()['password_configured']
    assert api_client.patch(BASE + '/smtp', json={'clear_password': True}).json()['password_configured'] is False
    assert db_session.get(MailTransportConfig, 1).smtp_password_encrypted is None


def test_password_validation_errors_omit_raw_input(api_client, caplog):
    for value in ({'nested': PASSWORD}, [PASSWORD], PASSWORD * 4000):
        response = api_client.patch(BASE + '/smtp', json={**SMTP, 'auth_method': 'PASSWORD', 'username': 'user', 'smtp_password': value})
        assert response.status_code == 422
        assert PASSWORD not in response.text + caplog.text
        assert all('input' not in error and 'ctx' not in error for error in response.json()['detail'])


def test_recipient_groups_deduplicated_stable_and_independent(api_client, db_session):
    response = api_client.patch(EVENT, json={'to': ['noc@example.com', 'NOC@example.com', 'other@example.com'], 'cc': ['noc@example.com', 'cc@example.com'], 'bcc': ['hidden@example.com', 'HIDDEN@example.com']})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['to'] == ['noc@example.com', 'other@example.com']
    assert result['cc'] == ['noc@example.com', 'cc@example.com']
    assert result['bcc'] == ['hidden@example.com']
    assert api_client.patch(EVENT, json={'to': []}).json() == {**result, 'to': []}
    row = db_session.get(MailEventConfig, ACTIVATION_EVENT)
    assert row.to_recipients == [] and row.bcc_recipients == ['hidden@example.com']


@pytest.mark.parametrize('group', ['to', 'cc', 'bcc'])
@pytest.mark.parametrize('value', [None, 'noc@example.com', ['bad address'], ['noc@example.com\nBcc: x@example.com'], [str(i)+'@example.com' for i in range(101)]])
def test_invalid_recipients(api_client, group, value):
    assert api_client.patch(EVENT, json={group: value}).status_code == 422
    assert api_client.get(EVENT).json()['mode'] == 'DISABLED'


def test_modes_persist_without_enabling_other_events_or_delivery(api_client):
    for mode in ('AUTOMATIC', 'MANUAL', 'DISABLED', 'AUTOMATIC'):
        assert api_client.patch(EVENT, json={'mode': mode}).json()['mode'] == mode
        assert api_client.get(EVENT).json()['mode'] == mode
    assert api_client.patch(EVENT, json={'mode': 'ENABLED'}).status_code == 422
    assert api_client.patch(BASE + '/events/capacity.created', json={'mode': 'AUTOMATIC'}).status_code == 404
    assert api_client.get(BASE + '/events/capacity.created/fields').status_code == 404
    assert len(api_client.get(BASE + '/events').json()) == 1


def test_fields_come_from_real_attributes_and_distinguish_history(api_client):
    response = api_client.get(EVENT + '/fields')
    assert response.status_code == 200
    fields = response.json(); by_id = {field['id']: field for field in fields}
    assert len(by_id) == len(fields) == len(ACTIVATION_FIELDS)
    assert {field['group'] for field in fields} == {'Activación FMS', 'Circuito', 'Cliente'}
    assert by_id['activation.activation_notes']['source_paths'] == ['Activation.activation_notes']
    assert by_id['activation.initial_capacity']['temporality'] == 'HISTORICAL'
    assert by_id['circuit.current_capacity']['temporality'] == 'CURRENT'
    assert by_id['circuit.current_capacity']['resolver'] == 'latest_capacity_effective_now_or_initial'
    for field in fields:
        for source in field['source_paths']:
            head, *parts = source.split('.')
            model = {'Activation': Activation, 'CapacityChange': CapacityChange}[head]
            for index, part in enumerate(parts):
                attribute = getattr(model, part)
                if index < len(parts) - 1: model = attribute.property.mapper.class_
    assert all('cpe_configuration' not in source for field in fields for source in field['source_paths'])


def test_automatic_intent_preserves_fms_and_configuration(api_client, operation_payload, db_session):
    configure(api_client)
    assert api_client.patch(EVENT, json={'mode': 'AUTOMATIC', 'to': ['noc@example.com']}).status_code == 200
    before = api_client.get(EVENT).json()
    row = create(api_client, '/api/activations', {**operation_payload, 'activation_notes': 'Histórico intacto'})
    assert api_client.get(f"/api/activations/{row['id']}").json() == row
    assert api_client.get(f"/api/activations/{row['id']}/interventions").json() == []
    assert api_client.get(EVENT).json() == before
    tables = set(inspect(db_session.connection()).get_table_names())
    assert not {'mail_delivery_work', 'mail_jobs', 'mail_messages'} & tables
    paths = api_client.get('/openapi.json').json()['paths']
    assert not any('/activations/' in path and '/send' in path for path in paths)


def test_real_migration_and_safe_downgrade(postgres_engine):
    database = 'mail_config_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE ' + database))
    engine = create_engine(postgres_engine.url.set(database=database))
    try:
        cli(engine.url, 'upgrade', '0025_activation_notes')
        with engine.begin() as db:
            db.execute(text("INSERT INTO customers(id,customer_code,name) VALUES(1,'C','Cliente')"))
            db.execute(text("INSERT INTO responsibles(id,name) VALUES(1,'Operador')"))
            db.execute(text("INSERT INTO circuits(id,customer_id,circuit_code,description) VALUES(1,1,'C-1','Conservar')"))
            db.execute(text("INSERT INTO activations(circuit_id,responsible_id,effective_at,activation_number,reference,activation_notes) VALUES(1,1,'2020-01-01T00:00:00Z',1,'ACT-1','Notas históricas')"))
            before = db.scalar(text('SELECT to_jsonb(a) FROM activations a'))
        cli(engine.url, 'upgrade', '0026_mail_configuration'); cli(engine.url, 'upgrade', '0026_mail_configuration')
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0026_mail_configuration'
            assert db.scalar(text('SELECT to_jsonb(a) FROM activations a')) == before
            assert db.scalar(text('SELECT mode FROM mail_event_config')) == 'DISABLED'
            assert db.scalar(text('SELECT host FROM mail_transport_config')) is None
            assert db.scalar(text('SELECT smtp_password_encrypted FROM mail_transport_config')) is None
        cli(engine.url, 'downgrade', '0025_activation_notes')
        assert 'mail_transport_config' not in inspect(engine).get_table_names()
        cli(engine.url, 'upgrade', '0026_mail_configuration')
        with engine.begin() as db:
            db.execute(text("UPDATE mail_event_config SET to_recipients='[\"noc@example.com\"]'::jsonb"))
        result = subprocess.run([sys.executable, '-B', '-m', 'alembic', 'downgrade', '0025_activation_notes'],
            cwd=Path(__file__).resolve().parents[1], env={**os.environ, 'DATABASE_URL': engine.url.render_as_string(hide_password=False)}, capture_output=True, text=True, timeout=30)
        assert result.returncode != 0 and 'Downgrade inseguro' in result.stderr
        with engine.connect() as db:
            assert db.scalar(text('SELECT to_recipients FROM mail_event_config')) == ['noc@example.com']
            assert db.scalar(text('SELECT to_jsonb(a) FROM activations a')) == before
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE ' + database))
