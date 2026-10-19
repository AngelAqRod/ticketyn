"""SMTP/OAuth tests use synthetic credentials, fixed fakes and disposable PostgreSQL."""
import json
import logging
import smtplib
import ssl
import time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from ticketyn.notifications import smtp, oauth
from ticketyn.core.config import get_settings, Settings
from ticketyn.models.mail_notifications import MailTransportConfig, MailEventConfig
from ticketyn.notifications.coordination import claim_test, release_test
from ticketyn.api import mail_transport
from test_mail_notifications import keys, configure, BASE, EVENT  # noqa: F401
from test_fms import create, operation_payload  # noqa: F401
from test_ticket_concurrency import concurrent_database  # noqa: F401
from test_e2e_update_migration import cli

CLIENT = '11111111-1111-4111-8111-111111111111'
TENANT = '22222222-2222-4222-8222-222222222222'
SECRET = 'synthetic-only-application-secret'
ACCESS = 'synthetic-only-access-token'
REFRESH = 'synthetic-only-refresh-token'
REDIRECT = 'http://localhost:5173/api/mail-notifications/oauth/callback'
TOKEN_REQUEST = oauth.token_request


class FakeSMTP:
    instances = []
    failure = None
    fail_phase = ''
    advertise_tls = True
    partial = False

    def __init__(self, **kwargs):
        self.kwargs = kwargs; self.actions = []; self.closed = False; self.sent = None
        self.instances.append(self)
    def action(self, phase):
        self.actions.append(phase)
        if self.fail_phase == phase: raise self.failure
    def connect(self, host, port):
        self.action('connect'); self.host = host; self.port = port; return 220, b'OK'
    def ehlo_or_helo_if_needed(self): self.action('ehlo')
    def ehlo(self): self.action('ehlo')
    def has_extn(self, extension): return self.advertise_tls
    def starttls(self, *, context):
        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        self.action('tls')
    def login(self, username, password): self.action('auth'); self.login_values = (username, password)
    def auth(self, mechanism, response):
        assert mechanism == 'XOAUTH2'
        self.auth_value = response(); assert response(b'provider challenge') == ''
        self.action('auth')
    def send_message(self, message, **kwargs):
        self.action('data'); self.sent = (message, kwargs)
        return {'other@example.com': (550, b'no')} if self.partial else {}
    def quit(self): self.action('quit')
    def close(self): self.closed = True


@pytest.fixture(autouse=True)
def isolated_network(monkeypatch):
    FakeSMTP.instances = []; FakeSMTP.failure = None; FakeSMTP.fail_phase = ''; FakeSMTP.advertise_tls = True; FakeSMTP.partial = False
    monkeypatch.setattr(smtplib, 'SMTP', FakeSMTP); monkeypatch.setattr(smtplib, 'SMTP_SSL', FakeSMTP)
    def forbidden(*args, **kwargs): raise AssertionError('Real OAuth network requests are forbidden in automated tests')
    monkeypatch.setattr(oauth, 'token_request', forbidden)


def message():
    return smtp.build_message(sender_email='noc@example.com', sender_name='NOC áé', to=['to@example.com'], cc=['cc@example.com'], bcc=['hidden@example.com'], subject='Prueba técnica', body='Datos:\nPrimero\nSegundo\n\nFirma')


@pytest.mark.parametrize(('security', 'auth'), [('NONE', 'NONE'), ('STARTTLS', 'NONE'), ('STARTTLS', 'PASSWORD'), ('IMPLICIT_TLS', 'PASSWORD'), ('STARTTLS', 'OAUTH2_DELEGATED'), ('IMPLICIT_TLS', 'OAUTH2_APPLICATION')])
def test_transport_modes_and_close(security, auth):
    result = smtp.send_message(smtp.TransportSettings('smtp.example.com', 25, security, auth, 'noc@example.com', security == 'NONE'), smtp.Credentials(password=SECRET, access_token=ACCESS), *message())
    assert result.status == 'ACCEPTED'
    instance = FakeSMTP.instances[-1]
    assert instance.closed and instance.actions[-1] == 'quit' and instance.kwargs['timeout'] == 20
    assert ('tls' in instance.actions) == (security == 'STARTTLS')
    if security == 'STARTTLS': assert instance.actions.index('tls') < instance.actions.index('data')
    if security == 'IMPLICIT_TLS':
        assert instance.kwargs['context'].check_hostname and instance.kwargs['context'].verify_mode == ssl.CERT_REQUIRED
    if auth == 'PASSWORD': assert instance.login_values == ('noc@example.com', SECRET)
    if auth.startswith('OAUTH2'): assert instance.auth_value == f'user=noc@example.com\x01auth=Bearer {ACCESS}\x01\x01'
    assert ACCESS not in repr(smtp.Credentials(access_token=ACCESS))


