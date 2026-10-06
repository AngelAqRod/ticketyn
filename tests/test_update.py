"""Updater helpers use isolated paths and fake services; no production mutations."""
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('update_support', ROOT/'deploy/update_support.py')
u = importlib.util.module_from_spec(spec); spec.loader.exec_module(u)


@pytest.mark.parametrize('tag', ['v0.2.0', 'v0.1.1-test.1', 'v1.2.3-rc.2', 'v1.2.3-alpha-beta', 'v1.2.3-0'])
def test_valid_tags(tag):
    assert u.tag_version(tag) == tag[1:]


@pytest.mark.parametrize('tag', ['', 'master', '-c', 'v01.2.3', 'v1.2', 'v1.2.3;rm -rf /', 'v1.2.3/evil', 'v1.2.3-01', 'v1.2.3+build', 'v1.2.3-'])
def test_invalid_tags(tag):
    with pytest.raises(u.UpdateError): u.tag_version(tag)


@pytest.mark.parametrize('source,target', [('0.1.0','0.1.0'), ('0.2.0','0.1.9'), ('0.2.0','0.2.0-test.1'), ('0.1.0','1.0.0')])
def test_reject_same_downgrade_major(source,target):
    with pytest.raises(u.UpdateError): u.forward(source,target)


@pytest.mark.parametrize('source,target', [('0.1.0','0.2.0'), ('0.1.0','0.1.1-test.1'), ('0.1.1-test.1','0.1.1'), ('0.1.1-test.2','0.1.1-test.10')])
def test_forward(source,target): u.forward(source,target)


def test_requires_root():
    if os.geteuid() == 0: pytest.skip('non-root test')
    result = subprocess.run([ROOT/'update.sh','v0.2.0'], text=True, capture_output=True)
    assert result.returncode and 'root' in result.stderr


def tar(parts):
    data=io.BytesIO()
    with tarfile.open(fileobj=data,mode='w') as archive:
        for name, value, kind in parts:
            item=tarfile.TarInfo(name); item.type=kind; item.size=len(value) if kind==tarfile.REGTYPE else 0
            if kind in (tarfile.SYMTYPE,tarfile.LNKTYPE): item.linkname='/etc/passwd'
            archive.addfile(item,io.BytesIO(value) if item.isfile() else None)
    data.seek(0); return data


@pytest.mark.parametrize('name,kind', [('src/.env',tarfile.REGTYPE), ('src/key.pem',tarfile.REGTYPE), ('src/.git/config',tarfile.REGTYPE), ('src/a',tarfile.SYMTYPE), ('src/a',tarfile.LNKTYPE), ('../evil',tarfile.REGTYPE), ('/etc/evil',tarfile.REGTYPE), ('src/test.dump',tarfile.REGTYPE)])
def test_sensitive_or_unsafe_archive(tmp_path,name,kind):
    archive=tmp_path/'source.tar'; archive.write_bytes(tar([(name,b'x',kind)]).read())
    with pytest.raises(u.UpdateError): u.extract_release(archive,tmp_path/'out')


def source(root, version='0.2.0'):
    root.mkdir(parents=True)
    for name in u.FILES+u.MAINTENANCE+('frontend/dist/index.html','frontend/dist/assets/app.js','src/ticketyn/main.py','alembic/env.py','deploy/systemd/ticketyn.service','deploy/nginx/ticketyn.conf'):
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('example')
    (root/'pyproject.toml').write_text('[project]\nversion = "'+version+'"\n')
    (root/'frontend/dist/index.html').write_text('<script src="/assets/app.js"></script>')
    return root


def test_release_allowlist_dist(tmp_path):
    tree=source(tmp_path/'tree'); (tree/'.env').write_text('SECRET'); (tree/'node_modules').mkdir()
    archive=tmp_path/'src.tar'
    with tarfile.open(archive,'w') as out:
        for path in tree.rglob('*'): out.add(path,arcname=str(path.relative_to(tree)),recursive=False)
    u.extract_release(archive,tmp_path/'out')
    assert (tmp_path/'out/frontend/dist/assets/app.js').exists()
    assert not (tmp_path/'out/.env').exists()
    assert not (tmp_path/'out/node_modules').exists()


