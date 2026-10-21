from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import json
import time
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from fastapi import HTTPException
from fastapi.testclient import TestClient
from ticketyn.models import Responsible
from ticketyn.models.security import SecurityRole, SecurityAudit
from ticketyn.security.memory import MemorySecurity, SessionLimit
from ticketyn.security.passwords import hash_password, verify_password, validate_password
from ticketyn.security.service import bootstrap, recover_superadmin, seed_foundation, set_access, change_operational_status, lock_security
from security_helpers import authenticate_test_client, fixture_password


@pytest.fixture
def security_client(db_session, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://unused:unused@127.0.0.1:1/unused')
    from ticketyn.core.config import get_settings
    get_settings.cache_clear()
    from ticketyn.main import create_app
    @contextmanager
    def factory():
        with Session(db_session.get_bind(), join_transaction_mode='create_savepoint') as session:
            yield session
    app = create_app(start_notifications=False, security_session_factory=factory)
    from ticketyn.db.session import get_session
    def operational_session():
        yield db_session
    app.dependency_overrides[get_session] = operational_session
    with TestClient(app) as client:
        yield client, app, factory
    get_settings.cache_clear()


def make_account(factory, *, temporary=False, role='SUPERADMIN', active=True, grant=True):
    with factory() as session:
        seed_foundation(session)
        if role == 'CUSTOM':
            custom = SecurityRole(name='Rol personalizado sin permisos')
            session.add(custom); session.flush(); role_id = custom.id
        else:
            role_id = session.scalar(select(SecurityRole.id).where(SecurityRole.code == role))
        account = Responsible(name='Security test', username='Tester', active=active, access_granted=grant, password_hash=fixture_password(), password_change_required=temporary, security_role_id=role_id)
        session.add(account); session.flush(); id = account.id; session.commit()
        return id


def login(client, password='test-only-password', username='Tester'):
    return client.post('/api/auth/login', json={'username': username, 'password': password})


def authorize(client, response):
    assert response.status_code == 200, response.text
    client.headers['Authorization'] = 'Bearer ' + response.json()['token']


def test_argon_parameters_and_password_rules():
    encoded = hash_password('  á\n ')
    assert '$argon2id$v=19$m=65536,t=3,p=4$' in encoded
    assert verify_password(encoded, '  á\n ')
    assert not verify_password(encoded, 'á')
    assert validate_password('x') == 'x'
    assert validate_password('ü' * 2048)
    for value in ['', 'ü' * 2049]:
        with pytest.raises(ValueError): validate_password(value)


def test_bootstrap_duplicate_and_audit(security_client):
    client, app, factory = security_client
    with factory() as session:
        person = Responsible(name='Existing historical person'); session.add(person); session.flush(); id = person.id
        bootstrap(session, id, 'First', 'x'); session.commit()
    with factory() as session:
        row = session.get(Responsible, id)
        assert row.name == 'Existing historical person' and row.password_change_required and row.access_granted
        assert session.scalar(select(SecurityAudit.event)) == 'BOOTSTRAP_SUPERADMIN'
        with pytest.raises(ValueError): bootstrap(session, id, 'Other', 'x')


def test_login_generic_errors_and_no_secrets(security_client, caplog):
    client, app, factory = security_client
    make_account(factory)
    for username in ['Tester', 'Nobody']:
        response = login(client, 'incorrect-sensitive-password', username)
        assert response.status_code == 401
        assert response.json()['detail'] == 'Usuario o contraseña incorrectos'
        assert 'incorrect-sensitive-password' not in response.text
    assert login(client, '').status_code == 422
    response = login(client, 'x' * 4097)
    assert response.status_code == 422 and 'xxxx' not in response.text
    assert 'incorrect-sensitive-password' not in caplog.text
    authorize(client, login(client, username='tEsTeR'))
    response = client.get('/api/auth/me')
    assert response.status_code == 200
    assert not any(key in response.json() for key in ['password_hash', 'token', 'password'])


def test_temporary_password_and_keep_current_invalidate_others(security_client):
    client, app, factory = security_client
    make_account(factory, temporary=True)
    first = login(client).json()['token']
    second = login(client).json()['token']
    client.headers['Authorization'] = 'Bearer ' + first
    assert client.get('/api/customers').status_code == 403
    assert client.get('/api/auth/me').json()['password_change_required']
    result = client.post('/api/auth/password', json={'current_password': 'test-only-password', 'new_password': 'ü'})
    assert result.status_code == 200 and not result.json()['password_change_required']
    assert client.get('/api/customers').status_code == 200
    client.headers['Authorization'] = 'Bearer ' + second
    assert client.get('/api/auth/me').status_code == 401
    authorize(client, login(client, 'ü'))
    assert client.post('/api/auth/logout', json={}).status_code == 200
    assert client.get('/api/auth/me').status_code == 401


def test_session_limit_idle_poll_does_not_renew(security_client):
    client, app, factory = security_client
    make_account(factory)
    now = [1000.0]; app.state.security.clock = lambda: now[0]
    for _ in range(5): authorize(client, login(client))
    assert login(client).status_code == 409
    now[0] += 1681
    assert 0 < client.get('/api/auth/me').json()['expires_in'] < 120
    now[0] += 120
    assert client.get('/api/auth/me').status_code == 401
    authorize(client, login(client))
    now[0] += 1600
    assert client.post('/api/auth/activity', json={}).status_code == 200
    now[0] += 1600
    assert client.get('/api/auth/me').status_code == 200


def test_cli_recovery_invalidates_live_server(security_client, monkeypatch):
    client, app, factory = security_client
    id = make_account(factory)
    for _ in range(5): authorize(client, login(client))
    # Exercise the identical transactional operation used by the local CLI in a separate session.
    with factory() as session:
        recover_superadmin(session, 'new-secret', source='CLI uid=test'); session.commit()
    assert client.get('/api/auth/me').status_code == 401
    authorize(client, login(client, 'new-secret'))
    assert client.get('/api/auth/me').json()['password_change_required']
    with factory() as session:
        assert session.get(Responsible, id).security_role_id == session.scalar(select(SecurityRole.id).where(SecurityRole.code == 'SUPERADMIN'))
        assert session.scalar(select(SecurityAudit).where(SecurityAudit.event == 'PASSWORD_RESET')).source == 'CLI uid=test'


@pytest.mark.parametrize('role', ['ADMIN', 'OPERATOR', 'AUDITOR', 'CUSTOM'])
def test_default_role_policy_and_all_routes_fail_closed(security_client, role):
    client, app, factory = security_client
    paths = ['/api/customers', '/api/system/version', '/docs', '/redoc', '/openapi.json', '/api/mail-notifications/smtp', '/api/unknown']
    for path in paths: assert client.get(path).status_code == 401, path
    assert client.get('/health').status_code == 200
    make_account(factory, role=role)
    authorize(client, login(client))
    permitted = {'/api/system/version'}
    if role in {'ADMIN', 'OPERATOR', 'AUDITOR'}: permitted.add('/api/customers')
    if role == 'ADMIN': permitted.update({'/docs', '/redoc', '/openapi.json', '/api/mail-notifications/smtp'})
    for path in paths: assert client.get(path).status_code == (200 if path in permitted else 403), path
    assert client.get('/api/auth/me').status_code == 200
    assert client.post('/api/auth/logout', json={}).status_code == 200


def test_operational_deactivation_preserves_grant_and_administrative_suspension(security_client):
    client, app, factory = security_client
    id = make_account(factory, role='OPERATOR')
    authorize(client, login(client))
    with factory() as session:
        lock_security(session); item = session.get(Responsible, id)
        change_operational_status(session, item, False); session.commit()
    assert client.get('/api/auth/me').status_code == 401
    assert login(client).status_code == 401
    with factory() as session:
        lock_security(session); item = session.get(Responsible, id)
        assert item.access_granted
        change_operational_status(session, item, True); session.commit()
    authorize(client, login(client))
    with factory() as session:
        set_access(session, id, False); session.commit()
    assert client.get('/api/auth/me').status_code == 401
    with factory() as session:
        lock_security(session); item = session.get(Responsible, id)
        change_operational_status(session, item, False); change_operational_status(session, item, True); session.commit()
        assert not item.access_granted


def test_last_superadmin_and_audit_rollback(security_client, monkeypatch):
    client, app, factory = security_client
    id = make_account(factory)
    with factory() as session:
        with pytest.raises(HTTPException): set_access(session, id, False)
        session.rollback()
    with factory() as session:
        before = session.get(Responsible, id).password_hash
    with factory() as session:
        from ticketyn.security.service import reset_password
        with patch('ticketyn.security.service.audit', side_effect=RuntimeError('audit unavailable')):
            with pytest.raises(RuntimeError): reset_password(session, id, 'replacement')
            session.rollback()
    with factory() as session:
        assert session.get(Responsible, id).password_hash == before


def test_rate_limits_cleanup_shared_ip(security_client):
    client, app, factory = security_client
    make_account(factory)
    now = [1000.0]; app.state.security.clock = lambda: now[0]
    for _ in range(5): assert login(client, 'wrong').status_code == 401
    response = login(client, 'wrong')
    assert response.status_code == 429 and int(response.headers['Retry-After']) <= 60
    assert login(client, 'wrong', 'Other-user').status_code == 401
    now[0] += 901
    authorize(client, login(client))
    memory = app.state.security
    memory.MAX_COUNTERS = 20
    for i in range(100): memory.failed(str(i), 'shared-ip')
    assert len(memory.counters) <= 20
    now[0] += 901; memory.cleanup()
    assert not memory.counters


def test_memory_concurrency_and_token_hashes():
    memory = MemorySecurity()
    def create(_):
        try: return memory.create(1, 0)
        except SessionLimit: return None
    with ThreadPoolExecutor(max_workers=10) as pool:
        tokens = [t for t in pool.map(create, range(20)) if t]
    assert len(tokens) == len(set(tokens)) == 5
    assert all(token not in repr(memory.sessions) for token in tokens)
    assert all(len(digest) == 64 for digest in memory.sessions)


def test_oauth_callback_requires_live_authorized_initiator(security_client):
    client, app, factory = security_client
    callback = '/api/mail-notifications/oauth/callback'
    assert client.get(callback + '?state=x&code=y', follow_redirects=False).status_code == 401
    make_account(factory)
    authorize(client, login(client))
    token = client.headers['Authorization'][7:]
    item = app.state.security.get(token)
    app.state.security.bind_flow('binding', item)
    client.cookies.set('ticketyn_mail_oauth_binding', 'binding', path=callback)
    client.post('/api/auth/logout', json={})
    assert client.get(callback + '?state=x&code=y', follow_redirects=False).status_code == 401


def test_migration_and_actual_cli_recovery_with_live_app(postgres_engine, tmp_path, monkeypatch, capsys):
    from uuid import uuid4
    from sqlalchemy import create_engine, text, inspect
    from test_e2e_update_migration import cli as alembic_cli
    from ticketyn.security.cli import main, settings_from_file
    from ticketyn.main import create_app
    from ticketyn.core.config import get_settings
    database = 'security_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text('CREATE DATABASE ' + database))
    engine = create_engine(postgres_engine.url.set(database=database))
    try:
        alembic_cli(engine.url, 'upgrade', '0029_mail_requests')
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO responsibles(id,name) VALUES(1,'Responsable histórico')"))
            before = connection.scalar(text('SELECT to_jsonb(r) FROM responsibles r WHERE id=1'))
        alembic_cli(engine.url, 'upgrade', '0030_security_foundation')
        with engine.connect() as connection:
            row = connection.execute(text('SELECT * FROM responsibles WHERE id=1')).mappings().one()
            assert not row['access_granted'] and row['username'] is None and row['password_hash'] is None
            assert connection.scalar(text("SELECT to_jsonb(r) - ARRAY['access_granted','username','password_hash','security_role_id','password_change_required','access_revision']::text[] FROM responsibles r WHERE id=1")) == before
            assert connection.scalar(text('SELECT count(*) FROM security_roles')) == 4
            assert connection.scalar(text('SELECT count(*) FROM security_audit')) == 0
        # The current ORM includes operational availability from Phase 3.
        alembic_cli(engine.url, 'upgrade', 'head')
        config = tmp_path / 'security.env'
        config.write_text('DATABASE_URL=' + engine.url.render_as_string(hide_password=False) + '\n')
        config.chmod(0o600)
        assert settings_from_file(str(config)).database_url.startswith('postgresql+psycopg:')
        monkeypatch.setattr('ticketyn.security.cli.getpass.getpass', lambda *_: 'temporary-secret')
        main(['--config', str(config), 'bootstrap', '--responsible-id', '1', '--username', 'first'])
        with pytest.raises(SystemExit): main(['--config', str(config), 'bootstrap', '--responsible-id', '1', '--username', 'duplicate'])
        monkeypatch.setenv('DATABASE_URL', engine.url.render_as_string(hide_password=False)); get_settings.cache_clear()
        @contextmanager
        def factory():
            with Session(engine) as session: yield session
        app = create_app(start_notifications=False, security_session_factory=factory)
        with TestClient(app) as client:
            authorize(client, login(client, 'temporary-secret', 'first'))
            assert client.get('/api/auth/me').status_code == 200
            monkeypatch.setattr('ticketyn.security.cli.getpass.getpass', lambda *_: 'recovered-secret')
            main(['--config', str(config), 'recover-superadmin'])
            assert client.get('/api/auth/me').status_code == 401
            authorize(client, login(client, 'recovered-secret', 'first'))
            assert client.get('/api/auth/me').json()['password_change_required']
        captured = capsys.readouterr()
        assert 'temporary-secret' not in captured.out + captured.err
        assert 'recovered-secret' not in captured.out + captured.err
        config.chmod(0o644)
        with pytest.raises(ValueError): settings_from_file(str(config))
        alembic_cli(engine.url, 'downgrade', '0029_mail_requests')
        with engine.connect() as connection:
            after = connection.scalar(text('SELECT to_jsonb(r) FROM responsibles r WHERE id=1'))
            assert after == before
            assert 'security_roles' not in inspect(connection).get_table_names()
        alembic_cli(engine.url, 'upgrade', 'head')
    finally:
        get_settings.cache_clear(); engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.execute(text('DROP DATABASE ' + database))


def test_argon_concurrency_is_bounded(monkeypatch):
    from threading import Event
    from ticketyn.security import passwords
    entered = Event(); release = Event()
    def blocked(*_):
        entered.set(); release.wait(timeout=5); return True
    from types import SimpleNamespace
    monkeypatch.setattr(passwords, 'HASHER', SimpleNamespace(verify=blocked))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(passwords.verify_password, 'encoded', 'x')
        assert entered.wait(timeout=2)
        second = pool.submit(passwords.verify_password, 'encoded', 'x')
        deadline = time.monotonic() + 2
        while passwords._SLOTS._value and time.monotonic() < deadline: time.sleep(.001)
        try:
            with pytest.raises(passwords.PasswordBusy): passwords.verify_password('encoded', 'x')
        finally:
            release.set()
        assert first.result() and second.result()


def test_memory_caps_restart_and_cleanup():
    now = [0.0]; memory = MemorySecurity(clock=lambda: now[0]); memory.MAX_SESSIONS = 3; memory.MAX_FLOWS = 2
    tokens = [memory.create(i, 0) for i in range(3)]
    with pytest.raises(SessionLimit): memory.create(99, 0)
    item = memory.get(tokens[0])
    memory.bind_flow('a', item); memory.bind_flow('b', item)
    with pytest.raises(SessionLimit): memory.bind_flow('c', item)
    assert not MemorySecurity().get(tokens[0])
    now[0] = 86401; memory.cleanup()
    assert not memory.sessions and not memory.flows


def test_bootstrap_on_empty_installation_uses_existing_catalog(security_client):
    client, app, factory = security_client
    with factory() as session:
        person = bootstrap(session, None, 'first', 'x', responsible_name='Primer Responsable')
        id = person.id
        session.commit()
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Responsible)) == 1
        assert session.get(Responsible, id).name == 'Primer Responsable'
    authorize(client, login(client, 'x', 'first'))
    assert client.get('/api/auth/me').json()['password_change_required']