def test_starttls_does_not_downgrade():
    FakeSMTP.advertise_tls = False
    with pytest.raises(smtp.MailFailure, match='TLS'):
        smtp.send_message(smtp.TransportSettings('smtp.example.com', 587, 'STARTTLS', 'PASSWORD', 'user'), smtp.Credentials(password=SECRET), *message())
    assert FakeSMTP.instances[-1].closed
    assert 'auth' not in FakeSMTP.instances[-1].actions and 'data' not in FakeSMTP.instances[-1].actions


@pytest.mark.parametrize('security', ['STARTTLS', 'IMPLICIT_TLS'])
def test_tls_peer_hostname_is_preserved_with_python_311_connect(monkeypatch, security):
    class LegacySMTP(FakeSMTP):
        # Python 3.11 stores _host only in __init__, not in connect(). Both
        # starttls() and SMTP_SSL._get_socket() use it for verified TLS/SNI.
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._host = ''
        def connect(self, host, port):
            if security == 'IMPLICIT_TLS':
                assert self._host == host
            return super().connect(host, port)
        def starttls(self, *, context):
            assert self._host == self.host
            super().starttls(context=context)
    monkeypatch.setattr(smtplib, 'SMTP', LegacySMTP)
    monkeypatch.setattr(smtplib, 'SMTP_SSL', LegacySMTP)
    result = smtp.send_message(smtp.TransportSettings('smtp.example.com', 587, security, 'PASSWORD', 'noc@example.com'),
                               smtp.Credentials(password=SECRET), *message())
    assert result.status == 'ACCEPTED' and FakeSMTP.instances[-1].closed


@pytest.mark.parametrize('auth', ['PASSWORD', 'OAUTH2_DELEGATED', 'OAUTH2_APPLICATION'])
def test_no_credentials_over_cleartext(auth):
    with pytest.raises(smtp.MailFailure):
        smtp.send_message(smtp.TransportSettings('localhost', 25, 'NONE', auth, 'user', True), smtp.Credentials(password=SECRET, access_token=ACCESS), *message())
    assert not FakeSMTP.instances


@pytest.mark.parametrize(('phase', 'failure', 'expected'), [
    ('connect', TimeoutError(SECRET), 'CONNECTION_ERROR'), ('connect', ssl.SSLError(SECRET), 'TLS_ERROR'),
    ('tls', ssl.SSLCertVerificationError(SECRET), 'TLS_ERROR'),
    ('tls', smtplib.SMTPResponseException(454, SECRET.encode()), 'TLS_ERROR'),
    ('auth', smtplib.SMTPAuthenticationError(535, SECRET.encode()), 'AUTH_ERROR'),
    ('auth', smtplib.SMTPNotSupportedError(SECRET), 'AUTH_ERROR'),
    ('data', smtplib.SMTPRecipientsRefused({'x': (550, SECRET)}), 'RECIPIENT_REJECTED'),
    ('data', smtplib.SMTPDataError(554, SECRET.encode()), 'MESSAGE_REJECTED'),
    ('data', smtplib.SMTPSenderRefused(550, SECRET.encode(), 'noc@example.com'), 'MESSAGE_REJECTED'),
    ('data', TimeoutError(SECRET), 'UNCERTAIN'), ('data', smtplib.SMTPServerDisconnected(SECRET), 'UNCERTAIN'),
    ('quit', TimeoutError(SECRET), 'ACCEPTED'),
])
def test_safe_error_classification_without_retries(phase, failure, expected, caplog):
    FakeSMTP.fail_phase = phase; FakeSMTP.failure = failure
    result = smtp.send_message(smtp.TransportSettings('smtp.example.com', 587, 'STARTTLS', 'PASSWORD', 'noc@example.com'), smtp.Credentials(password=SECRET), *message())
    assert result.status == expected and SECRET not in result.message and SECRET not in caplog.text
    assert len(FakeSMTP.instances) == 1 and FakeSMTP.instances[0].closed
    assert FakeSMTP.instances[0].actions.count('data') <= 1


