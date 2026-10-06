"""Recovery evidence and services are isolated; never access a managed host."""
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

import pytest
from test_update import u, ROOT, updater, source, migrations, configured_preflight
from test_restore import components, package


class Lab:
    def __init__(self, obj):
        self.obj = obj
        self.revision = 'old'
        self.active = True
        self.enabled = True
        self.calls = []
        self.backups = []
        self.fail = None
        self.transient = False
        self.counts = {}

    def head(self, release):
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        cfg = Config(str(release/'alembic.ini'))
        cfg.set_main_option('script_location', str(release/'alembic'))
        return ScriptDirectory.from_config(cfg).get_current_head()

    def pg(self, sql, database='postgres'):
        if 'pg_get_userbyid' in sql:
            return 'ticketyn:UTF8'
        if 'system_identifier' in sql:
            return '456'
        return '123'

    def backup(self):
        if self.fail == 'backup':
            u.fail('backup falló')
        obj = self.obj
        parts = components({'env': obj.env, 'release': obj.old})
        parts['metadata.txt'] = parts['metadata.txt'].replace(b'0004_nodes_responsibles', self.revision.encode())
        for key in ('ticketyn_version', 'release_name'):
            parts['metadata.txt'] = parts['metadata.txt'].replace((key+'=0.1.0\n').encode(), (key+'='+obj.source_version+'\n').encode())
        parts['metadata.txt'] = parts['metadata.txt'].replace(b'expected_git_tag=v0.1.0\n', ('expected_git_tag=v'+obj.source_version+'\n').encode())
        parts['metadata.txt'] = parts['metadata.txt'].replace(b'source_release_path=/opt/ticketyn/releases/0.1.0\n', ('source_release_path=/opt/ticketyn/releases/'+obj.source_version+'\n').encode())
        archive = package({'root': obj.backups}, parts)
        final = obj.backups/('snapshot-'+str(len(self.backups))+'.tar')
        archive.rename(final)
        self.backups.append(final)
        return '✓ Backup completo y verificado: '+str(final)

    def run(self, args, **kwargs):
        args = [str(a) for a in args]
        self.calls.append(args)
        if args[0].endswith('/backup.sh'):
            return self.backup()
        if 'plan' in args:
            return u.migration_plan(Path(args[-3]), Path(args[-2]), args[-1])
        if 'verify-python' in args and self.fail == 'import':
            u.fail('import falló')
        if 'install' in args and self.fail == 'dependencies':
            u.fail('dependencias fallaron')
        if 'migrate' in args:
            if self.fail == 'migrate':
                u.fail('migración falló')
            self.revision = self.head(Path(args[-2]))
        if 'port' in args:
            return '8080'
        if args[0] == 'ss':
            return 'LISTEN 0 128 127.0.0.1:8000 0.0.0.0:*' if self.active else ''
        if args[0] == 'systemctl':
            if 'show' in args:
                return ('active' if self.active else 'inactive') if '--property=ActiveState' in args else ('enabled' if self.enabled else 'disabled')
            if args[1] == 'start':
                if self.fail == 'start':
                    u.fail('arranque falló')
                self.active = True
            if args[1] == 'stop':
                self.active = False
            if args[1] == 'enable':
                self.enabled = True
            if args[1] == 'disable':
                self.enabled = False
            if args[1] == 'is-active' and args[-1] == 'ticketyn' and not self.active:
                u.fail('servicio detenido')
        if args[0] == 'curl':
            url = args[-1]
            self.counts[url] = self.counts.get(url, 0)+1
            if self.fail in ('health', 'api') and url.endswith('/health' if self.fail == 'health' else '/api/customers') or self.transient and self.counts[url] == 1:
                raise subprocess.CalledProcessError(22, args, stderr='502 synthetic-secret')
            if url.endswith('/health'):
                return '{"status":"ok"}'
            if url.endswith('/api/customers'):
                return '[]'
            current = self.obj.current.resolve()
            return (current/'frontend/dist/index.html').read_bytes() if url.endswith('/') else (current/'frontend/dist/assets/app.js').read_bytes()
        return ''

    def bind(self, obj):
        self.obj = obj
        obj.run = self.run
        obj.pg = self.pg
        obj.db_revision = lambda: self.revision
        obj.head = self.head
        obj.lock = lambda: None
        obj.healthy = u.Updater.healthy.__get__(obj)

    def recovery(self, tag='v0.2.1'):
        previous = self.obj
        obj = u.Updater(tag, previous.base, previous.config, previous.backups, previous.lock_path, recover=True)
        obj.unit, obj.site, obj.link = previous.unit, previous.site, previous.link
        self.bind(obj)
        obj.work = Path(tempfile.mkdtemp(prefix='work-'+obj.version+'-', dir=previous.base.parent))
        return obj

    def incoming(self, obj, later=False):
        tree = source(obj.work/'source', '.'.join(map(str, u.ri.semver(obj.version)[0])))
        tree.chmod(0o700)
        migrations(tree, True)
        if later:
            (tree/'alembic/versions/later.py').write_text("revision='later'\ndown_revision='new'\n")
        obj.record('preparing', commit='a'*40, tag_oid='a'*40,
                   package_version=u.ri.project_version(tree),
                   release_hashes={str(p.relative_to(tree)): u.digest(p) for p in tree.rglob('*') if p.is_file()})
        return tree