def test_missing_frontend(tmp_path):
    archive=tmp_path/'src.tar';archive.write_bytes(tar([('pyproject.toml',b'x',tarfile.REGTYPE)]).read())
    with pytest.raises(u.UpdateError):u.extract_release(archive,tmp_path/'out')


@pytest.fixture
def updater(tmp_path):
    base=tmp_path/'opt'; config=tmp_path/'etc';backs=tmp_path/'backs'
    for p in (base/'releases',config,backs): p.mkdir(parents=True,mode=0o700)
    old=source(base/'releases/0.1.0','0.1.0'); current=base/'current'; current.symlink_to(old)
    env=config/'ticketyn.env';env.write_text('DATABASE_URL=postgresql+psycopg://ticketyn:synthetic-secret@127.0.0.1:5432/ticketyn\n');env.chmod(0o600)
    obj=u.Updater('v0.2.0',base,config,backs,tmp_path/'lock')
    obj.old=old;obj.source_version='0.1.0';obj.target=base/'releases/0.2.0';obj.revision='old';obj.env_hash=u.digest(env);obj.db_oid='123';obj.cluster='456';obj.port='8080'
    obj.work=tmp_path/'work';obj.work.mkdir(mode=0o700)
    obj.run=lambda args,**kwargs:''
    obj.begin()
    return obj


def test_state_private_no_secret(updater):
    data=(updater.state/'state.json').read_text()
    assert 'synthetic-secret' not in data and 'DATABASE_URL' not in data
    assert (updater.state.stat().st_mode&0o777)==0o700
    assert ((updater.state/'state.json').stat().st_mode&0o777)==0o600


def test_preflight_nonexistent(tmp_path):
    obj=u.Updater('v0.2.0',tmp_path/'missing',tmp_path/'etc',tmp_path/'backs',tmp_path/'lock')
    with pytest.raises(FileNotFoundError):obj.preflight()


@pytest.mark.parametrize('key,value', [('env_hash','changed'),('db_oid','9'),('cluster','9'),('target','/etc'),('origin','https://evil')])
def test_resume_identity_mismatch(updater,key,value):
    updater.data[key]=value
    with pytest.raises(u.UpdateError):updater.validate_resume()


@pytest.mark.parametrize('phase',['migrating','migrated','activating','starting','checking'])
def test_ambiguous_resume_refused(updater,phase):
    updater.data['phase']=phase
    with pytest.raises(u.UpdateError,match='interrumpida'):updater.validate_resume()


def test_safe_resume_and_foreign_destination(updater):
    updater.validate_resume()
    updater.target.mkdir(mode=0o700)
    with pytest.raises(u.UpdateError,match='propio'):updater.validate_resume()


def test_resume_changed_old_schema(updater):
    updater.revision='changed'
    with pytest.raises(u.UpdateError):updater.validate_resume()


def test_failure_before_migration_does_not_stop(updater):
    calls=[];updater.run=lambda args,**kwargs:calls.append(args) or ''
    updater.failure()
    assert not calls and updater.current.resolve()==updater.old


@pytest.mark.parametrize('phase',['migrating','migrated','activating','starting','checking'])
def test_failure_after_boundary_stops_preserves(updater,phase):
    updater.record(phase);calls=[];updater.run=lambda args,**kwargs:calls.append(args) or ''
    updater.failure()
    assert ['systemctl','stop','ticketyn'] in calls
    assert updater.old.exists() and updater.state.exists()
    assert json.loads((updater.state/'state.json').read_text())['result']=='interrupted_or_failed'


def test_failed_preflight_no_mutation(updater):
    updater.authorized=False;updater.data['phase']='migrating';calls=[];updater.run=lambda args,**kwargs:calls.append(args)
    updater.failure();assert calls==[]