def test_mime_bcc_utf8_and_exact_line_structure():
    mail, sender, envelope = message()
    assert sender == 'noc@example.com'
    assert envelope == ['to@example.com', 'cc@example.com', 'hidden@example.com']
    assert mail['Bcc'] is None and 'hidden@example.com' not in mail.as_string()
    assert str(mail['Subject']) == 'Prueba técnica'
    assert mail.get_content().replace('\r\n', '\n') == 'Datos:\nPrimero\nSegundo\n\nFirma\n'
    assert mail.get_content_type() == 'text/plain' and mail.get_content_charset() == 'utf-8'


@pytest.mark.parametrize('changes', [{'subject': 'Hi\r\nBcc: evil@example.com'}, {'sender_name': 'NOC\nX:bad'}, {'to': ['a@example.com\nBcc:b@example.com']}, {'bcc': ['invalid']}, {'sender_email': 'bad'}, {'to': []}])
def test_mime_rejects_invalid_headers(changes):
    values = dict(sender_email='noc@example.com', sender_name='NOC', to=['to@example.com'], subject='Prueba', body='Texto')
    values.update(changes)
    with pytest.raises(smtp.MailFailure): smtp.build_message(**values)


@pytest.fixture
def oauth_config(api_client, keys, monkeypatch):
    monkeypatch.setenv('MAIL_OAUTH_REDIRECT_URI', REDIRECT); get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def delegated(api_client, provider='GMAIL'):
    configure(api_client, auth_method='OAUTH2_DELEGATED', provider=provider, username='noc@example.com')
    payload = {'client_id': CLIENT, 'client_secret': SECRET}
    if provider == 'MICROSOFT_365': payload['tenant_id'] = TENANT
    response = api_client.patch(BASE + '/oauth', json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def authorize(api_client):
    result = api_client.post(BASE + '/oauth/authorize')
    assert result.status_code == 200, result.text
    query = parse_qs(urlsplit(result.json()['authorization_url']).query)
    return query['state'][0], query


def tokens(): return {'access_token': ACCESS, 'refresh_token': REFRESH, 'expires_at': time.time() + 3600}


@pytest.mark.parametrize('provider', ['GMAIL', 'GOOGLE_WORKSPACE', 'OUTLOOK_COM', 'MICROSOFT_365'])
def test_delegated_flow_pkce_encryption_callback_and_replay(api_client, oauth_config, db_session, monkeypatch, provider, caplog):
    delegated(api_client, provider)
    state, query = authorize(api_client)
    assert query['code_challenge_method'] == ['S256'] and query['redirect_uri'] == [REDIRECT]
    assert ('offline_access' in query['scope'][0]) == provider.startswith(('OUTLOOK', 'MICROSOFT'))
    calls = []
    def exchange(url, data):
        calls.append((url, data)); assert data['code'] == 'synthetic-code'
        assert oauth.b64(__import__('hashlib').sha256(data['code_verifier'].encode()).digest()) == query['code_challenge'][0]
        return tokens()
    monkeypatch.setattr(oauth, 'token_request', exchange)
    response = api_client.get(BASE + '/oauth/callback', params={'state': state, 'code': 'synthetic-code'}, follow_redirects=False)
    assert response.status_code == 303 and response.headers['location'] == '/mail-notifications?oauth=connected'
    assert api_client.get(BASE + '/oauth').json()['status'] == 'CONNECTED'
    assert len(calls) == 1
    assert api_client.patch(BASE + '/oauth', json={}).json()['status'] == 'CONNECTED'
    row = db_session.get(MailTransportConfig, 1)
    assert all(secret not in row.oauth_credentials_encrypted for secret in (SECRET, ACCESS, REFRESH))
    assert oauth.read_credentials(row)['tokens']['refresh_token'] == REFRESH
    for path in ('/oauth', '/smtp'):
        assert all(secret not in api_client.get(BASE + path).text for secret in (SECRET, ACCESS, REFRESH))
    again = api_client.get(BASE + '/oauth/callback', params={'state': state, 'code': 'synthetic-code'}, follow_redirects=False)
    assert again.headers['location'].endswith('error') and len(calls) == 1
    assert SECRET not in caplog.text and ACCESS not in caplog.text


@pytest.mark.parametrize('invalid', ['wrong_state', 'missing_cookie', 'expired', 'duplicate', 'provider_error', 'missing_code'])
def test_invalid_callbacks_do_not_exchange(api_client, oauth_config, db_session, invalid):
    delegated(api_client); state, _ = authorize(api_client)
    params = {'state': state, 'code': 'code'}
    if invalid == 'wrong_state': params['state'] = 'wrong'
    if invalid == 'missing_cookie': api_client.cookies.clear()
    if invalid == 'expired':
        row = db_session.get(MailTransportConfig, 1); data = oauth.read_credentials(row)
        data['pending']['expires_at'] = 0; oauth.save_credentials(row, data); db_session.commit()
    if invalid == 'provider_error': params = {'state': state, 'error': 'access_denied', 'error_description': SECRET}
    if invalid == 'missing_code': params = {'state': state}
    if invalid == 'duplicate': params = [('state', state), ('state', 'bad'), ('code', 'code')]
    response = api_client.get(BASE + '/oauth/callback', params=params, follow_redirects=False)
    assert response.status_code == 303 and response.headers['location'].endswith('error')
    assert SECRET not in response.text and SECRET not in response.headers['location']


def test_refresh_and_revocation_are_safe(api_client, oauth_config, db_session, monkeypatch):
    delegated(api_client)
    row = db_session.get(MailTransportConfig, 1); data = oauth.read_credentials(row)
    data['tokens'] = {**tokens(), 'expires_at': 0}; oauth.save_credentials(row, data); db_session.commit()
    calls = []
    def refresh(url, payload):
        calls.append(payload); assert payload['grant_type'] == 'refresh_token' and payload['refresh_token'] == REFRESH
        return {'access_token': ACCESS, 'refresh_token': None, 'expires_at': time.time() + 3600}
    monkeypatch.setattr(oauth, 'token_request', refresh)
    result = api_client.post(BASE + '/smtp/test', json={'recipient': 'test@example.com'})
    assert result.json()['status'] == 'ACCEPTED', result.text
    assert oauth.read_credentials(row)['tokens']['refresh_token'] == REFRESH
    assert len(calls) == 1
    response = api_client.post(BASE + '/oauth/disconnect')
    assert response.json()['status'] == 'REQUIRES_AUTHORIZATION'
    assert 'tokens' not in oauth.read_credentials(row)
    row.test_not_before = None; row.test_lease_until = None
    data = oauth.read_credentials(row); data['tokens'] = {**tokens(), 'expires_at': 0}; oauth.save_credentials(row, data); db_session.commit()
    def revoked(*args): raise smtp.MailFailure('AUTH_ERROR')
    monkeypatch.setattr(oauth, 'token_request', revoked)
    assert api_client.post(BASE + '/smtp/test', json={'recipient': 'test@example.com'}).json()['status'] == 'AUTH_ERROR'
    assert api_client.get(BASE + '/oauth').json()['status'] == 'AUTH_ERROR'


def service_account():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, {'type': 'service_account', 'client_email': 'service@example.iam.gserviceaccount.com', 'private_key': key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()}


@pytest.mark.parametrize('provider', ['MICROSOFT_365', 'GOOGLE_WORKSPACE'])
def test_application_flows(api_client, oauth_config, db_session, monkeypatch, provider):
    configure(api_client, auth_method='OAUTH2_APPLICATION', provider=provider, username='noc@example.com')
    payload = {'client_id': CLIENT, 'tenant_id': TENANT, 'client_secret': SECRET}
    if provider == 'GOOGLE_WORKSPACE':
        key, account = service_account(); payload = {'service_account': json.dumps(account)}
    response = api_client.patch(BASE + '/oauth', json=payload)
    assert response.status_code == 200, response.text
    captured = []
    def exchange(url, data):
        captured.append(data)
        if provider == 'MICROSOFT_365':
            assert data['grant_type'] == 'client_credentials' and data['scope'] == 'https://outlook.office365.com/.default'
        else:
            from cryptography.hazmat.primitives.asymmetric import padding
            from cryptography.hazmat.primitives import hashes
            import base64
            parts = data['assertion'].split('.')
            decode = lambda value: base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
            claims = json.loads(decode(parts[1])); assert claims['sub'] == 'noc@example.com' and claims['scope'] == oauth.GOOGLE_SCOPE
            assert claims['aud'] == oauth.GOOGLE_TOKEN and claims['exp'] - claims['iat'] == 3600
            key.public_key().verify(decode(parts[2]), '.'.join(parts[:2]).encode(), padding.PKCS1v15(), hashes.SHA256())
        return tokens()
    monkeypatch.setattr(oauth, 'token_request', exchange)
    result = api_client.post(BASE + '/smtp/test', json={'recipient': 'test@example.com'})
    assert result.json()['status'] == 'ACCEPTED', result.text
    assert len(captured) == 1
    row = db_session.get(MailTransportConfig, 1)
    assert SECRET not in row.oauth_credentials_encrypted
    assert FakeSMTP.instances[-1].auth_value.endswith(ACCESS + '\x01\x01')


def test_changed_profile_invalidates_oauth_but_partial_metadata_preserves_it(api_client, oauth_config, db_session):
    delegated(api_client)
    row = db_session.get(MailTransportConfig, 1); previous = row.oauth_credentials_encrypted
    assert api_client.patch(BASE + '/smtp', json={'sender_name': 'NOC updated'}).status_code == 200
    assert db_session.get(MailTransportConfig, 1).oauth_credentials_encrypted == previous
    assert api_client.patch(BASE + '/smtp', json={'provider': 'MICROSOFT_365'}).status_code == 200
    row = db_session.get(MailTransportConfig, 1)
    assert row.oauth_credentials_encrypted is None and row.oauth_settings == {} and row.oauth_status == 'UNCONFIGURED'


def test_oauth_input_validation_missing_key_and_credential_preservation(api_client, oauth_config, keys, db_session):
    delegated(api_client)
    for changes in ({'tenant_id': 'https://evil.test'}, {'client_id': 'malicious/?'}, {'client_secret': ''}, {'client_secret': None}, {'service_account': SECRET}, {'token_url': 'https://evil.test'}):
        result = api_client.patch(BASE + '/oauth', json=changes)
        assert result.status_code == 422 and SECRET not in result.text
    original = oauth.read_credentials(db_session.get(MailTransportConfig, 1))['client_secret']
    assert api_client.patch(BASE + '/oauth', json={}).status_code == 200
    assert oauth.read_credentials(db_session.get(MailTransportConfig, 1))['client_secret'] == original
    keys.unlink()
    assert api_client.get(BASE + '/oauth').status_code == 200
    result = api_client.patch(BASE + '/oauth', json={'client_secret': SECRET})
    assert result.status_code == 503 and SECRET not in result.text


@pytest.mark.parametrize('url', ['http://evil.test/api/mail-notifications/oauth/callback', 'https://good.test/elsewhere', 'https://user:pass@good.test/api/mail-notifications/oauth/callback', 'https://good.test/api/mail-notifications/oauth/callback?x=1', 'https://good.test/api/mail-notifications/oauth/callback#x'])
def test_callback_config_must_be_exact(url):
    with pytest.raises(ValueError): Settings(database_url='postgresql+psycopg://test/test', mail_oauth_redirect_uri=url)


def test_callback_access_logging_is_suppressed():
    filter = mail_transport.CallbackAccessFilter()
    record = logging.LogRecord('uvicorn.access', logging.INFO, '', 1, '%s %s %s %s %s', ('client', 'GET', oauth.CALLBACK_PATH + '?code=secret', '1.1', 303), None)
    assert filter.filter(record) is False
    record.args = ('client', 'GET', '/api/health', '1.1', 200)
    assert filter.filter(record)


def test_test_endpoint_is_limited_fixed_and_independent(api_client, db_session, operation_payload, keys):
    configure(api_client, auth_method='PASSWORD', username='noc', smtp_password=SECRET)
    api_client.patch(EVENT, json={'mode': 'AUTOMATIC', 'to': ['event@example.com'], 'bcc': ['hidden@example.com']})
    before = api_client.get(EVENT).json()
    for payload in ({'recipient': 'bad'}, {'recipient': ['a@example.com']}, {'recipient': 'to@example.com', 'body': SECRET}, {'recipient': 'to@example.com', 'host': 'evil.test'}):
        assert api_client.post(BASE + '/smtp/test', json=payload).status_code == 422
    result = api_client.post(BASE + '/smtp/test', json={'recipient': 'temporary@example.com'})
    assert result.json()['status'] == 'ACCEPTED', result.text
    message, envelope = FakeSMTP.instances[-1].sent
    assert envelope['to_addrs'] == ['temporary@example.com']
    assert 'event@example.com' not in message.as_string() and 'hidden@example.com' not in message.as_string()
    assert 'No corresponde a una activación FMS' in message.get_content()
    assert api_client.get(EVENT).json() == before
    row = db_session.get(MailTransportConfig, 1)
    assert row.test_lease_token is None and row.test_lease_until is None
    assert api_client.post(BASE + '/smtp/test', json={'recipient': 'other@example.com'}).status_code == 429
    assert len(FakeSMTP.instances) == 1
    count = len(FakeSMTP.instances)
    create(api_client, '/api/activations', operation_payload)
    assert len(FakeSMTP.instances) == count
    assert 'temporary@example.com' not in str(row.oauth_settings)
    assert not {'mail_jobs', 'mail_messages', 'mail_delivery_work'} & set(inspect(db_session.connection()).get_table_names())


def test_lease_recovers_after_crash_and_blocks_mutations(api_client, db_session):
    configure(api_client)
    row = db_session.get(MailTransportConfig, 1)
    row.test_lease_until = datetime.now(timezone.utc) + timedelta(minutes=10); row.test_lease_token = 'synthetic-lease'; db_session.commit()
    assert api_client.post(BASE + '/smtp/test', json={'recipient': 'to@example.com'}).status_code == 409
    assert api_client.patch(BASE + '/smtp', json={'port': 465}).status_code == 409
    row.test_lease_until = datetime.now(timezone.utc) - timedelta(seconds=1); row.test_not_before = None; db_session.commit()
    assert api_client.post(BASE + '/smtp/test', json={'recipient': 'to@example.com'}).json()['status'] == 'ACCEPTED'


def test_cross_connection_concurrency(concurrent_database):
    engine, _ = concurrent_database
    with Session(engine) as session:
        session.add(MailTransportConfig(id=1)); session.commit()
    barrier = Barrier(2)
    def claim(_):
        with Session(engine) as session:
            barrier.wait(timeout=10)
            try:
                row, token = claim_test(session); session.commit(); return token
            except __import__('fastapi').HTTPException as error:
                session.rollback(); return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, range(2)))
    assert sum(isinstance(item, str) for item in results) == 1 and 409 in results
    with Session(engine) as session:
        token = next(item for item in results if isinstance(item, str))
        release_test(session, token)
        assert session.get(MailTransportConfig, 1).test_lease_token is None


