"""Abort uses real durable files and mocked read-only host observations."""
import json
import signal
import subprocess
import sys

import pytest
from test_update import u, ROOT, updater, configured_preflight


@pytest.fixture
def aborter(updater):
    configured_preflight(updater)
    updater.record('preparing', result='interrupted_or_failed', diagnostic='Fallo descargando candidata',
                   unit_hash=u.digest(updater.unit), site_hash=u.digest(updater.site),
                   source_snapshot=u.release_snapshot(updater.old))
    obj = u.AbortUpdater(base=updater.base, config=updater.config, backups=updater.backups, lock=updater.lock_path, nginx_root=updater.nginx_root)
    obj.unit = updater.unit
    obj.pg, obj.db_revision, obj.head = updater.pg, updater.db_revision, updater.head
    def forbidden(*args, **kwargs):
        pytest.fail('Abort invoked mutating/service/backup/activation operation')
    obj.run = forbidden
    obj.backup = obj.activate = obj.begin = forbidden
    return obj


@pytest.mark.parametrize('phase', u.SAFE_RETRY)
def test_abort_safe_phases_archives_and_preserves_all_resources(aborter, updater, phase, capsys):
    updater.record(phase, result='interrupted_or_failed')
    before = json.loads((updater.state/'state.json').read_text())
    previous = updater.current.readlink()
    updater.target.mkdir(mode=0o700)
    backup = updater.backups/'retained.tar'; backup.write_text('retained'); backup.chmod(0o600)
    env = updater.env.read_bytes()
    aborter.execute()
    archived = updater.config/'update-history'/before['operation']/'state.json'
    body = u.read_json(archived)
    assert body['result'] == 'interrupted_or_failed' and body['phase'] == phase
    assert body['abort']['reason'] == 'voluntarily_aborted'
    assert body['abort']['original_checkpoint'] == before['checkpoint']
    assert body['diagnostic'] == before['diagnostic']
    for key in before.keys() - {'checkpoint'}:
        assert body[key] == before[key]
    aborter.verify_checkpoint(body)
    assert not updater.state.exists()
    assert updater.current.readlink() == previous and updater.old.exists() and updater.target.exists()
    assert backup.read_text() == 'retained' and updater.env.read_bytes() == env
    output = capsys.readouterr()
    assert 'synthetic-secret' not in output.out + output.err


@pytest.mark.parametrize('phase', ['migrating', 'migrated', 'activating', 'starting', 'checking', 'complete'])
def test_abort_after_boundary_rejected_without_changes(aborter, updater, phase):
    updater.record(phase, result='success' if phase == 'complete' else 'interrupted_or_failed')
    before = (updater.state/'state.json').read_bytes()
    with pytest.raises(u.UpdateError, match='SAFE_RETRY'):
        aborter.execute()
    assert (updater.state/'state.json').read_bytes() == before
    assert not (updater.config/'update-history').exists()


@pytest.mark.parametrize('kind', ['tamper', 'receipt', 'current', 'release', 'inode', 'config', 'db', 'oid', 'cluster', 'unit', 'site', 'pending', 'recovery', 'restore'])
def test_abort_identity_fail_closed(aborter, updater, kind):
    if kind == 'tamper':
        body = u.read_json(updater.state/'state.json'); body['diagnostic'] = 'changed'
        (updater.state/'state.json').write_text(json.dumps(body))
    elif kind == 'receipt':
        receipt = updater.config/'update-evidence'/updater.data['operation']/(updater.data['checkpoint']['id']+'.json')
        receipt.write_text('{}')
    elif kind == 'current':
        updater.current.unlink(); updater.current.symlink_to(updater.base/'other')
    elif kind == 'release':
        (updater.old/'src/ticketyn/main.py').write_text('altered')
    elif kind == 'inode':
        moved = updater.old.with_name('moved'); updater.old.rename(moved)
        updater.old.mkdir(mode=0o700)
    elif kind == 'config':
        updater.env.write_text(updater.env.read_text()+'# changed\n')
    elif kind == 'db':
        aborter.db_revision = lambda: 'new'
    elif kind in ('oid', 'cluster'):
        original = aborter.pg
        aborter.pg = lambda sql, database='postgres': '999' if ('SELECT oid' if kind == 'oid' else 'system_identifier') in sql else original(sql, database)
    elif kind in ('unit', 'site'):
        getattr(aborter, kind).write_text('changed')
    elif kind == 'pending':
        updater.record('preparing', result='pending')
    elif kind == 'recovery':
        updater.record('preparing', kind='recovery')
    else:
        (updater.config/'restore-state').mkdir(mode=0o700)
    before = (updater.state/'state.json').read_bytes()
    with pytest.raises((u.UpdateError, ValueError, OSError)):
        aborter.execute()
    assert (updater.state/'state.json').read_bytes() == before
    assert not (updater.config/'update-history').exists()