@pytest.fixture
def failed(updater, monkeypatch):
    configured_preflight(updater)
    migrations(updater.old)
    lab = Lab(updater)
    lab.bind(updater)
    updater.record('preparing', source_snapshot=u.release_snapshot(updater.old), unit_hash=u.digest(updater.unit), site_hash=u.digest(updater.site))
    updater.prepare(lab.incoming(updater))
    updater.backup()
    lab.fail = 'health'
    monkeypatch.setattr('time.sleep', lambda _: None)
    with pytest.raises(u.UpdateError):
        updater.activate()
    updater.failure()
    lab.fail = None
    assert updater.data['phase'] == 'checking'
    assert lab.revision == 'new' and not lab.active and not lab.enabled
    return lab


def prepare(lab, later=False):
    obj = lab.recovery()
    obj.preflight()
    obj.begin()
    obj.prepare(lab.incoming(obj, later))
    obj.backup()
    return obj


@pytest.mark.parametrize('later', [False, True])
def test_recovery_complete_and_second_backup(failed, later):
    original = copy.deepcopy(failed.obj.data)
    obj = prepare(failed, later)
    assert obj.current.resolve().name == '0.2.0'
    assert len(failed.backups) == 2
    before = len(failed.calls)
    obj.activate()
    assert any('migrate' in c for c in failed.calls[before:]) == later
    assert failed.revision == ('later' if later else 'new')
    assert obj.current.resolve() == obj.target
    assert failed.active and failed.enabled and not obj.state.exists()
    original_history = obj.config/'update-history'/original['operation']/'state.json'
    assert json.loads(original_history.read_text())['result'] == 'interrupted_or_failed'
    history = json.loads((obj.config/'update-history'/obj.data['operation']/'state.json').read_text())
    assert history['parent_operation_id'] == original['operation'] and history['result'] == 'success'
    assert all(p.exists() for p in failed.backups)
    assert Path(original['previous']).exists() and Path(original['target']).exists()
    assert failed.calls[-1] == ['systemctl', 'enable', 'ticketyn']
    before = len(failed.backups)
    again = failed.recovery()
    again.execute()
    assert len(failed.backups) == before  # completed recovery is verified, not repeated


def test_old_format_evidence_is_insufficient(failed):
    obj = failed.recovery()
    d = json.loads((obj.state/'state.json').read_text())
    d['format'] = 'ticketyn-update-v1'
    (obj.state/'state.json').write_text(json.dumps(d))
    with pytest.raises(u.UpdateError, match='estado v1'):
        obj.preflight()
    assert len(failed.backups) == 1 and not failed.active