def test_every_operational_route_denies_anonymous(security_client):
    client, app, factory = security_client
    # Enumerate actual OpenAPI contracts so a newly added router is covered too.
    for path, methods in app.openapi()['paths'].items():
        if path in {'/health', '/api/auth/login'}:
            continue
        import re
        concrete = re.sub(r'\{[^}]+\}', '1', path)
        for method in methods:
            if method not in {'get', 'post', 'patch', 'put', 'delete'}:
                continue
            response = client.request(method.upper(), concrete, json={} if method in {'post', 'patch', 'put'} else None, follow_redirects=False)
            assert response.status_code == 401, (method, path, response.status_code)


def test_new_access_to_inactive_person_is_rejected(security_client):
    _, _, factory = security_client
    id = make_account(factory, active=False, grant=False, role='OPERATOR')
    with factory() as session:
        with pytest.raises(HTTPException) as error: set_access(session, id, True)
        assert error.value.status_code == 422


def test_stale_token_cannot_revoke_new_revision_sessions():
    memory = MemorySecurity()
    old = memory.create(1, 0)
    new = memory.create(1, 1)
    assert memory.get(old) is None
    assert memory.get(new) is not None


def test_unicode_username_uniqueness_and_reservation(security_client):
    from sqlalchemy.exc import IntegrityError
    client, app, factory = security_client
    with factory() as session:
        seed_foundation(session)
        person = Responsible(name='Responsable con acentos'); session.add(person); session.flush()
        bootstrap(session, person.id, 'Ángel', 'x'); session.commit()
    authorize(client, login(client, 'x', 'ángel'))
    with factory() as session:
        session.add(Responsible(name='Otra persona', username='ÁNGEL'))
        with pytest.raises(IntegrityError): session.flush()
        session.rollback()


