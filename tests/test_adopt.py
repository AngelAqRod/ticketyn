"""Adoption only operates on isolated paths; SQL and services are read-only mocks."""
import importlib.util
import os
from pathlib import Path
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('adopt_support', ROOT/'deploy/adopt_support.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
u = a.u


@pytest.fixture
def lab(tmp_path, monkeypatch):
    base = tmp_path/'opt'; base.mkdir(); (base/'releases').mkdir()
    old = base/'releases/0.1.0'; old.mkdir()
    (old/'.git').mkdir()
    cfg = tmp_path/'etc'; cfg.mkdir(mode=0o700)
    backups = tmp_path/'backups'; backups.mkdir(mode=0o700)
    obj = a.Adopter(base=base, config=cfg, backups=backups, lock=tmp_path/'lock', command=tmp_path/'bin/ticketyn-update')
    obj.command.parent.mkdir()
    (base/'current').symlink_to(old)
    # Literal baseline blobs, not arbitrary fixtures accepted by the validator.
    result = subprocess.run(['git', '-C', str(ROOT), 'ls-tree', '-rz', a.COMMIT], check=True, capture_output=True)
    blobs = {}
    for record in result.stdout.split(b'\0'):
        if not record: continue
        header, name = record.split(b'\t', 1); mode, kind, oid = header.split()
        name = os.fsdecode(name)
        data = subprocess.run(['git', '-C', str(ROOT), 'cat-file', 'blob', oid.decode()], check=True, capture_output=True).stdout
        blobs[name] = data
        file = old/name; file.parent.mkdir(parents=True, exist_ok=True); file.write_bytes(data)
    venv = old/'.venv'; (venv/'bin').mkdir(parents=True)
    (venv/'pyvenv.cfg').write_text('home = /usr/bin\ninclude-system-site-packages = false\nversion = 3.11.9\n')
    (venv/'bin/python').symlink_to(Path('/usr/bin/python3').resolve())
    site_packages = venv/'lib/python3.11/site-packages'; site_packages.mkdir(parents=True)
    import shutil
    shutil.copytree(old/'src/ticketyn', site_packages/'ticketyn')
    pins = ['ticketyn==0.1.0']+[line for line in (old/'requirements.lock').read_text().splitlines() if line and not line.startswith('#')]
    for pin in pins:
        name, version = pin.split('==')
        metadata = site_packages/(name.replace('-', '_')+'-'+version+'.dist-info')
        metadata.mkdir(); (metadata/'METADATA').write_text('Metadata-Version: 2.1\nName: '+name+'\nVersion: '+version+'\n')
    obj.unit = tmp_path/'ticketyn.service'; obj.unit.write_bytes(blobs['deploy/systemd/ticketyn.service'])
    obj.site = tmp_path/'ticketyn.conf'; obj.site.write_bytes(blobs['deploy/nginx/ticketyn.conf'])
    obj.link = tmp_path/'enabled'; obj.link.symlink_to(obj.site)
    obj.env.write_text('DATABASE_URL=postgresql+psycopg://ticketyn:TEST_SECRET@127.0.0.1:5432/ticketyn\n'); obj.env.chmod(0o600)
    def git(*args, binary=False):
        if args[0] == 'config': return b''
        if args[0] in ('fsck', 'for-each-ref'): return ''
        if args[0] == 'rev-parse': return str(old) if args[1] == '--show-toplevel' else a.COMMIT
        if args[0] == 'status': return ''
        if args[0] == 'ls-tree': return result.stdout
        if args[0] == 'ls-files':
            records = []
            for entry in result.stdout.split(b'\0'):
                if entry:
                    header, name = entry.split(b'\t',1); mode, kind, oid = header.split()
                    records.append(mode+b' '+oid+b' 0\t'+name)
            return b'\0'.join(records)+b'\0'
        if args[0] == 'cat-file':
            return subprocess.run(['git', '-C', str(ROOT), *args], check=True, capture_output=True).stdout
        if args[0] == 'show': return blobs[args[1].split(':', 1)[1]].decode().strip()
        raise AssertionError(args)
    monkeypatch.setattr(obj, 'git', git)
    calls = []
    def run(args, **kwargs):
        calls.append(list(map(str,args)))
        if args[0] == 'systemctl' and 'FragmentPath' in ' '.join(map(str,args)): return str(obj.unit)
        if args[0] == 'systemctl' and 'show' in args:
            prop = next(x.split('=',1)[1] for x in args if str(x).startswith('--property='))
            loaded = {'User':'ticketyn','Group':'ticketyn','WorkingDirectory':'/opt/ticketyn/current',
                      'EnvironmentFiles':'/etc/ticketyn/ticketyn.env (ignore_errors=no)',
                      'Environment':'PYTHONDONTWRITEBYTECODE=1','UMask':'0077', 'NoNewPrivileges':'yes',
                      'PrivateTmp':'yes','ProtectSystem':'full','ProtectHome':'yes',
                      'Type':'simple','LoadState':'loaded','DynamicUser':'no',
                      'ExecStart':'{ path=/opt/ticketyn/current/.venv/bin/uvicorn ; argv[]=/opt/ticketyn/current/.venv/bin/uvicorn ticketyn.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1 ; ignore_errors=no ; }'}
            return loaded.get(prop, '')
        if args[0] == 'python3' and 'port' in args: return '80'
        if '--database-identity' in args: return 'ticketyn:ticketyn:12345:'+a.REVISION
        if args[:2] == ['nginx', '-T']: return '# configuration file '+str(obj.link)+':\n'+obj.site.read_text()
        return ''
    monkeypatch.setattr(obj, 'run', run)
    monkeypatch.setattr(obj, 'authenticate', lambda: 'ticketyn:ticketyn:12345')
    monkeypatch.setattr(obj, 'head', lambda path: a.REVISION)
    monkeypatch.setattr(obj, 'db_revision', lambda: a.REVISION)
    def pg(sql, database='postgres'):
        assert sql.startswith('SELECT '), 'Adoption must never mutate PostgreSQL'
        calls.append(['sql', sql])
        if 'pg_get_userbyid' in sql: return 'ticketyn:UTF8'
        if 'system_identifier' in sql: return '123456789'
        return '12345'
    monkeypatch.setattr(obj, 'pg', pg)
    monkeypatch.setattr(obj, 'healthy', lambda path: None)
    obj.scripts = ROOT
    obj.calls = calls
    return obj


def test_success_evidence_and_updater_contract(lab):
    lab.execute()
    receipt = u.read_json(lab.installed/'adoption.json')
    assert receipt['commit'] == a.COMMIT and receipt['revision'] == a.REVISION
    assert receipt['origin'] == 'adopted' and receipt['db_oid'] == '12345'
    assert receipt['release_snapshot']['pyproject.toml'] == u.digest(lab.old/'pyproject.toml')
    assert (lab.installed/'format').read_text().strip() == '1'
    assert (lab.installed/'status').read_text().strip() == 'complete'
    assert lab.command.stat().st_mode & 0o777 == 0o755
    assert lab.installed.stat().st_mode & 0o777 == 0o700
    for file in lab.installed.iterdir(): assert file.stat().st_mode & 0o777 == 0o600
    assert 'TEST_SECRET' not in str(receipt)
    assert all(not any(x in ' '.join(call) for x in ('migrate', 'restart', 'stop', 'reload', 'pg_dump')) for call in lab.calls)
    before = lab.current.readlink()
    with pytest.raises(u.UpdateError, match='install-state'): lab.execute()
    assert lab.current.readlink() == before
    # The real normal updater accepts format, deployment and identities.
    updater = u.Updater('v0.1.1', base=lab.base, config=lab.config, backups=lab.config/'backups')
    updater.backups.mkdir(mode=0o700)
    updater.unit, updater.site, updater.link = lab.unit, lab.site, lab.link
    updater.run = lab.run; updater.head = lab.head; updater.db_revision = lab.db_revision
    updater.pg = lab.pg; updater.healthy = lab.healthy
    updater.preflight()
    assert updater.source_version == '0.1.0'


@pytest.mark.parametrize('kind', ['outside', 'file', 'wrong-version', 'env-mode', 'env-content',
                                  'unit', 'nginx', 'link', 'update-state', 'restore-state', 'install-state',
                                  'modified', 'local-changes', 'commit', 'revision', 'owner', 'oid', 'cluster',
                                  'head', 'inactive', 'disabled', 'health', 'dropins', 'fragment', 'extra-listen',
                                  'project-version', 'release-mode', 'env-symlink', 'backup-mode', 'credentials', 'unknown-listen'])
def test_fail_closed(lab, tmp_path, monkeypatch, kind):
    if kind in ('outside', 'file', 'wrong-version'):
        lab.current.unlink()
        if kind == 'file': lab.current.write_text('not link')
        else:
            target = tmp_path if kind == 'outside' else lab.releases/'0.2.0'
            target.mkdir(exist_ok=True); lab.current.symlink_to(target)
    elif kind == 'env-mode': lab.env.chmod(0o644)
    elif kind == 'env-content': lab.env.write_text('INVALID=secret')
    elif kind == 'project-version': (lab.releases/'0.1.0/pyproject.toml').write_text('[project]\nversion="0.2.0"\n')
    elif kind == 'release-mode': (lab.releases/'0.1.0').chmod(0o777)
    elif kind == 'backup-mode': lab.backups.chmod(0o755)
    elif kind == 'env-symlink':
        saved = lab.config/'saved.env'; lab.env.rename(saved); lab.env.symlink_to(saved)
    elif kind == 'unit': lab.unit.write_text('User=root')
    elif kind == 'nginx': lab.site.write_text('listen 80;\nroot /tmp;')
    elif kind == 'link': lab.link.unlink(); lab.link.symlink_to(lab.unit)
    elif kind.endswith('-state'): (lab.config/kind).mkdir()
    elif kind == 'modified': (lab.releases/'0.1.0/src/ticketyn/main.py').write_text('tampered')
    elif kind in ('local-changes', 'commit'):
        original = lab.git
        monkeypatch.setattr(lab, 'git', lambda *args, **kw: 'modified' if args[0] == ('status' if kind == 'local-changes' else 'rev-parse') and args[1] != '--show-toplevel' else original(*args, **kw))
    elif kind == 'revision': monkeypatch.setattr(lab, 'db_revision', lambda: '0005_wrong')
    elif kind == 'head': monkeypatch.setattr(lab, 'head', lambda path: '0005_wrong')
    elif kind in ('owner','oid','cluster'):
        original = lab.pg
        def pg(sql, database='postgres'):
            field = {'owner':'pg_get_userbyid','oid':'SELECT oid','cluster':'system_identifier'}[kind]
            return 'unexpected' if field in sql else original(sql, database)
        monkeypatch.setattr(lab, 'pg', pg)
    elif kind == 'credentials': monkeypatch.setattr(lab, 'authenticate', lambda: 'otra:ticketyn:12345')
    elif kind == 'health': monkeypatch.setattr(lab, 'healthy', lambda path: u.fail('health'))
    else:
        original = lab.run
        def run(args, **kwargs):
            text = ' '.join(map(str,args))
            if kind in ('inactive','disabled') and ('is-enabled' if kind == 'disabled' else 'is-active') in text: u.fail('servicio no disponible')
            if kind == 'credentials' and '--database-identity' in args: return 'otra:ticketyn:12345:'+a.REVISION
            if kind == 'dropins' and 'DropInPaths' in text: return '/tmp/dropin'
            if kind == 'fragment' and 'FragmentPath' in text: return '/tmp/unit'
            result = original(args, **kwargs)
            if kind == 'extra-listen' and args[:2] == ['nginx','-T']: result += '\nlisten 80;'
            if kind == 'unknown-listen' and args[:2] == ['nginx','-T']: result += '\nlisten localhost;'
            return result
        monkeypatch.setattr(lab, 'run', run)
    with pytest.raises((u.UpdateError, u.rs.RestoreError, OSError, ValueError)):
        lab.execute()
    assert not lab.installed.exists() if kind != 'install-state' else True
    assert not lab.command.exists()


@pytest.mark.parametrize('phase', ['provision', 'revalidate', 'rename', 'after-rename'])
def test_interruption_retry(lab, monkeypatch, phase):
    original_install, original_validate, original_rename = a.p.install, lab.validate, u.rs.rename_exclusive
    if phase == 'provision': monkeypatch.setattr(a.p, 'install', lambda *args: (_ for _ in ()).throw(InterruptedError()))
    if phase == 'revalidate':
        count = [0]
        def validate():
            count[0] += 1
            if count[0] == 2: raise InterruptedError()
            return original_validate()
        monkeypatch.setattr(lab, 'validate', validate)
    if phase in ('rename','after-rename'):
        def rename(source, target):
            if target == lab.installed:
                if phase == 'after-rename': original_rename(source,target)
                raise InterruptedError()
            return original_rename(source,target)
        monkeypatch.setattr(u.rs, 'rename_exclusive', rename)
    with pytest.raises(InterruptedError): lab.execute()
    assert not list(lab.config.glob('.adoption-*'))
    monkeypatch.setattr(a.p, 'install', original_install); monkeypatch.setattr(lab, 'validate', original_validate)
    monkeypatch.setattr(u.rs, 'rename_exclusive', original_rename)
    if phase == 'after-rename':
        assert (lab.installed/'status').read_text().strip() == 'complete'
        with pytest.raises(u.UpdateError): lab.execute()
    else:
        assert not lab.installed.exists()
        lab.execute()


def test_requires_root():
    if os.geteuid() == 0: pytest.skip('non-root check')
    result = subprocess.run([ROOT/'adopt.sh'], capture_output=True, text=True)
    assert result.returncode and 'root' in result.stderr


def test_real_git_verification_and_hidden_modification(tmp_path):
    # Offline local clone, independent object files; never touches active/DEV.
    release = tmp_path/'0.1.0'
    subprocess.run(['git','clone','--no-hardlinks','--no-checkout',str(ROOT),str(release)],check=True,capture_output=True)
    subprocess.run(['git','-C',str(release),'checkout','--detach',a.COMMIT],check=True,capture_output=True)
    obj = a.Adopter(); obj.old = release
    assert obj.verify_git()['pyproject.toml'] == u.digest(release/'pyproject.toml')
    subprocess.run(['git','-C',str(release),'update-index','--assume-unchanged','src/ticketyn/main.py'],check=True)
    (release/'src/ticketyn/main.py').write_text('hidden modification')
    with pytest.raises(u.UpdateError, match='distinto'): obj.verify_git()
    subprocess.run(['git','-C',str(release),'config','include.path','/tmp/untrusted-config'],check=True)
    with pytest.raises(u.UpdateError, match='Configuración Git externa'): obj.verify_git()


@pytest.mark.parametrize('text,valid', [('listen 80;\nlisten [::]:80;',True),('listen 80;',True),
                                       ('listen 80;\nlisten [::]:81;',False),('listen [::]:80;',False)])
def test_baseline_ipv6_port(tmp_path, text, valid, capsys):
    path = tmp_path/'site'; path.write_text(text)
    if valid:
        u.rs.port(path); assert capsys.readouterr().out.strip() == '80'
    else:
        with pytest.raises(u.rs.RestoreError): u.rs.port(path)


@pytest.mark.parametrize('target', ['current', 'env', 'unit', 'site', 'release'])
def test_unexpected_ownership(lab, monkeypatch, target):
    path = {'current': lab.current, 'env': lab.env, 'unit': lab.unit,
            'site': lab.site, 'release': lab.releases/'0.1.0'}[target]
    original = Path.lstat
    def lstat(self):
        info = original(self)
        if self == path:
            values = list(info); values[4] = os.geteuid()+1
            return os.stat_result(values)
        return info
    monkeypatch.setattr(Path, 'lstat', lstat)
    with pytest.raises(u.UpdateError): lab.execute()
    assert not lab.installed.exists() and not lab.command.exists()


def test_changes_during_provision_fail_closed(lab, monkeypatch):
    original = a.p.install
    def install(*args):
        result = original(*args)
        lab.env.write_text('DATABASE_URL=postgresql+psycopg://ticketyn:OTHER_SECRET@127.0.0.1:5432/ticketyn\n')
        return result
    monkeypatch.setattr(a.p, 'install', install)
    with pytest.raises(u.UpdateError, match='cambió'): lab.execute()
    assert not lab.installed.exists()


def test_no_secrets_in_output(lab, capsys):
    lab.execute()
    output = capsys.readouterr()
    assert 'TEST_SECRET' not in output.out+output.err
    assert 'DATABASE_URL' not in output.out+output.err


@pytest.mark.parametrize('signum', [a.signal.SIGINT, a.signal.SIGTERM])
def test_signal_handler_aborts_before_publication(monkeypatch, signum):
    handlers = {}
    monkeypatch.setattr(a.signal, 'signal', lambda number, callback: handlers.update({number: callback}))
    monkeypatch.setattr(a.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(a.os, 'getegid', lambda: 0)
    monkeypatch.setattr(a.os, 'umask', lambda mask: 0o022)
    monkeypatch.setattr(a.sys, 'argv', ['adopt_support.py'])
    class Pending:
        def execute(self): handlers[signum](signum, None)
    monkeypatch.setattr(a, 'Adopter', Pending)
    with pytest.raises(InterruptedError): a.main()


def test_adoption_reads_real_postgres_without_migrating(lab, postgres_engine, monkeypatch):
    """Fixture provisions a disposable baseline; adoption itself only SELECTs.

    Services/venv remain isolated doubles: no host production commands executed.
    """
    from sqlalchemy import create_engine, text
    from ticketyn.db.base import Base
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        assert not admin.scalar(text("SELECT 1 FROM pg_database WHERE datname='ticketyn'"))
        assert not admin.scalar(text("SELECT 1 FROM pg_roles WHERE rolname='ticketyn'"))
        admin.execute(text('CREATE ROLE ticketyn LOGIN'))
        admin.execute(text("CREATE DATABASE ticketyn OWNER ticketyn TEMPLATE template0 ENCODING 'UTF8'"))
    engine = create_engine(postgres_engine.url.set(database='ticketyn', username='ticketyn'))
    try:
        Base.metadata.create_all(engine)  # Fixture only; no Alembic execution.
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)'))
            connection.execute(text('INSERT INTO alembic_version VALUES (:revision)'), {'revision': a.REVISION})
            connection.execute(text("INSERT INTO customers(customer_code,name,active) VALUES ('ADOPT_TEST','Ficticio',true)"))
        def pg(sql, database='postgres'):
            assert sql.startswith('SELECT ')
            selected = engine if database == 'ticketyn' else postgres_engine
            with selected.connect() as connection:
                connection.execute(text('SET TRANSACTION READ ONLY'))
                return str(connection.execute(text(sql)).scalar_one())
        monkeypatch.setattr(lab, 'pg', pg)
        monkeypatch.setattr(lab, 'db_revision', lambda: pg('SELECT version_num FROM alembic_version', 'ticketyn'))
        original_run = lab.run
        def run(args, **kwargs):
            if '--database-identity' in args:
                return 'ticketyn:ticketyn:'+pg("SELECT oid FROM pg_database WHERE datname='ticketyn'")+':'+a.REVISION
            return original_run(args, **kwargs)
        monkeypatch.setattr(lab, 'run', run)
        monkeypatch.setattr(lab, 'authenticate', lambda: 'ticketyn:ticketyn:'+pg("SELECT oid FROM pg_database WHERE datname='ticketyn'"))
        before = pg("SELECT oid FROM pg_database WHERE datname='ticketyn'")
        lab.execute()
        assert pg('SELECT customer_code FROM customers', 'ticketyn') == 'ADOPT_TEST'
        assert pg("SELECT oid FROM pg_database WHERE datname='ticketyn'") == before
        assert lab.db_revision() == a.REVISION
        receipt = u.read_json(lab.installed/'adoption.json')
        assert receipt['db_oid'] == before
        assert receipt['cluster'] == pg('SELECT system_identifier FROM pg_control_system()')
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE ticketyn'))
            admin.execute(text('DROP ROLE ticketyn'))


@pytest.mark.parametrize('arguments', [['--force'], ['v0.1.0'], ['--recover', 'v0.1.1']])
def test_no_bypass_arguments(monkeypatch, arguments):
    monkeypatch.setattr(a.os, 'geteuid', lambda: 0)
    monkeypatch.setattr(a.sys, 'argv', ['adopt_support.py', *arguments])
    with pytest.raises(u.UpdateError, match='no acepta'): a.main()


def test_installer_rejects_completed_adoption_without_fabricated_fields(lab):
    lab.execute()
    result = subprocess.run(['bash', '-c', '''
source "$1"
protected_path() { [[ ! -L $1 && $(stat -c %a "$1") == "$2" ]] || fail "Estado inseguro"; }
INSTALL_STATE="$2"
load_state
echo SHOULD_NOT_RUN
''', 'test', str(ROOT/'install.sh'), str(lab.installed)], capture_output=True, text=True)
    assert result.returncode != 0 and 'ya fue adoptado' in result.stderr
    assert 'SHOULD_NOT_RUN' not in result.stdout
    assert not (lab.installed/'token').exists()


def test_audit_corrupt_oid_matching_file_assume_unchanged_rejected(tmp_path):
    import zlib
    release = tmp_path/'0.1.0'
    subprocess.run(['git','clone','--no-hardlinks','--no-checkout',str(ROOT),str(release)],check=True,capture_output=True)
    subprocess.run(['git','-C',str(release),'checkout','--detach',a.COMMIT],check=True,capture_output=True)
    name = 'src/ticketyn/main.py'
    oid = subprocess.check_output(['git','-C',str(release),'rev-parse',a.COMMIT+':'+name]).decode().strip()
    changed = (release/name).read_bytes()+b'\n# coherent forged blob\n'
    object_path = release/'.git/objects'/oid[:2]/oid[2:]
    object_path.parent.mkdir(exist_ok=True)
    if object_path.exists(): object_path.chmod(0o600)
    object_path.write_bytes(zlib.compress(b'blob '+str(len(changed)).encode()+b'\0'+changed))
    (release/name).write_bytes(changed)
    subprocess.run(['git','-C',str(release),'update-index','--assume-unchanged',name],check=True)
    obj = a.Adopter(); obj.old = release
    with pytest.raises(u.UpdateError): obj.verify_git()


@pytest.mark.parametrize('mechanism', ['alternates','http-alternates','replace','grafts','shallow'])
def test_external_git_resolution_rejected(lab, mechanism, monkeypatch):
    lab.old = lab.releases/'0.1.0'
    if mechanism == 'replace':
        original = lab.git
        monkeypatch.setattr(lab, 'git', lambda *args, **kw: 'refs/replace/anything' if args[0]=='for-each-ref' else original(*args, **kw))
    else:
        name = {'alternates':'objects/info/alternates','http-alternates':'objects/info/http-alternates',
                'grafts':'info/grafts','shallow':'shallow'}[mechanism]
        path = lab.old/'.git'/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text('/external')
    with pytest.raises(u.UpdateError): lab.verify_git()


@pytest.mark.parametrize('kind', ['external-python','writable-cache','changed-installed-source','pth','external-lib'])
def test_runtime_rejects_before_any_release_execution(lab, tmp_path, kind):
    old = lab.releases/'0.1.0'
    if kind == 'external-python':
        external = tmp_path/'evil'; external.write_text('must not execute'); external.chmod(0o777)
        interpreter = old/'.venv/bin/python'; interpreter.unlink(); interpreter.symlink_to(external)
    elif kind == 'writable-cache':
        path = old/'src/ticketyn/__pycache__'; path.mkdir(); path.chmod(0o777)
    elif kind == 'changed-installed-source':
        (old/'.venv/lib/python3.11/site-packages/ticketyn/main.py').write_text('evil')
    elif kind == 'pth':
        (old/'.venv/lib/python3.11/site-packages/evil.pth').write_text('import evil')
    else:
        (old/'.venv/lib64').symlink_to(tmp_path)
    with pytest.raises((u.UpdateError, ValueError)): lab.execute()
    assert not lab.installed.exists()
    assert not any('.venv/bin/' in ' '.join(call) for call in lab.calls)


def test_audit_world_writable_ancestor_rejected(tmp_path):
    parent = tmp_path/'unsafe'; parent.mkdir(); parent.chmod(0o777)
    child = parent/'safe'; child.mkdir(mode=0o700)
    with pytest.raises(u.UpdateError, match='Ancestro'): u.secure(child,directory=True)
    with pytest.raises(ValueError, match='Ancestro'): a.p.secure(child,directory=True)


@pytest.mark.parametrize('property', ['User','Group','WorkingDirectory','EnvironmentFiles','Environment','ExecStart'])
def test_correct_disk_stale_loaded_systemd_rejected(lab, monkeypatch, property):
    original = lab.run
    def run(args, **kwargs):
        if '--property='+property in args: return 'stale'
        return original(args, **kwargs)
    monkeypatch.setattr(lab,'run',run)
    with pytest.raises(u.UpdateError,match='cargad'): lab.execute()
    assert not lab.installed.exists()


def test_audit_commented_ipv6_is_not_active(lab):
    lab.site.write_text(lab.site.read_text().replace('listen [::]:80;', '# listen [::]:80;'))
    lab.execute()
    assert lab.installed.exists()


@pytest.mark.parametrize('change', ['invalid-json','changed-receipt','wrong-origin','missing-seal','inconsistent-sealed'])
def test_updater_rejects_adoption_tampering(lab, change):
    lab.execute()
    path = lab.installed/'adoption.json'
    if change == 'invalid-json': path.write_text('{bad')
    elif change == 'changed-receipt': path.write_text(path.read_text()+' ')
    elif change == 'wrong-origin': (lab.installed/'origin').write_text('other')
    elif change == 'missing-seal': (lab.installed/'adoption.sha256').unlink()
    else:
        data = u.read_json(path); data['commit'] = '0'*40; u.write_json(path,data)
        (lab.installed/'adoption.sha256').write_text(u.digest(path))
    with pytest.raises((u.UpdateError, ValueError, OSError)):
        updater = u.Updater('v0.1.1',base=lab.base,config=lab.config,backups=lab.backups)
        updater.preflight()


def test_adoption_receipt_survives_legitimate_new_generation(lab):
    lab.execute()
    before = (lab.installed/'adoption.json').read_bytes()
    # Historical provenance must not bind future healthy generations to baseline
    # DB OID/current/env. Normal updater/restore validate the active identity.
    new = lab.releases/'0.2.0'; new.mkdir()
    (new/'pyproject.toml').write_text('[project]\nversion="0.2.0"\n')
    lab.current.unlink(); lab.current.symlink_to(new)
    lab.env.write_text('DATABASE_URL=postgresql+psycopg://ticketyn:RESTORED@127.0.0.1:5432/ticketyn\n')
    u.validate_adoption(lab.installed,lab.base)
    updater = u.Updater('v0.2.1',base=lab.base,config=lab.config,backups=lab.backups)
    updater.unit, updater.site, updater.link = lab.unit, lab.site, lab.link
    updater.run, updater.head, updater.db_revision = lab.run, lab.head, lab.db_revision
    original_pg = lab.pg
    updater.pg = lambda sql,database='postgres': '99999' if 'SELECT oid' in sql else original_pg(sql,database)
    updater.healthy = lab.healthy
    updater.preflight()
    assert updater.source_version == '0.2.0' and updater.db_oid == '99999'
    assert (lab.installed/'adoption.json').read_bytes() == before


def test_readonly_psql_options_and_no_dml(lab, monkeypatch):
    captured = []
    monkeypatch.setattr(lab,'run',lambda args,**kwargs: captured.append(args) or 'on')
    assert a.Adopter.pg(lab,'SELECT current_setting(\'transaction_read_only\')') == 'on'
    assert any('default_transaction_read_only=on' in arg for arg in captured[0])
    assert any('search_path=pg_catalog' in arg for arg in captured[0])
    with pytest.raises(u.UpdateError): a.Adopter.pg(lab,'CREATE TABLE forbidden(id int)')


@pytest.mark.parametrize('shape', ['v:ticketyn:1043:false','r:other:1043:false','r:ticketyn:23:false','r:ticketyn:1043:true'])
def test_alembic_object_shape_rejected_before_read(lab, monkeypatch, shape):
    queries = []
    monkeypatch.setattr(lab,'pg',lambda sql,database='postgres': queries.append(sql) or shape)
    with pytest.raises(u.UpdateError): a.Adopter.db_revision(lab)
    assert len(queries) == 1 and 'pg_catalog.pg_class' in queries[0]


def test_authentication_anonymous_fd_readonly_no_secret_arguments(lab, monkeypatch, capsys):
    from types import SimpleNamespace
    def run(args, **kwargs):
        assert 'TEST_SECRET' not in str(args)+str(kwargs['env'])
        assert 'default_transaction_read_only=on' in kwargs['env']['PGOPTIONS']
        fd, = kwargs['pass_fds']
        assert os.fstat(fd).st_mode & 0o777 == 0o600
        assert os.read(fd,1000).endswith(b':TEST_SECRET\n')
        return SimpleNamespace(stdout='ticketyn:ticketyn:12345\n')
    monkeypatch.setattr(a.subprocess,'run',run)
    assert a.Adopter.authenticate(lab) == 'ticketyn:ticketyn:12345'
    assert 'TEST_SECRET' not in str(capsys.readouterr())


def test_adoption_requires_durable_valid_updater_before_state(lab, monkeypatch):
    original = a.p.validate_publication
    calls = []
    def validate(*args, **kwargs):
        calls.append('publication')
        assert not lab.installed.exists()
        original(*args, **kwargs)
    monkeypatch.setattr(a.p,'validate_publication',validate)
    lab.execute()
    assert len(calls) >= 2


def test_real_postgres_readonly_even_select_function_cannot_write(lab, postgres_engine, monkeypatch):
    """Actual psql/PGOPTIONS on the disposable cluster; never host postgres."""
    from sqlalchemy import text
    import getpass
    with postgres_engine.begin() as connection:
        connection.execute(text('CREATE TABLE public.adopt_readonly_probe (value integer)'))
        connection.execute(text("CREATE FUNCTION public.adopt_write_probe() RETURNS integer LANGUAGE plpgsql AS $$ BEGIN INSERT INTO public.adopt_readonly_probe VALUES (1); RETURN 1; END $$"))
    def run(args, **kwargs):
        env = {'PATH':os.environ['PATH'], 'PGOPTIONS':next(value.split('=',1)[1] for value in args if value.startswith('PGOPTIONS='))}
        command = args[args.index('psql'):]
        command = ['--host='+postgres_engine.url.query['host'] if value.startswith('--host=')
                   else '--port='+postgres_engine.url.query['port'] if value.startswith('--port=')
                   else '--username='+getpass.getuser() if value.startswith('--username=') else value for value in command]
        return subprocess.run(command,env=env,capture_output=True,text=True,check=True).stdout.strip()
    monkeypatch.setattr(lab,'run',run)
    try:
        assert a.Adopter.pg(lab,"SELECT current_setting('transaction_read_only')") == 'on'
        with pytest.raises(subprocess.CalledProcessError):
            a.Adopter.pg(lab,'SELECT public.adopt_write_probe()')
        with postgres_engine.connect() as connection:
            assert connection.scalar(text('SELECT count(*) FROM public.adopt_readonly_probe')) == 0
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(text('DROP FUNCTION public.adopt_write_probe()'))
            connection.execute(text('DROP TABLE public.adopt_readonly_probe'))


def test_ticketyn_cached_bytecode_cannot_override_verified_source(lab):
    import importlib.util, marshal
    old = lab.releases/'0.1.0'
    source = old/'.venv/lib/python3.11/site-packages/ticketyn/main.py'
    cache = Path(importlib.util.cache_from_source(str(source)))
    cache.parent.mkdir(exist_ok=True)
    cache.write_bytes(importlib.util.MAGIC_NUMBER+b'\0'*12+marshal.dumps(compile('print("evil")',str(source),'exec')))
    with pytest.raises(u.UpdateError,match='Bytecode'): lab.execute()
    assert not lab.installed.exists()


def test_verified_ticketyn_bytecode_is_read_not_executed(lab):
    import importlib.util, marshal
    source = lab.releases/'0.1.0/.venv/lib/python3.11/site-packages/ticketyn/main.py'
    cache = Path(importlib.util.cache_from_source(str(source)))
    cache.parent.mkdir(exist_ok=True)
    cache.write_bytes(importlib.util.MAGIC_NUMBER+b'\0'*12+marshal.dumps(compile(source.read_bytes(),str(source),'exec')))
    lab.execute()
    assert lab.installed.exists()


def test_alembic_baseline_head_parsed_without_release_execution(lab):
    assert a.Adopter.head(lab, lab.releases/'0.1.0') == a.REVISION
    assert not any('.venv/bin/' in ' '.join(call) for call in lab.calls)


def test_entrypoint_uses_system_python_not_administrator_path():
    assert 'exec /usr/bin/python3 -I -B' in (ROOT/'adopt.sh').read_text()
    assert 'exec python3 ' not in (ROOT/'adopt.sh').read_text()


@pytest.mark.parametrize('setting', ['home = /tmp', 'include-system-site-packages = true', 'executable = /tmp/evil', 'stdlib_dir = /tmp'])
def test_venv_cannot_redirect_runtime_to_external_python(lab, setting):
    cfg = lab.releases/'0.1.0/.venv/pyvenv.cfg'
    text = cfg.read_text()
    key = setting.split('=',1)[0].strip()
    text = '\n'.join(line for line in text.splitlines() if not line.startswith(key+' ='))
    cfg.write_text(text+'\n'+setting+'\n')
    with pytest.raises(u.UpdateError): lab.execute()
    assert not lab.installed.exists()


def test_manipulated_index_rejected_before_status(lab, monkeypatch):
    lab.old = lab.releases/'0.1.0'
    original = lab.git
    calls = []
    def git(*args, **kwargs):
        calls.append(args[0])
        if args[0] == 'ls-files': return b'160000 '+a.COMMIT.encode()+b' 0\tsrc\0'
        return original(*args,**kwargs)
    monkeypatch.setattr(lab,'git',git)
    with pytest.raises(u.UpdateError,match='Índice'): lab.verify_git()
    assert 'status' not in calls