def test_transport_migration_preserves_config_and_template(postgres_engine):
    database = 'mail_transport_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin: admin.execute(text('CREATE DATABASE ' + database))
    engine = create_engine(postgres_engine.url.set(database=database))
    try:
        cli(engine.url, 'upgrade', '0027_mail_templates')
        with engine.begin() as db:
            db.execute(text("UPDATE mail_transport_config SET host='smtp.example.com',smtp_password_encrypted='opaque-secret'"))
            db.execute(text("UPDATE mail_event_config SET mode='MANUAL',to_recipients='[\"noc@example.com\"]'::jsonb,template=CAST(:value AS jsonb)"), {'value': '{"version":1,"subject":[],"body":[]}'})
            previous = db.scalar(text('SELECT to_jsonb(e) FROM mail_event_config e'))
        cli(engine.url, 'upgrade', '0028_mail_transport')
        with engine.connect() as db:
            assert db.scalar(text('SELECT oauth_status FROM mail_transport_config')) == 'UNCONFIGURED'
            assert db.scalar(text('SELECT smtp_password_encrypted FROM mail_transport_config')) == 'opaque-secret'
            assert db.scalar(text('SELECT to_jsonb(e) FROM mail_event_config e')) == previous
        cli(engine.url, 'downgrade', '0027_mail_templates')
        assert 'oauth_settings' not in {col['name'] for col in inspect(engine).get_columns('mail_transport_config')}
        cli(engine.url, 'upgrade', '0028_mail_transport')
        with engine.begin() as db: db.execute(text("UPDATE mail_transport_config SET oauth_settings='{}'::jsonb,oauth_status='CONNECTED'"))
        with pytest.raises(AssertionError, match='Desconecta'): cli(engine.url, 'downgrade', '0027_mail_templates')
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin: admin.execute(text('DROP DATABASE ' + database))