def test_archive_state_allows_next_operation(updater):
    updater.record('complete',result='success');token=updater.data['operation'];updater.archive_state()
    assert not updater.state.exists()
    assert (updater.config/'update-history'/token/'state.json').exists()
    assert updater.old.exists()


@pytest.mark.parametrize('transient',[False,True])
def test_http_transient_silent(updater,monkeypatch,capsys,transient):
    counts={}
    def run(args,**kw):
        if args[0]=='ss':return 'LISTEN 0 128 127.0.0.1:8000 0.0.0.0:*'
        if args[0]=='curl':
            url=args[-1];counts[url]=counts.get(url,0)+1
            if transient and counts[url]==1:raise subprocess.CalledProcessError(22,args,stderr='curl 502 synthetic-secret')
            if url.endswith('/health'):return '{"status":"ok"}'
            if url.endswith('/api/customers'):return '[]'
            if url.endswith('/'):return (updater.old/'frontend/dist/index.html').read_text()
            return (updater.old/'frontend/dist/assets/app.js').read_text()
        return ''
    updater.run=run;monkeypatch.setattr('time.sleep',lambda _:None)
    updater.healthy(updater.old)
    assert '502' not in ''.join(capsys.readouterr())


@pytest.mark.parametrize('path',['/health','/api/customers','/'])
def test_persistent_http_error(updater,monkeypatch,path):
    def run(args,**kw):
        if args[0]=='ss':return 'LISTEN 0 128 127.0.0.1:8000 0.0.0.0:*'
        if args[0]=='curl':
            if args[-1].endswith(path):raise subprocess.CalledProcessError(22,args,stderr='secret')
            return '{"status":"ok"}' if args[-1].endswith('/health') else '[]'
        return ''
    updater.run=run;monkeypatch.setattr('time.sleep',lambda _:None)
    with pytest.raises(u.UpdateError,match='30 intentos'):updater.healthy(updater.old)


@pytest.mark.parametrize('address',['0.0.0.0:8000','[::]:8000'])
def test_socket_local_only(updater,address):
    updater.run=lambda args,**kw:'LISTEN 0 128 '+address+' 0.0.0.0:*' if args[0]=='ss' else ''
    with pytest.raises(u.UpdateError,match='LOCAL'):updater.check_socket()


def migrations(root,new=False):
    (root/'alembic/versions').mkdir(parents=True,exist_ok=True)
    (root/'alembic.ini').write_text('[alembic]\nscript_location = alembic\n')
    (root/'alembic/env.py').write_text('')
    (root/'alembic/versions/old.py').write_text("revision='old'\ndown_revision=None\n")
    if new:(root/'alembic/versions/new.py').write_text("revision='new'\ndown_revision='old'\n")


@pytest.mark.parametrize('changed',[False,True])
def test_migration_plan(updater,changed):
    migrations(updater.old);migrations(updater.target,changed)
    assert u.migration_plan(updater.old,updater.target,'old')==('new' if changed else 'old')


@pytest.mark.parametrize('bad',['modified','orphan','branch'])
def test_incompatible_alembic(updater,bad):
    migrations(updater.old);migrations(updater.target,True)
    if bad=='modified':(updater.target/'alembic/versions/old.py').write_text("revision='old'\ndown_revision=None\n#changed")
    elif bad=='orphan':(updater.target/'alembic/versions/new.py').write_text("revision='new'\ndown_revision=None\n")
    else:(updater.target/'alembic/versions/branch.py').write_text("revision='other'\ndown_revision='old'\n")
    with pytest.raises(u.UpdateError):u.migration_plan(updater.old,updater.target,'old')