@pytest.mark.parametrize('signal_number', [signal.SIGINT, signal.SIGTERM])
def test_interrupted_abort_intent_blocks_update_and_recovers(aborter, updater, monkeypatch, signal_number):
    original = aborter.archive_state
    def interrupted():
        raise u.UpdateError('Interrumpido por señal '+str(signal_number))
    monkeypatch.setattr(aborter, 'archive_state', interrupted)
    with pytest.raises(u.UpdateError, match='señal'):
        aborter.execute()
    body = u.read_json(updater.state/'state.json')
    assert body['abort']['reason'] == 'voluntarily_aborted'
    for recover in (False, True):
        updater.recover = recover
        with pytest.raises(u.UpdateError, match='Abort pendiente'):
            updater.read_state()
    updater.recover = False
    monkeypatch.setattr(aborter, 'archive_state', original)
    aborter.execute()
    assert not updater.state.exists()


def test_interruption_after_atomic_archive_and_second_abort(aborter, updater, monkeypatch):
    original = aborter.archive_state
    def interrupted():
        original()
        raise KeyboardInterrupt()
    monkeypatch.setattr(aborter, 'archive_state', interrupted)
    with pytest.raises(KeyboardInterrupt):
        aborter.execute()
    assert not updater.state.exists()
    archived = updater.config/'update-history'/updater.data['operation']/'state.json'
    saved = archived.read_bytes()
    with pytest.raises(u.UpdateError, match='No existe update-state'):
        aborter.execute()
    assert archived.read_bytes() == saved


def test_new_update_different_tag_after_abort(aborter, updater):
    aborter.execute()
    next_update = u.Updater('v0.3.0', updater.base, updater.config, updater.backups, updater.lock_path, nginx_root=updater.nginx_root)
    next_update.unit = updater.unit
    next_update.pg, next_update.db_revision, next_update.head, next_update.run, next_update.healthy = updater.pg, updater.db_revision, updater.head, updater.run, updater.healthy
    next_update.preflight()
    assert next_update.data is None and next_update.target == updater.releases/'0.3.0'
    next_update.begin()
    assert next_update.data['tag'] == 'v0.3.0'


def test_abort_does_not_overwrite_history(aborter, updater):
    history = updater.config/'update-history'; history.mkdir(mode=0o700)
    target = history/updater.data['operation']; target.mkdir(mode=0o700)
    (target/'unrelated').write_text('preserve')
    before = (updater.state/'state.json').read_bytes()
    with pytest.raises(u.UpdateError, match='historial'):
        aborter.execute()
    assert (updater.state/'state.json').read_bytes() == before
    assert (target/'unrelated').read_text() == 'preserve'


def test_read_only_postgres_integration(aborter, updater, db_session):
    from sqlalchemy import text
    oid = str(db_session.scalar(text('SELECT oid FROM pg_database WHERE datname=current_database()')))
    cluster = str(db_session.scalar(text('SELECT system_identifier FROM pg_control_system()')))
    updater.record('preparing', db_oid=oid, cluster=cluster)
    def pg(sql, database='postgres'):
        if 'SELECT oid' in sql:
            return str(db_session.scalar(text('SELECT oid FROM pg_database WHERE datname=current_database()')))
        if 'system_identifier' in sql:
            return str(db_session.scalar(text(sql)))
        if 'pg_get_userbyid' in sql:
            return 'ticketyn:UTF8'  # Test DB owner intentionally differs from production.
        pytest.fail('Unexpected SQL: '+sql)
    aborter.pg = pg
    before = db_session.scalar(text('SELECT count(*) FROM tickets'))
    aborter.execute()
    assert db_session.scalar(text('SELECT count(*) FROM tickets')) == before


def test_interruption_before_intent_keeps_original_checkpoint(aborter, updater, monkeypatch):
    saved = (updater.state/'state.json').read_bytes()
    persist = aborter.persist
    monkeypatch.setattr(aborter, 'persist', lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        aborter.execute()
    assert (updater.state/'state.json').read_bytes() == saved
    updater.read_state()  # Original failed operation remains valid and blocked.
    monkeypatch.setattr(aborter, 'persist', persist)
    aborter.execute()
    assert not updater.state.exists()


def test_history_parent_synced_before_archive(aborter, monkeypatch):
    calls = []
    sync = u.rs.sync_directory
    rename = u.rs.rename_exclusive
    def record_sync(path):
        calls.append(('sync', path)); sync(path)
    def record_rename(left, right):
        if left == aborter.state:
            assert ('sync', aborter.config/'update-history') in calls
            assert ('sync', aborter.config) in calls
        rename(left, right)
    monkeypatch.setattr(u.rs, 'sync_directory', record_sync)
    monkeypatch.setattr(u.rs, 'rename_exclusive', record_rename)
    aborter.execute()