@pytest.mark.parametrize('payload', [
    {'access_token': ACCESS, 'expires_in': 3600, 'token_type': 'Bearer', 'refresh_token': REFRESH},
    {'access_token': ACCESS, 'expires_in': '3600'},
])
def test_https_token_response_validated_and_posts_no_url_secrets(monkeypatch, payload):
    import io
    captured = []
    class Opener:
        def open(self, request, timeout):
            captured.append((request, timeout)); return io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(oauth, 'build_opener', lambda *handlers: Opener())
    result = TOKEN_REQUEST(oauth.GOOGLE_TOKEN, {'client_secret': SECRET, 'grant_type': 'refresh_token'})
    request, timeout = captured[0]
    assert request.full_url == oauth.GOOGLE_TOKEN and SECRET not in request.full_url
    assert SECRET.encode() in request.data and timeout == 15
    assert result['access_token'] == ACCESS and result['expires_at'] > time.time()


@pytest.mark.parametrize('payload', [[], {}, {'access_token': ACCESS, 'expires_in': 0}, {'access_token': ACCESS, 'expires_in': 9999999}, {'access_token': 'unsafe\nsecret'}, {'access_token': ACCESS, 'token_type': 'Basic'}, {'access_token': ACCESS, 'refresh_token': []}])
def test_malformed_provider_response_is_sanitized(monkeypatch, payload, caplog):
    import io
    class Opener:
        def open(self, *args, **kwargs): return io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(oauth, 'build_opener', lambda *handlers: Opener())
    with pytest.raises(smtp.MailFailure) as error: TOKEN_REQUEST(oauth.GOOGLE_TOKEN, {'client_secret': SECRET})
    assert error.value.status == 'AUTH_ERROR' and SECRET not in str(error.value) and SECRET not in caplog.text