def test_single_worker_configuration_rejects_multiple_workers(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')
    monkeypatch.setenv('WEB_CONCURRENCY', '2')
    from ticketyn.main import create_app
    from ticketyn.core.config import get_settings
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match='único trabajador'): create_app(start_notifications=False)
    finally:
        get_settings.cache_clear()


def test_http_security_mutations_require_transactional_audit(security_client, caplog):
    from sqlalchemy.exc import SQLAlchemyError
    client, app, factory = security_client
    id = make_account(factory)
    authorize(client, login(client))
    with factory() as session:
        before = (session.get(Responsible, id).password_hash, session.get(Responsible, id).access_revision)
    with patch('ticketyn.api.auth.audit', side_effect=SQLAlchemyError('sensitive-secret')):
        response = client.post('/api/auth/password', json={'current_password': 'test-only-password', 'new_password': 'new-sensitive-password'})
        assert response.status_code == 503
        assert client.post('/api/auth/logout', json={}).status_code == 503
    with factory() as session:
        item = session.get(Responsible, id)
        assert (item.password_hash, item.access_revision) == before
    assert client.get('/api/auth/me').status_code == 200
    assert 'sensitive-secret' not in response.text + caplog.text
    assert 'new-sensitive-password' not in response.text + caplog.text


from test_ticket_concurrency import concurrent_database


