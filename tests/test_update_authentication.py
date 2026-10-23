"""Authentication-aware updates: simulated OS/network and disposable PostgreSQL."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from test_update import ROOT, u, source, updater  # noqa: F401 -- shared isolated fixture


def security_source(root, version='0.7.0'):
    source(root, version)
    for name in ['src/ticketyn/main.py', 'src/ticketyn/api/auth.py', 'src/ticketyn/security/bootstrap.py',
                 'bootstrap-superadmin.sh', 'alembic/versions/0030_security_foundation.py',
                 'alembic/versions/0031_role_permissions.py', 'alembic/versions/0032_responsible_selectable.py']:
        target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    return root


def package(tree, destination):
    with tarfile.open(destination, 'w') as archive:
        for path in tree.rglob('*'):
            archive.add(path, arcname=path.relative_to(tree), recursive=False)
    return destination


def test_extracts_original_executable_bootstrap_and_shares_installer_detector(tmp_path):
    tree = security_source(tmp_path / 'tree')
    extracted = tmp_path / 'out'
    u.extract_release(package(tree, tmp_path / 'release.tar'), extracted)
    assert (extracted / 'bootstrap-superadmin.sh').read_bytes() == (ROOT / 'bootstrap-superadmin.sh').read_bytes()
    assert (extracted / 'bootstrap-superadmin.sh').stat().st_mode & 0o111
    assert u.authentication(extracted)
    assert u.security_capabilities.capability(extracted) == 'required'
    assert u.security_capabilities.__file__ == str(ROOT / 'deploy/install_security.py')
    # Capability detection follows code/schema, even before an official version bump.
    (extracted / 'pyproject.toml').write_text('[project]\nversion = "0.6.2"\n')
    assert u.authentication(extracted)


def test_legacy_archive_does_not_require_bootstrap(tmp_path):
    tree = source(tmp_path / 'tree', '0.6.2')
    u.extract_release(package(tree, tmp_path / 'release.tar'), tmp_path / 'out')
    assert not u.authentication(tmp_path / 'out')
    assert not (tmp_path / 'out/bootstrap-superadmin.sh').exists()


@pytest.mark.parametrize('missing', ['bootstrap-superadmin.sh', 'src/ticketyn/security/bootstrap.py',
                                   'src/ticketyn/api/auth.py', 'alembic/versions/0032_responsible_selectable.py'])
def test_incomplete_security_archive_rejected_before_activation(tmp_path, missing):
    tree = security_source(tmp_path / 'tree'); (tree / missing).unlink()
    with pytest.raises(u.UpdateError, match='incompleta'):
        u.extract_release(package(tree, tmp_path / 'release.tar'), tmp_path / 'out')


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'not-executable', 'duplicate'])
def test_unsafe_bootstrap_not_published(tmp_path, kind):
    tree = security_source(tmp_path / 'tree')
    script = tree / 'bootstrap-superadmin.sh'
    if kind in ('symlink', 'hardlink'):
        script.unlink()
        if kind == 'symlink': script.symlink_to(ROOT / 'bootstrap-superadmin.sh')
        else: os.link(tree / 'src/ticketyn/main.py', script)
    if kind == 'not-executable': script.chmod(0o644)
    archive = package(tree, tmp_path / 'release.tar')
    if kind == 'duplicate':
        with tarfile.open(archive, 'a') as output:
            output.add(script, arcname='bootstrap-superadmin.sh')
    with pytest.raises(u.UpdateError):
        u.extract_release(archive, tmp_path / 'out')


@pytest.mark.parametrize('status', ['401', '200', '403', '500'])
def test_authenticated_health_uses_status_only_and_no_credentials(updater, monkeypatch, status):
    tree = security_source(updater.target)
    updater.current.unlink(); updater.current.symlink_to(tree)
    calls = []
    def run(args, **kwargs):
        args = list(map(str, args)); calls.append(args)
        if args[0] == 'ss': return 'LISTEN 0 128 127.0.0.1:8000 0.0.0.0:*'
        if args[0] == 'curl':
            if args[-1].endswith('/health'): return b'{"status":"ok"}'
            if args[-1].endswith('/api/customers'): return status.encode()
            if args[-1].endswith('/'): return (tree / 'frontend/dist/index.html').read_bytes()
            return (tree / 'frontend/dist/assets/app.js').read_bytes()
        return ''
    updater.run = run; monkeypatch.setattr('time.sleep', lambda _: None)
    if status == '401': updater.healthy(tree)
    else:
        with pytest.raises(u.UpdateError, match='30 intentos'): updater.healthy(tree)
    api = [args for args in calls if args[-1].endswith('/api/customers')]
    assert len(api) == (1 if status == '401' else 30)
    assert all('-fsS' not in args and '-w' in args and '/dev/null' in args for args in api)
    assert not any('Authorization' in ' '.join(args) or '/api/auth/login' in ' '.join(args)
                   or 'bootstrap-superadmin.sh' in ' '.join(args) for args in calls)


def test_authenticated_health_checks_health_contract(updater, monkeypatch):
    tree = security_source(updater.target)
    calls = []
    updater.run = lambda args, **kwargs: calls.append(list(map(str, args))) or b'{"status":"wrong"}'
    monkeypatch.setattr('time.sleep', lambda _: None)
    with pytest.raises(u.UpdateError, match='/health no respondió'):
        updater.healthy(tree)
    assert len([args for args in calls if args[-1].endswith('/health')]) == 30
    assert not any(args[-1].endswith('/api/customers') for args in calls)


def test_authenticated_api_transient_failure_is_retried_without_logging_secrets(updater, monkeypatch, capsys):
    tree = security_source(updater.target)
    updater.current.unlink(); updater.current.symlink_to(tree)
    attempts = []
    def run(args, **kwargs):
        if str(args[0]) == 'ss': return 'LISTEN 0 128 127.0.0.1:8000 0.0.0.0:*'
        if str(args[0]) == 'curl':
            if args[-1].endswith('/health'): return b'{"status":"ok"}'
            if args[-1].endswith('/api/customers'):
                attempts.append(1)
                if len(attempts) == 1:
                    raise subprocess.CalledProcessError(7, args, stderr='synthetic-secret')
                return b'401'
            if args[-1].endswith('/'): return (tree / 'frontend/dist/index.html').read_bytes()
            return (tree / 'frontend/dist/assets/app.js').read_bytes()
        return ''
    updater.run = run; monkeypatch.setattr('time.sleep', lambda _: None)
    updater.healthy(tree)
    assert len(attempts) == 2
    captured = capsys.readouterr()
    assert 'synthetic-secret' not in captured.out + captured.err


def test_administrative_notice_never_executes_bootstrap(updater, capsys):
    security_source(updater.target)
    def forbidden(*args, **kwargs):
        raise AssertionError('No command or DB operation allowed for administrative notice')
    updater.run = forbidden; updater.pg = forbidden
    updater.administrative_notice()
    output = capsys.readouterr().out
    assert 'Actualización técnica completada' in output
    assert 'pendiente de comprobación manual' in output
    assert 'sudo /opt/ticketyn/current/bootstrap-superadmin.sh --check' in output
    assert 'código 3' in output and 'código 0' in output
    assert 'synthetic-secret' not in output


def test_legacy_completion_has_no_initialization_notice(updater, capsys):
    source(updater.target)
    updater.administrative_notice()
    assert capsys.readouterr().out == ''


@pytest.fixture
def database(postgres_engine):
    name = 'updater_auth_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text(f'CREATE DATABASE {name}'))
    engine = create_engine(postgres_engine.url.set(database=name))
    try:
        yield engine
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
            connection.execute(text(f'DROP DATABASE {name}'))


@pytest.mark.parametrize('health_failure', [False, True])
def test_062_to_authentication_with_real_schema_and_manual_initialization_only(tmp_path, database, monkeypatch, capsys, health_failure):
    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session
    from ticketyn.core.config import get_settings
    from ticketyn.db.session import get_session
    from ticketyn.models import Responsible
    from ticketyn.security.bootstrap import create_superadmin

    monkeypatch.setenv('DATABASE_URL', database.url.render_as_string(hide_password=False))
    monkeypatch.setattr('time.sleep', lambda _: None)
    get_settings.cache_clear()
    base, config, backs = tmp_path / 'opt', tmp_path / 'etc', tmp_path / 'backups'
    for path in (base / 'releases', config, backs): path.mkdir(parents=True, mode=0o700)
    old = source(base / 'releases/0.6.2', '0.6.2')
    shutil.copytree(ROOT / 'alembic', old / 'alembic', dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
    for path in (old / 'alembic/versions').glob('*.py'):
        if path.name[:4].isdigit() and int(path.name[:4]) >= 30: path.unlink()
    shutil.copy2(ROOT / 'alembic.ini', old)
    old_config = Config(str(old / 'alembic.ini'))
    command.upgrade(old_config, 'head')
    with database.begin() as connection:
        identity = connection.scalar(text("INSERT INTO responsibles(name) VALUES ('Histórico conservado') RETURNING id"))
        original = connection.execute(text('SELECT id,name,active FROM responsibles')).all()

    (base / 'current').symlink_to(old)
    env = config / 'ticketyn.env'
    env.write_text('DATABASE_URL=postgresql+psycopg://ticketyn:synthetic-only@127.0.0.1:5432/ticketyn\n'); env.chmod(0o600)
    obj = u.Updater('v0.7.0', base, config, backs, tmp_path / 'lock', nginx_root=config / 'nginx')
    obj.old = old; obj.source_version = '0.6.2'; obj.revision = '0029_mail_requests'
    obj.target = base / 'releases/0.7.0'; obj.unit = config / 'unit'
    obj.env_hash = u.digest(env); obj.db_oid = '123'; obj.cluster = '456'; obj.port = '8080'
    obj.work = tmp_path / 'work'; obj.work.mkdir(mode=0o700)
    obj.begin()
    incoming = security_source(obj.work / 'source')
    shutil.copytree(ROOT / 'alembic', incoming / 'alembic', dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(ROOT / 'alembic.ini', incoming)
    obj.record('preparing', commit='a' * 40, tag_oid='a' * 40, package_version='0.7.0',
               release_hashes={str(path.relative_to(incoming)): u.digest(path) for path in incoming.rglob('*') if path.is_file()})
    obj.db_revision = lambda: read_revision(database)
    obj.pg = lambda sql, database='postgres': '123'
    calls = []; service = {'active': True, 'enabled': True}
    @contextmanager
    def sessions():
        with Session(database) as session: yield session
    from ticketyn.main import create_app
    app = create_app(start_notifications=False, security_session_factory=sessions)
    def operation_session():
        with Session(database) as session: yield session
    app.dependency_overrides[get_session] = operation_session

    with TestClient(app) as client:
        def run(args, **kwargs):
            args = list(map(str, args)); calls.append(args)
            assert not any(arg.endswith('/bootstrap-superadmin.sh') for arg in args)
            if 'plan' in args: return u.migration_plan(old, obj.target, obj.revision)
            if 'migrate' in args:
                command.upgrade(Config(str(obj.target / 'alembic.ini')), 'head')
            if args[0] == 'systemctl':
                if args[1] in ('start', 'stop'): service['active'] = args[1] == 'start'
                if args[1] in ('enable', 'disable'): service['enabled'] = args[1] == 'enable'
            if args[0] == 'curl':
                url = args[-1]
                if url.endswith('/health') and health_failure:
                    raise subprocess.CalledProcessError(22, args)
                if url.endswith('/health'): return client.get('/health').content
                if url.endswith('/api/customers'):
                    response = client.get('/api/customers')
                    assert response.status_code == 401
                    return b'401'
                if url.endswith('/'): return (obj.target / 'frontend/dist/index.html').read_bytes()
                return (obj.target / 'frontend/dist/assets/app.js').read_bytes()
            if args[0] == 'ss': return 'LISTEN 0 128 127.0.0.1:8000 0.0.0.0:*'
            return ''
        obj.run = run
        obj.prepare(incoming)
        backup = backs / 'pre-update.tar'; backup.write_bytes(b'isolated backup placeholder'); backup.chmod(0o600)
        obj.record('prepared', backup=str(backup), backup_sha256=u.digest(backup))
        if health_failure:
            with pytest.raises(u.UpdateError): obj.activate()
            obj.failure()
            assert not service['active'] and not service['enabled']
            with pytest.raises(u.UpdateError, match='interrumpida'): obj.validate_resume()
            assert obj.state.exists() and obj.data['phase'] == 'checking'
        else:
            obj.activate(); obj.administrative_notice()
            assert service['active'] and service['enabled'] and not obj.state.exists()
            assert (obj.target / 'bootstrap-superadmin.sh').stat().st_mode & 0o111
        assert obj.current.resolve() == obj.target and old.exists() and backup.exists()
        assert read_revision(database) == obj.data['target_head']  # current never downgrades DB
        with database.connect() as connection:
            assert connection.execute(text('SELECT id,name,active FROM responsibles')).all() == original
            assert connection.scalar(text('SELECT count(*) FROM responsibles WHERE access_granted OR username IS NOT NULL')) == 0
        assert 'bootstrap-superadmin.sh' in obj.data['release_hashes']
        if not health_failure:
            output = capsys.readouterr().out
            assert 'pendiente de comprobación manual' in output
            # Emulate the separate authorized manual phase in this disposable DB.
            with Session(database) as session:
                admin, _ = create_superadmin(session, 'manual-fixture', 'synthetic-password', responsible_name='Manual fixture')
                session.commit(); admin_id, password_hash = admin.id, admin.password_hash
            before = len(calls)
            obj.preflight = lambda: None; obj.lock = lambda: None
            obj.execute()  # completed checkpoint: no migration, bootstrap or account mutation
            assert len(calls) == before
            with Session(database) as session:
                assert session.get(Responsible, admin_id).password_hash == password_hash
                assert session.get(Responsible, identity).username is None
    get_settings.cache_clear()


def read_revision(engine):
    with engine.connect() as connection:
        return connection.scalar(text('SELECT version_num FROM alembic_version'))