@pytest.mark.parametrize(('code', 'expected'), [(400, 'AUTH_ERROR'), (401, 'AUTH_ERROR'), (403, 'AUTH_ERROR'), (500, 'CONNECTION_ERROR')])
def test_provider_http_errors_never_expose_body(monkeypatch, code, expected):
    import io
    from urllib.error import HTTPError
    class Opener:
        def open(self, *args, **kwargs): raise HTTPError(oauth.GOOGLE_TOKEN, code, SECRET, {}, io.BytesIO(SECRET.encode()))
    monkeypatch.setattr(oauth, 'build_opener', lambda *handlers: Opener())
    with pytest.raises(smtp.MailFailure) as error: TOKEN_REQUEST(oauth.GOOGLE_TOKEN, {'client_secret': SECRET})
    assert error.value.status == expected and SECRET not in str(error.value)
    assert oauth.NoRedirect().redirect_request(None, None, None, None, None, None) is None


def test_credentials_rejected_at_api_for_plaintext(api_client, keys):
    for method in ('PASSWORD', 'OAUTH2_DELEGATED', 'OAUTH2_APPLICATION'):
        result = api_client.patch(BASE + '/smtp', json={'host': 'local.example.com', 'sender_email': 'noc@example.com', 'security': 'NONE', 'allow_unencrypted': True, 'auth_method': method, 'provider': 'MICROSOFT_365', 'username': 'noc@example.com', **({'smtp_password': SECRET} if method == 'PASSWORD' else {})})
        assert result.status_code == 422 and SECRET not in result.text
    assert not FakeSMTP.instances