@pytest.mark.parametrize('migration',[False,True])
def test_activation_order(updater,migration):
    source(updater.target);updater.data['target_head']='new' if migration else 'old'
    calls=[];updater.revalidate=lambda:None;updater.verify_target=lambda:None;updater.data['backup']=str(updater.env);updater.data['backup_sha256']=u.digest(updater.env);updater.db_revision=lambda:updater.data['target_head']
    updater.run=lambda args,**kw:calls.append([str(a) for a in args]) or ''
    def healthy(release):
        assert updater.current.resolve()==updater.target
        assert (updater.old/'pyproject.toml').exists()
        calls.append(['healthy'])
    updater.healthy=healthy;updater.activate()
    assert updater.current.resolve()==updater.target
    assert calls[:2]==[['systemctl','disable','ticketyn'],['systemctl','stop','ticketyn']]
    assert (any('migrate' in c for c in calls))==migration
    assert calls[-3:]==[['systemctl','start','ticketyn'],['healthy'],['systemctl','enable','ticketyn']]
    assert not updater.state.exists()


@pytest.mark.parametrize('where',['migrate','start','healthy'])
def test_activation_failure_preserves_artifacts(updater,where):
    source(updater.target);updater.data['target_head']='new';updater.revalidate=lambda:None;updater.verify_target=lambda:None;updater.data['backup']=str(updater.env);updater.data['backup_sha256']=u.digest(updater.env)
    updater.db_revision=lambda:'new'
    def run(args,**kw):
        if where=='migrate' and 'migrate' in args or where=='start' and args[:2]==['systemctl','start']:
            raise subprocess.CalledProcessError(1,args,stderr='synthetic-secret')
        return ''
    updater.run=run
    updater.healthy=lambda _:u.fail('health failed') if where=='healthy' else None
    with pytest.raises((u.UpdateError,subprocess.CalledProcessError)):updater.activate()
    updater.failure()
    assert updater.target.exists() and updater.old.exists() and updater.state.exists()
    assert updater.current.resolve()==(updater.old if where=='migrate' else updater.target)


def test_prerelease_identity_backups_unchanged_format(tmp_path):
    release=source(tmp_path/'0.1.1-test.1','0.1.1')
    data={'format':'ticketyn-release-v1','version':'0.1.1-test.1','tag':'v0.1.1-test.1','package_version':'0.1.1','commit':'a'*40,'pyproject_sha256':u.digest(release/'pyproject.toml')}
    u.write_json(release/'.ticketyn-release.json',data,exclusive=True)
    assert u.ri.identity(release)=='0.1.1-test.1'
    data['tag']='v0.1.1';(release/'.ticketyn-release.json').write_text(json.dumps(data))
    with pytest.raises(ValueError):u.ri.identity(release)


def test_exact_git_tag_fetch_no_branch_pull(updater,tmp_path):
    repo=source(tmp_path/'repo')
    def git(*args):return subprocess.check_output(['git',*map(str,args)],text=True).strip()
    git('init','--quiet',repo);git('-C',repo,'add','.')
    git('-C',repo,'-c','user.name=Test','-c','user.email=test@example.invalid','commit','--quiet','-m','fixture')
    git('-C',repo,'tag','v0.2.0')
    old_origin=u.ORIGIN
    try:
        u.ORIGIN=str(repo)
        updater.git=lambda *args:git('-c','core.hooksPath=/dev/null',*args)
        result=updater.fetch()
        assert (result/'frontend/dist/index.html').exists()
        assert not (result/'.git').exists()
        assert updater.data['commit']==git('-C',repo,'rev-parse','HEAD')
        updater.tag='v0.9.0'
        with pytest.raises(u.UpdateError,match='inexistente'):updater.fetch()
    finally:u.ORIGIN=old_origin


def test_tag_retargeted_rejected(updater):
    updater.data.update(commit='a'*40,tag_oid='a'*40)
    def git(*args):
        if args[0]=='ls-remote':return 'b'*40+'\trefs/tags/v0.2.0'
        if 'rev-parse' in args:return 'b'*40
        if 'cat-file' in args:return 'commit'
        return ''
    updater.git=git
    with pytest.raises(u.UpdateError,match='modificado'):updater.fetch()