def test_last_superadmin_serializes_concurrent_suspensions(concurrent_database):
    from threading import Barrier
    from ticketyn.security.service import seed_foundation
    engine, _ = concurrent_database
    with Session(engine) as session:
        seed_foundation(session)
        role = session.scalar(select(SecurityRole.id).where(SecurityRole.code == 'SUPERADMIN'))
        people = [Responsible(name=f'Administrador {i}', username=f'admin{i}', security_role_id=role, password_hash=fixture_password(), access_granted=True) for i in range(2)]
        session.add_all(people); session.flush(); ids = [p.id for p in people]; session.commit()
    barrier = Barrier(2)
    def suspend(id):
        with Session(engine) as session:
            barrier.wait(timeout=5)
            try:
                set_access(session, id, False); session.commit(); return 200
            except HTTPException as error:
                session.rollback(); return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(suspend, ids)) == [200, 409]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Responsible).where(Responsible.access_granted.is_(True))) == 1


def test_full_size_password_json_escape_overhead_is_supported(security_client):
    client, _, factory = security_client
    make_account(factory)
    authorize(client, login(client))
    password = '\0' * 4096
    first = client.post('/api/auth/password', json={'current_password': 'test-only-password', 'new_password': password})
    assert first.status_code == 200
    second = client.post('/api/auth/password', json={'current_password': password, 'new_password': password})
    assert second.status_code == 200
    response = client.post('/api/auth/password', content='x' * 65537, headers={'Content-Type': 'application/json'})
    assert response.status_code == 413


def test_role_change_is_effective_without_session_refresh(security_client):
    client, app, factory = security_client
    id = make_account(factory)
    authorize(client, login(client))
    assert client.get('/api/customers').status_code == 200
    with factory() as session:
        session.get(Responsible, id).security_role_id = session.scalar(select(SecurityRole.id).where(SecurityRole.code == 'OPERATOR'))
        session.commit()
    assert client.get('/api/customers').status_code == 200
    assert client.get('/api/mail-notifications/smtp').status_code == 403
    assert client.get('/api/auth/me').json()['role'] == 'OPERATOR'


def test_login_session_invalidated_during_creation_returns_controlled_error(security_client, monkeypatch):
    client, app, factory = security_client
    make_account(factory)
    original = app.state.security.create
    def create_then_revoke(*args, **kwargs):
        token = original(*args, **kwargs)
        app.state.security.revoke(token)
        return token
    monkeypatch.setattr(app.state.security, 'create', create_then_revoke)
    response = login(client)
    assert response.status_code == 401
    assert 'token' not in response.json()