def test_password_not_reused_with_another_username(api_client, keys):
    configure(api_client, auth_method='PASSWORD', username='first', smtp_password=SECRET)
    assert api_client.patch(BASE + '/smtp', json={'username': 'second'}).status_code == 422
    assert api_client.get(BASE + '/smtp').json()['username'] == 'first'
    assert api_client.patch(BASE + '/smtp', json={'username': 'second', 'smtp_password': 'replacement-synthetic'}).status_code == 200


@pytest.mark.parametrize('notes', [
    None, '', ' \t\r\n ', 'INTERNET CON IP PUBLICA',
    'INTERNET CON IP PUBLICA\n192.0.2.1\nPUERTO: 1 CORE 3',
    'Primero\r\n\r\n  Tercero', '\n  Notas con espacios  \n',
])
@pytest.mark.parametrize('custom_label', [None, 'Detalles técnicos'])
def test_mime_uses_renderer_body_without_changing_section_spacing(api_client, operation_payload, notes, custom_label):
    description = 'Servicio\nDetalle del circuito'
    assert api_client.patch(f"/api/circuits/{operation_payload['circuit_id']}", json={'description': description}).status_code == 200
    activation = create(api_client, '/api/activations', {**operation_payload, 'activation_notes': notes})
    note_block = {'type': 'field', 'field_id': 'activation.activation_notes'}
    if custom_label is not None:
        note_block.update(label_mode='CUSTOM', custom_label=custom_label)
    template = {'subject': [{'type': 'field', 'field_id': 'activation.reference'}], 'body': [
        {'type': 'introduction', 'text': 'Estimados,'}, {'type': 'field', 'field_id': 'activation.reference'},
        note_block, {'type': 'field', 'field_id': 'circuit.description'},
        {'type': 'signature', 'text': 'Saludos,\nNOC'}]}
    response = api_client.post(EVENT + '/preview', json={'activation_id': activation['id'], 'template': template})
    assert response.status_code == 200, response.text
    preview = response.json()
    label = custom_label or 'NOTAS DE ACTIVACIÓN'
    note_section = f'\n{label}:\n{notes}' if notes and notes.strip() else ''
    expected = (f"Estimados,\n\nCORRELATIVO: {activation['reference']}" + note_section +
                f'\nDESCRIPCIÓN DEL CIRCUITO: {description}\n\nSaludos,\nNOC')
    assert preview == {'subject': activation['reference'], 'body': expected}
    mail, sender, recipients = smtp.build_message(sender_email='noc@example.com', sender_name='NOC', to=['test@example.com'], **preview)
    assert str(mail['Subject']) == preview['subject']
    assert mail.get_content().replace('\r\n', '\n').removesuffix('\n') == expected.replace('\r\n', '\n')
    result = smtp.send_message(smtp.TransportSettings('smtp.example.com', 587, 'STARTTLS', 'NONE'),
                               smtp.Credentials(), mail, sender, recipients)
    assert result.status == 'ACCEPTED'
    submitted, _ = FakeSMTP.instances[-1].sent
    assert submitted.get_content().replace('\r\n', '\n').removesuffix('\n') == expected.replace('\r\n', '\n')
    assert api_client.get(f"/api/activations/{activation['id']}").json() == activation
    assert api_client.get(f"/api/activations/{activation['id']}/interventions").json() == []