@pytest.mark.parametrize('failure',['dependencies','import'])
def test_prepare_failure_current_intact(updater,tmp_path,failure):
    incoming=source(updater.work/'source');updater.data.update(commit='a'*40,tag_oid='a'*40,package_version='0.2.0')
    def run(args,**kw):
        strings=list(map(str,args))
        if (failure=='dependencies' and 'install' in strings) or (failure=='import' and 'verify-python' in strings):
            raise subprocess.CalledProcessError(1,args,stderr='synthetic-secret')
        return ''
    updater.run=run
    with pytest.raises(subprocess.CalledProcessError):updater.prepare(incoming)
    updater.failure()
    assert updater.current.resolve()==updater.old and updater.target.exists()
    assert updater.data['phase']=='preparing'


def test_backup_failure_no_activation(updater):
    def run(args,**kwargs):raise subprocess.CalledProcessError(1,args,stderr='synthetic-secret')
    updater.run=run
    with pytest.raises(subprocess.CalledProcessError):updater.backup()
    assert updater.current.resolve()==updater.old and updater.data['phase']=='preparing'


def test_revalidate_current_changed(updater):
    source(updater.target);updater.current.unlink();updater.current.symlink_to(updater.target)
    with pytest.raises(u.UpdateError):updater.revalidate()


def test_lock_concurrency(tmp_path):
    lock=tmp_path/'lock';a=u.Updater('v0.2.0',lock=lock);b=u.Updater('v0.2.0',lock=lock)
    a.lock()
    try:
        with pytest.raises(u.UpdateError,match='ejecución'):b.lock()
    finally:
        os.close(a.lock_fd)
        if b.lock_fd is not None:os.close(b.lock_fd)


def test_symlink_lock_rejected(tmp_path):
    foreign=tmp_path/'foreign';foreign.write_text('keep');(tmp_path/'lock').symlink_to(foreign)
    with pytest.raises(OSError):u.Updater('v0.2.0',lock=tmp_path/'lock').lock()
    assert foreign.read_text()=='keep'


def test_real_postgres_forward_migration(postgres_engine,tmp_path,monkeypatch):
    """Real CLI migration in the disposable test cluster, separate database."""
    from sqlalchemy import text,create_engine
    from alembic.config import Config
    from alembic import command
    name='ticketyn_update_test'
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as c:
        c.execute(text('CREATE DATABASE '+name))
    url=postgres_engine.url.set(database=name)
    release=tmp_path/'release';release.mkdir();migrations(release,True)
    (release/'alembic/env.py').write_text('''from alembic import context
from sqlalchemy import create_engine
import os
engine=create_engine(os.environ['DATABASE_URL'])
with engine.connect() as conn:
    context.configure(connection=conn)
    with context.begin_transaction():context.run_migrations()
engine.dispose()
''')
    (release/'alembic/versions/old.py').write_text("""from alembic import op
revision='old'
down_revision=None
def upgrade():op.execute('CREATE TABLE update_preserved (value text)')
def downgrade():pass
""")
    (release/'alembic/versions/new.py').write_text("""from alembic import op
revision='new'
down_revision='old'
def upgrade():op.execute('ALTER TABLE update_preserved ADD COLUMN added integer')
def downgrade():pass
""")
    monkeypatch.setenv('DATABASE_URL',url.render_as_string(hide_password=False))
    cfg=Config(str(release/'alembic.ini'));cfg.set_main_option('script_location',str(release/'alembic'))
    engine=create_engine(url)
    try:
        command.upgrade(cfg,'old')
        with engine.begin() as c:c.execute(text("INSERT INTO update_preserved (value) VALUES ('persistente')"))
        result=subprocess.run([ROOT/'.venv/bin/python','-m','alembic','-c',release/'alembic.ini','upgrade','head'],cwd=release,text=True,capture_output=True)
        assert result.returncode==0,result.stderr
        with engine.connect() as c:
            assert c.execute(text('SELECT version_num FROM alembic_version')).scalar()=='new'
            assert c.execute(text('SELECT value FROM update_preserved')).scalar()=='persistente'
            assert c.execute(text('SELECT added FROM update_preserved')).scalar() is None
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as c:c.execute(text('DROP DATABASE '+name))