@pytest.mark.parametrize('problem', ['json', 'checkpoint', 'source', 'target', 'current', 'current_inode', 'revision', 'oid', 'cluster', 'env', 'backup_missing', 'backup_changed', 'active', 'enabled', 'listener', 'parent_phase'])
def test_incoherent_recovery_never_modifies_installation(failed, problem):
    original = failed.obj
    obj = failed.recovery()
    d = original.data
    if problem == 'json':
        value = dict(d, db_oid='999'); (obj.state/'state.json').write_text(json.dumps(value))
    elif problem == 'checkpoint':
        (obj.config/'update-evidence'/d['operation']/(d['checkpoint']['id']+'.json')).unlink()
    elif problem in ('source', 'target'):
        path = Path(d['previous' if problem == 'source' else 'target'])/'src/ticketyn/main.py'
        path.write_text('alterado')
    elif problem == 'current':
        obj.current.unlink(); obj.current.symlink_to(Path(d['previous']))
    elif problem == 'current_inode':
        moved = obj.base/'other'; obj.current.rename(moved); obj.current.symlink_to(Path(d['target']))
    elif problem == 'revision':
        failed.revision = 'unexpected'
    elif problem in ('oid', 'cluster'):
        old = failed.pg
        obj.pg = lambda sql, database='postgres': '999' if ('SELECT oid' in sql if problem == 'oid' else 'system_identifier' in sql) else old(sql, database)
    elif problem == 'env':
        obj.env.write_text(obj.env.read_text().replace('synthetic-secret', 'different'))
    elif problem == 'backup_missing':
        failed.backups[0].unlink()
    elif problem == 'backup_changed':
        failed.backups[0].write_bytes(b'corrupt')
    elif problem == 'active':
        failed.active = True
    elif problem == 'enabled':
        failed.enabled = True
    elif problem == 'listener':
        old = obj.run; obj.run = lambda args, **kw: 'foreign listener' if args[0] == 'ss' else old(args, **kw)
    else:
        original.record('migrating', result='interrupted_or_failed')
    before = len(failed.calls)
    with pytest.raises((u.UpdateError, FileNotFoundError)):
        obj.preflight()
    obj.failure()
    assert not any(c[:2] in (['systemctl', 'start'], ['systemctl', 'stop']) or 'migrate' in c or c[0].endswith('/backup.sh') for c in failed.calls[before:])


@pytest.mark.parametrize('where', ['import', 'dependencies', 'backup', 'migrate', 'start', 'health', 'api', 'switch'])
def test_failure_keeps_durable_state_and_artifacts(failed, monkeypatch, where):
    obj = failed.recovery()
    obj.preflight(); obj.begin()
    failed.fail = where
    if where == 'switch':
        monkeypatch.setattr(u, 'switch_current', lambda *a, **kw: u.fail('exchange falló'))
    with pytest.raises(u.UpdateError):
        obj.prepare(failed.incoming(obj, later=where == 'migrate'))
        obj.backup(); obj.activate()
    obj.failure()
    state = json.loads((obj.state/'state.json').read_text())
    assert state['result'] == 'interrupted_or_failed'
    assert obj.old.exists() and obj.target.exists() and failed.backups[0].exists()
    assert not failed.active and not failed.enabled
    assert obj.current.resolve() == (obj.target if where in ('start', 'health', 'api') else obj.old)
    assert state['parent_operation_id']


@pytest.mark.parametrize('phase', ['preparing', 'backup', 'prepared', 'stopping', 'migrated', 'activating', 'starting', 'checking', 'migrating'])
def test_retry_boundaries(failed, phase):
    obj = prepare(failed)
    if phase in ('preparing', 'backup', 'prepared', 'stopping', 'migrated', 'migrating'):
        obj.record(phase, result='interrupted_or_failed')
    else:
        obj.publish_permissions()
        obj.record('activating')
        u.switch_current(obj.current, obj.target, obj.old, obj.data['current_inode'], obj.base/'.retry',
                         lambda inode: obj.record('activating', activated_current_inode=inode))
        obj.record(phase, result='interrupted_or_failed')
    retry = failed.recovery()
    retry.preflight(); retry.begin()
    if phase in u.SAFE_RETRY:
        # Retry the exact tag; immutable prepared content is reused, new backup required.
        retry.prepare(failed.incoming(retry)); retry.backup(); retry.activate()
    else:
        retry.finish_recovery_activation()
    assert retry.current.resolve() == retry.target and not retry.state.exists()
    assert failed.active and failed.enabled