def configured_preflight(updater):
    installed=updater.config/'install-state';installed.mkdir(mode=0o700)
    for name,value in [('format','1'),('status','complete')]:
        p=installed/name;p.write_text(value);p.chmod(0o600)
    updater.unit=updater.config/'unit';updater.unit.write_text((ROOT/'deploy/systemd/ticketyn.service').read_text());updater.unit.chmod(0o600)
    updater.site=updater.config/'site';updater.site.write_text('server {\n listen 8080;\n root /opt/ticketyn/current/frontend/dist;\n}\n');updater.site.chmod(0o600)
    updater.link=updater.config/'enabled';updater.link.symlink_to(updater.site)
    updater.db_revision=lambda:'old';updater.head=lambda _:'old';updater.healthy=lambda _:None
    def pg(sql,database='postgres'):
        if 'pg_get_userbyid' in sql:return 'ticketyn:UTF8'
        if 'system_identifier' in sql:return '456'
        return '123'
    updater.pg=pg
    updater.run=lambda args,**kw:'8080' if 'port' in args else ''


@pytest.mark.parametrize('problem',['restore','current','permissions','destination','unmanaged','space'])
def test_preflight_protections(updater,monkeypatch,problem):
    configured_preflight(updater)
    shutil.rmtree(updater.state);updater.data=None;updater.authorized=False
    if problem=='restore':(updater.config/'restore-state').mkdir()
    elif problem=='current':updater.current.unlink();updater.current.mkdir()
    elif problem=='permissions':updater.env.chmod(0o644)
    elif problem=='destination':updater.target.mkdir()
    elif problem=='unmanaged':(updater.config/'install-state/status').write_text('failed')
    else:monkeypatch.setattr(u.shutil,'disk_usage',lambda _:type('Space',(),{'free':0})())
    with pytest.raises(u.UpdateError):updater.preflight()
    assert not updater.authorized


def test_current_activation_race_rejected(updater,monkeypatch):
    source(updater.target);updater.data['target_head']='old';updater.revalidate=lambda:None;updater.verify_target=lambda:None;updater.data['backup']=str(updater.env);updater.data['backup_sha256']=u.digest(updater.env);updater.db_revision=lambda:'old'
    original_record=updater.record
    def record(phase,**fields):
        original_record(phase,**fields)
        if phase=='activating':updater.current.unlink();updater.current.mkdir()
    updater.record=record
    with pytest.raises(u.UpdateError,match='current cambió'):updater.activate()
    assert updater.current.is_dir() and not updater.current.is_symlink()
    assert updater.old.exists()


def test_backup_verified_and_retained(updater,monkeypatch):
    from test_restore import package, components
    i={'root':updater.backups,'env':updater.env,'release':updater.old}
    parts=components(i)
    parts['metadata.txt']=parts['metadata.txt'].replace(b'0004_nodes_responsibles',b'old')
    archive=package(i,parts)
    def run(args,**kwargs):
        if args[0]==updater.scripts/'backup.sh':return '✓ Backup completo y verificado: '+str(archive)
        return ''
    updater.run=run;updater.backup()
    assert archive.exists() and updater.data['backup']==str(archive)
    assert updater.data['backup_sha256']==u.digest(archive)
    assert updater.current.resolve()==updater.old


@pytest.mark.parametrize('signum',[2,15])
def test_signal_while_preparing_keeps_old_state(updater,tmp_path,signum):
    # An isolated helper subprocess raises the same signal exception as the entrypoint.
    code='''import importlib.util,signal,sys
spec=importlib.util.spec_from_file_location('u',sys.argv[1]);u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)
a=u.Updater('v0.2.0',sys.argv[2],sys.argv[3],sys.argv[4]);a.read_state();a.authorized=True
try:
 def handler(n,f):raise u.UpdateError('Interrumpido')
 signal.signal(int(sys.argv[5]),handler);signal.raise_signal(int(sys.argv[5]))
except u.UpdateError:a.failure();sys.exit(1)
'''
    result=subprocess.run([sys.executable,'-c',code,ROOT/'deploy/update_support.py',updater.base,updater.config,updater.backups,str(signum)],capture_output=True,text=True)
    assert result.returncode==1
    assert updater.current.resolve()==updater.old
    assert 'synthetic-secret' not in result.stdout+result.stderr
    assert json.loads((updater.state/'state.json').read_text())['result']=='interrupted_or_failed'