def test_interrupted_real_migration_refuses_guessing(failed):
    obj = prepare(failed, later=True)
    obj.record('migrating', result='interrupted_or_failed')
    failed.revision = 'later'
    retry = failed.recovery()
    with pytest.raises(u.UpdateError, match='durante migración'):
        retry.preflight()
    assert not failed.active and not failed.enabled


@pytest.mark.parametrize('signum', [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize('phase', ['preparing', 'checking'])
def test_signals_keep_recovery_diagnostic(failed, phase, signum):
    obj = prepare(failed)
    obj.record(phase)
    code = '''import importlib.util,signal,sys
s=importlib.util.spec_from_file_location('u',sys.argv[1]);u=importlib.util.module_from_spec(s);s.loader.exec_module(u)
a=u.Updater('v0.2.1',sys.argv[2],sys.argv[3],sys.argv[4],recover=True);a.read_state();a.authorized=True
a.run=lambda *args,**kwargs:''
def interrupted(n,f):raise u.UpdateError('Interrumpido')
signal.signal(int(sys.argv[5]),interrupted)
try:signal.raise_signal(int(sys.argv[5]))
except u.UpdateError:a.failure();sys.exit(1)
'''
    result = subprocess.run([sys.executable, '-c', code, ROOT/'deploy/update_support.py', obj.base, obj.config, obj.backups, str(int(signum))], text=True, capture_output=True)
    assert result.returncode == 1 and 'synthetic-secret' not in result.stdout+result.stderr
    obj.read_state()
    assert obj.data['result'] == 'interrupted_or_failed'
    assert failed.backups[0].exists()


def test_transient_http_is_silent_and_autostart_last(failed, capsys):
    obj = prepare(failed)
    failed.transient = True; failed.counts.clear()
    obj.activate()
    assert '502' not in ''.join(capsys.readouterr())
    assert failed.calls[-1] == ['systemctl', 'enable', 'ticketyn']


def test_recovery_requires_pending_state(failed):
    obj = failed.recovery()
    obj.state.rename(obj.config/'saved')
    with pytest.raises((u.UpdateError, FileNotFoundError)):
        obj.preflight()


def test_recovery_root_required():
    if os.geteuid() == 0:
        pytest.skip('non-root test')
    result = subprocess.run([ROOT/'update.sh', '--recover', 'v0.2.1'], text=True, capture_output=True)
    assert result.returncode != 0 and 'root' in result.stderr


@pytest.mark.parametrize('tag', ['v0.2.0', 'v0.1.9', 'v1.0.0'])
def test_recovery_is_strictly_forward(failed, tag):
    obj = failed.recovery(tag)
    with pytest.raises(u.UpdateError):
        obj.preflight()
    assert not failed.active and len(failed.backups) == 1


@pytest.mark.parametrize('which', ['unit', 'site'])
def test_deployment_identity_altered(failed, which):
    obj = failed.recovery()
    path = getattr(obj, which)
    path.write_text(path.read_text()+'\n# altered\n')
    with pytest.raises(u.UpdateError, match='identidad|Identidad'):
        obj.preflight()


def test_parent_history_tampering_refused(failed):
    obj = prepare(failed)
    parent = obj.config/'update-history'/obj.data['parent_operation_id']/'state.json'
    value = json.loads(parent.read_text()); value['result'] = 'success'
    parent.write_text(json.dumps(value))
    retry = failed.recovery()
    with pytest.raises(u.UpdateError, match='modificado'):
        retry.preflight()


def test_evidence_private_and_no_secret(failed, capsys):
    obj = prepare(failed)
    for path in (obj.config/'update-evidence').rglob('*'):
        assert path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o600)
        if path.is_file():
            assert 'synthetic-secret' not in path.read_text()
            assert 'DATABASE_URL' not in path.read_text()
    assert 'synthetic-secret' not in ''.join(capsys.readouterr())


def test_execute_recovers_without_migration(failed):
    obj = failed.recovery()
    obj.fetch = lambda: failed.incoming(obj)
    calls = len(failed.calls)
    obj.execute()
    assert not any('migrate' in c for c in failed.calls[calls:])
    assert failed.active and failed.enabled and len(failed.backups) == 2


def test_second_failed_recovery_can_move_forward(failed):
    first = prepare(failed)
    failed.fail = 'health'
    with pytest.raises(u.UpdateError):
        first.activate()
    first.failure(); failed.fail = None
    parent = first.data['operation']
    second = failed.recovery('v0.2.2')
    second.preflight(); second.begin()
    second.prepare(failed.incoming(second)); second.backup(); second.activate()
    assert second.data['parent_operation_id'] == parent
    assert len(failed.backups) == 3 and all(p.exists() for p in failed.backups)
    assert (second.config/'update-history'/parent/'state.json').exists()


@pytest.mark.parametrize('boundary', ['before_exchange', 'after_exchange', 'after_enable'])
def test_power_loss_activation_boundaries(failed, monkeypatch, boundary):
    obj = prepare(failed)
    obj.publish_permissions(); obj.record('activating')
    temporary = obj.base/'.power-loss'
    if boundary == 'before_exchange':
        temporary.symlink_to(obj.target)
        obj.record('activating', activated_current_inode=u.stamp(temporary))
    else:
        u.switch_current(obj.current, obj.target, obj.old, obj.data['current_inode'], temporary,
                         lambda inode: obj.record('activating', activated_current_inode=inode))
        if boundary == 'after_enable':
            obj.record('checking'); failed.active = True; failed.enabled = True
    retry = failed.recovery()
    if boundary == 'after_enable':
        with pytest.raises(u.UpdateError, match='detenido'):
            retry.preflight()
    else:
        retry.preflight(); retry.begin(); retry.finish_recovery_activation()
        assert failed.active and failed.enabled


def test_archive_interrupted_can_be_retried(failed, monkeypatch):
    obj = prepare(failed)
    original_archive = obj.archive_state
    monkeypatch.setattr(obj, 'archive_state', lambda: u.fail('cierre interrumpido'))
    with pytest.raises(u.UpdateError):
        obj.activate()
    # Completed/healthy is not downgraded to failed merely by archive interruption.
    assert obj.data['phase'] == 'complete' and obj.data['result'] == 'success'
    retry = failed.recovery()
    retry.execute()
    assert not retry.state.exists() and len(failed.backups) == 2


def test_native_postgres_recovery_migrates_and_preserves(updater, postgres_engine, monkeypatch):
    """Run real DDL/dumps only in a UUID database of conftest's disposable cluster."""
    import shutil
    from uuid import uuid4
    from sqlalchemy import create_engine, text
    from alembic.config import Config
    from alembic import command
    database = 'recovery_'+uuid4().hex
    assert postgres_engine.url.host is None
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE '+database))
    url = postgres_engine.url.set(database=database)
    engine = create_engine(url)
    configured_preflight(updater)
    migrations(updater.old)
    environment = '''from alembic import context
from sqlalchemy import create_engine
import os
engine=create_engine(os.environ['DATABASE_URL'])
with engine.connect() as conn:
 context.configure(connection=conn)
 with context.begin_transaction():context.run_migrations()
engine.dispose()
'''
    old_script = """from alembic import op
revision='old'
down_revision=None
def upgrade():op.execute('CREATE TABLE preserved (value text)')
def downgrade():pass
"""
    new_script = """from alembic import op
revision='new'
down_revision='old'
def upgrade():op.execute('ALTER TABLE preserved ADD COLUMN first_probe text')
def downgrade():pass
"""
    (updater.old/'alembic/env.py').write_text(environment)
    (updater.old/'alembic/versions/old.py').write_text(old_script)
    monkeypatch.setenv('DATABASE_URL', url.render_as_string(hide_password=False))
    def migrate(release, revision):
        cfg = Config(str(release/'alembic.ini')); cfg.set_main_option('script_location', str(release/'alembic'))
        command.upgrade(cfg, revision)
    def revision():
        with engine.connect() as c:
            return c.scalar(text('SELECT version_num FROM alembic_version'))
    lab = Lab(updater); lab.bind(updater)
    original_run = lab.run
    def run(args, **kwargs):
        if 'migrate' in args:
            migrate(Path(args[-2]), 'head')
            lab.revision = revision()
            lab.calls.append(list(map(str, args)))
            return ''
        if str(args[0]) == 'pg_restore':
            subprocess.run(list(map(str, args)), check=True, capture_output=True)
            return ''
        return original_run(args, **kwargs)
    lab.run = run
    original_backup = lab.backup
    def backup():
        result = original_backup()
        from test_restore import support
        import tempfile
        archive = lab.backups[-1]
        with tempfile.TemporaryDirectory(dir=lab.obj.work) as directory:
            content = Path(directory)/'content'; support.validate(archive, content)
            dump = subprocess.check_output(['pg_dump', '-Fc', '--host='+url.query['host'], '--port='+str(url.query['port']), '--dbname='+database])
            parts = {p.name: p.read_bytes() for p in content.iterdir() if p.name != 'SHA256SUMS'}
            parts['database.dump'] = dump
            rebuilt = package({'root': Path(directory)}, parts)
            archive.write_bytes(rebuilt.read_bytes())
        return result
    lab.backup = backup
    try:
        migrate(updater.old, 'head')
        with engine.begin() as c:
            c.execute(text("INSERT INTO preserved(value) VALUES ('dato anterior ñ')"))
        lab.bind(updater)
        updater.record('preparing', source_snapshot=u.release_snapshot(updater.old), unit_hash=u.digest(updater.unit), site_hash=u.digest(updater.site))
        tree = lab.incoming(updater)
        (tree/'alembic/env.py').write_text(environment)
        (tree/'alembic/versions/old.py').write_text(old_script)
        (tree/'alembic/versions/new.py').write_text(new_script)
        updater.record('preparing', release_hashes={str(p.relative_to(tree)): u.digest(p) for p in tree.rglob('*') if p.is_file()})
        updater.prepare(tree); updater.backup()
        lab.fail = 'health'; monkeypatch.setattr('time.sleep', lambda _: None)
        with pytest.raises(u.UpdateError):
            updater.activate()
        updater.failure(); lab.fail = None
        assert revision() == 'new'
        obj = lab.recovery(); obj.db_revision = revision
        obj.preflight(); obj.begin()
        incoming = lab.incoming(obj)
        shutil.copytree(updater.target/'alembic', incoming/'alembic', dirs_exist_ok=True)
        (incoming/'alembic/versions/later.py').write_text("""from alembic import op
revision='later'
down_revision='new'
def upgrade():op.execute('ALTER TABLE preserved ADD COLUMN recovery_probe text')
def downgrade():pass
""")
        obj.record('preparing', release_hashes={str(p.relative_to(incoming)): u.digest(p) for p in incoming.rglob('*') if p.is_file()})
        obj.prepare(incoming); obj.backup(); obj.activate()
        with engine.connect() as c:
            assert c.scalar(text('SELECT version_num FROM alembic_version')) == 'later'
            assert c.execute(text('SELECT value, first_probe, recovery_probe FROM preserved')).one() == ('dato anterior ñ', None, None)
        assert len(lab.backups) == 2 and all(p.exists() for p in lab.backups)
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE '+database))


def test_diagnostic_write_failure_still_stops(failed, monkeypatch):
    obj = prepare(failed)
    obj.record('checking'); failed.active = True; failed.enabled = True
    monkeypatch.setattr(obj, 'record', lambda *a, **kw: (_ for _ in ()).throw(OSError('disk full')))
    obj.failure()
    assert not failed.active and not failed.enabled
    assert obj.state.exists() and failed.backups[0].exists()


def test_disable_failure_still_attempts_stop(failed):
    obj = prepare(failed)
    obj.record('checking'); failed.active = True
    original = obj.run
    def run(args, **kwargs):
        if args[:2] == ['systemctl', 'disable']:
            u.fail('disable failed')
        return original(args, **kwargs)
    obj.run = run; obj.failure()
    assert not failed.active


def test_original_history_exchange_interruption_can_retry(failed, monkeypatch):
    obj = failed.recovery(); obj.preflight()
    original = u.exchange
    monkeypatch.setattr(u, 'exchange', lambda *a: u.fail('before state exchange'))
    with pytest.raises(u.UpdateError):
        obj.begin()
    monkeypatch.setattr(u, 'exchange', original)
    retry = failed.recovery(); retry.preflight(); retry.begin()
    assert retry.data['parent_operation_id']
    assert len(failed.backups) == 1 and not failed.active


def test_extra_state_component_refused(failed):
    obj = failed.recovery(); (obj.state/'foreign').write_text('unexpected')
    with pytest.raises(u.UpdateError, match='Estructura'):
        obj.preflight()


def test_recovery_venv_tampering_refused(failed):
    obj = failed.recovery()
    release = obj.current.resolve()
    (release/'.venv').mkdir(); (release/'.venv/foreign.py').write_text('unexpected installed code')
    with pytest.raises(u.UpdateError, match='alterado'):
        obj.preflight()


def test_partial_venv_without_evidence_requires_intervention(failed):
    obj = failed.recovery(); obj.preflight(); obj.begin()
    incoming = failed.incoming(obj)
    obj.record('preparing', target_inode=u.stamp(incoming))
    u.rs.rename_exclusive(incoming, obj.target)
    (obj.target/'.venv/bin').mkdir(parents=True)
    (obj.target/'.venv/bin/pip').write_text('unverified partial executable')
    retry = failed.recovery()
    with pytest.raises(u.UpdateError, match='venv parcial'):
        retry.preflight()
    assert not failed.active and len(failed.backups) == 1


def test_prepared_recovery_tampering_not_accepted_on_retry(failed):
    obj = prepare(failed)
    (obj.target/'src/ticketyn/main.py').write_text('tampered')
    retry = failed.recovery()
    with pytest.raises(u.UpdateError, match='alterado'):
        retry.preflight()


def test_pointer_changed_during_checks_does_not_enable(failed):
    obj = prepare(failed)
    original = obj.healthy
    def healthy(release):
        original(release)
        obj.current.rename(obj.base/'saved-pointer')
        obj.current.symlink_to(obj.target)
    obj.healthy = healthy
    with pytest.raises(u.UpdateError, match='current'):
        obj.activate()
    obj.failure()
    assert not failed.active and not failed.enabled and obj.state.exists()


def test_actual_legacy_fields_cannot_be_promoted(failed):
    obj = failed.recovery()
    data = json.loads((obj.state/'state.json').read_text())
    # Exactly the historical v1 evidence: target hashes, backup/OID/cluster;
    # no source snapshot, independent receipt, or activated pointer identity.
    for key in ('kind', 'checkpoint', 'source_snapshot', 'target_snapshot', 'activated_current_inode', 'unit_hash', 'site_hash'):
        data.pop(key, None)
    data['format'] = 'ticketyn-update-v1'
    (obj.state/'state.json').write_text(json.dumps(data))
    assert data['backup_sha256'] and data['release_hashes'] and data['db_oid']
    with pytest.raises(u.UpdateError, match='estado v1'):
        obj.preflight()
    assert not failed.active and len(failed.backups) == 1