def test_atomic_current_exchange(updater):
    source(updater.target)
    u.switch_current(updater.current,updater.target,updater.old,u.stamp(updater.current),updater.base/'.switch')
    assert updater.current.resolve()==updater.target and updater.old.exists()


def test_atomic_current_race_preserves_foreign_file(updater,monkeypatch):
    source(updater.target);original=u.exchange;counter=0
    def race(left,right):
        nonlocal counter
        counter+=1
        if counter==1:
            right.unlink();right.write_text('foreign administrator file')
        original(left,right)
    monkeypatch.setattr(u,'exchange',race)
    with pytest.raises(u.UpdateError,match='concurrentemente'):
        u.switch_current(updater.current,updater.target,updater.old,u.stamp(updater.current),updater.base/'.switch')
    assert updater.current.read_text()=='foreign administrator file'
    assert updater.old.exists() and updater.target.exists()


def test_successful_prepare_has_independent_venv_and_dist(updater):
    incoming=source(updater.work/'source')
    updater.data.update(commit='a'*40,tag_oid='a'*40,package_version='0.2.0')
    calls=[]
    def run(args,**kwargs):
        calls.append(list(map(str,args)))
        return 'old' if 'plan' in args else ''
    updater.run=run;updater.prepare(incoming)
    assert updater.current.resolve()==updater.old
    assert updater.data['phase']=='backup'
    assert (updater.target/'frontend/dist/index.html').exists()
    assert u.ri.identity(updater.target)=='0.2.0'
    assert any(str(updater.target/'.venv') in c for c in calls)
    assert any('check' in c for c in calls)
    assert any('verify-python' in c for c in calls)
    assert not any('npm' in c or 'node' in c or 'apt' in c for c in calls)


def test_prepare_rejects_target_tampering(updater):
    incoming=source(updater.work/'source')
    source(updater.target);(updater.target/'src/ticketyn/main.py').write_text('changed')
    updater.data.update(commit='a'*40,package_version='0.2.0')
    with pytest.raises(u.UpdateError,match='cambió'):updater.prepare(incoming)
    assert updater.current.resolve()==updater.old


def test_inherited_lock_held_by_child(tmp_path):
    obj=u.Updater('v0.2.0',lock=tmp_path/'lock');obj.lock()
    # Child survives parent descriptor closure and retains the same flock.
    child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(0.5)'],pass_fds=(obj.lock_fd,))
    os.close(obj.lock_fd)
    other=u.Updater('v0.2.0',lock=tmp_path/'lock')
    try:
        with pytest.raises(u.UpdateError):other.lock()
        child.wait()
        if other.lock_fd is not None:os.close(other.lock_fd)
        other.lock()
    finally:
        child.wait()
        if other.lock_fd is not None:os.close(other.lock_fd)


def test_real_release_tree_does_not_match_its_own_key_detector(tmp_path):
    archive = tmp_path/'candidate.tar'
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().strip('\0').split('\0')
    with tarfile.open(archive, 'w') as output:
        for name in names:
            if u.selected(name):
                output.add(ROOT/name, arcname=name, recursive=False)
    candidate = tmp_path/'candidate'
    u.extract_release(archive, candidate)
    assert (candidate/'deploy/update_support.py').is_file()
    assert (candidate/'frontend/dist/index.html').is_file()


def test_key_detector_still_rejects_private_key_content(tmp_path):
    archive = tmp_path/'source.tar'
    payload = b'-----BEGIN PRIVATE KEY' + b'-----\nsynthetic\n'
    archive.write_bytes(tar([('src/unexpected.txt', payload, tarfile.REGTYPE)]).read())
    with pytest.raises(u.UpdateError, match='clave privada'):
        u.extract_release(archive, tmp_path/'out')
