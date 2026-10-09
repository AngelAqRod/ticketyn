"""Migration retries never use DEV, host services or a real installation."""
import copy
import hashlib
import json
from pathlib import Path
import signal
import subprocess

import pytest
from test_update import u, updater, configured_preflight, migrations
from test_update_recovery import Lab


@pytest.fixture
def failed_migration(updater, monkeypatch):
    configured_preflight(updater)
    migrations(updater.old)
    lab = Lab(updater); lab.bind(updater)
    updater.record('preparing', source_snapshot=u.release_snapshot(updater.old),
                   unit_hash=u.digest(updater.unit), site_hash=u.digest(updater.site))
    updater.prepare(lab.incoming(updater)); updater.backup()
    lab.fail = 'migrate'
    with pytest.raises(u.UpdateError): updater.activate()
    updater.failure(); lab.fail = None
    assert updater.data['phase'] == 'migrating' and lab.revision == 'old'
    assert updater.current.resolve() == updater.old
    monkeypatch.setattr('time.sleep', lambda _: None)
    return lab


def retry(lab):
    previous = lab.obj
    obj = u.MigrationRetryUpdater(base=previous.base, config=previous.config,
        backups=previous.backups, lock=previous.lock_path, nginx_root=previous.nginx_root)
    obj.unit = previous.unit
    lab.bind(obj)
    obj.work = previous.work
    obj.read_state(); obj.tag=obj.data['tag']; obj.version=u.tag_version(obj.tag)
    def proof(data):
        obj.bound_backup(data, Path(data['previous']), data['source_head'])
        return dict(method='pg-schema-ddl-v1', backup_schema_sha256='a'*64,
                    live_schema_sha256='a'*64, original_backup_sha256=data['backup_sha256'])
    obj.schema_proof = proof
    return obj


def test_success_preserves_parent_data_releases_backups(failed_migration, capsys):
    lab=failed_migration; original=copy.deepcopy(lab.obj.data)
    obj=retry(lab); obj.preflight(); obj.begin_retry()
    assert len(lab.backups)==2
    assert obj.data['kind']=='migration_retry' and obj.data['parent_operation_id']==original['operation']
    assert obj.current.resolve()==obj.old and lab.revision=='old'
    obj.activate_retry()
    assert lab.revision=='new' and lab.active and lab.enabled
    assert not obj.state.exists() and obj.current.resolve()==obj.target
    parent=json.loads((obj.config/'update-history'/original['operation']/'state.json').read_text())
    assert parent==original  # including original failed checkpoint, not rewritten
    child=json.loads((obj.config/'update-history'/obj.data['operation']/'state.json').read_text())
    assert child['phase']=='complete' and child['result']=='success'
    assert all(p.exists() for p in lab.backups) and obj.old.exists() and obj.target.exists()
    assert 'synthetic-secret' not in capsys.readouterr().out
    obj.verify_checkpoint(parent); obj.verify_checkpoint(child)
    with pytest.raises(u.UpdateError, match='No existe'):
        obj.execute()  # a second call cannot migrate again


@pytest.mark.parametrize('problem', ['active','enabled','listener','current','source','target','env','unit','site','oid','cluster','revision','backup','checkpoint','pending','phase','kind'])
def test_inconsistent_state_rejected_without_stopping(failed_migration, problem):
    lab=failed_migration; obj=retry(lab); d=obj.data
    if problem=='active': lab.active=True
    elif problem=='enabled': lab.enabled=True
    elif problem=='listener':
        original=obj.run; obj.run=lambda args,**kw: 'LISTEN 0 128 127.0.0.1:8000 0.0.0.0:*' if args[0]=='ss' else original(args,**kw)
    elif problem=='current': obj.current.unlink(); obj.current.symlink_to(d['target'])
    elif problem in ('source','target'): (Path(d['previous' if problem=='source' else 'target'])/'README.md').write_text('changed')
    elif problem in ('env','unit','site'): getattr(obj, problem).write_text('changed')
    elif problem in ('oid','cluster'):
        original=obj.pg; obj.pg=lambda sql,database='postgres': '999' if ('SELECT oid' if problem=='oid' else 'system_identifier') in sql else original(sql,database)
    elif problem=='revision': lab.revision='partial'
    elif problem=='backup': Path(d['backup']).write_bytes(b'corrupt')
    elif problem=='checkpoint': (obj.config/'update-evidence'/d['operation']/(d['checkpoint']['id']+'.json')).unlink()
    else:
        if problem=='pending': lab.obj.record('migrating',result='pending')
        elif problem=='phase': lab.obj.record('migrated',result='interrupted_or_failed')
        else: lab.obj.record('migrating',kind='recovery')
    before=len(lab.calls)
    with pytest.raises((u.UpdateError, u.rs.RestoreError, ValueError, OSError, KeyError)): obj.preflight()
    assert not any(c[:2] in (['systemctl','stop'],['systemctl','disable']) or 'migrate' in c or c[0].endswith('/backup.sh') for c in lab.calls[before:])


def test_backup_failure_preserves_live_original(failed_migration):
    lab=failed_migration; obj=retry(lab); obj.preflight()
    before=(obj.state/'state.json').read_bytes(); lab.fail='backup'
    with pytest.raises(u.UpdateError): obj.begin_retry()
    assert (obj.state/'state.json').read_bytes()==before
    assert obj.current.resolve()==obj.old and lab.revision=='old'


@pytest.mark.parametrize('after', [False,True])
@pytest.mark.parametrize('signum', [signal.SIGINT,signal.SIGTERM])
def test_transition_interrupted_is_recoverable(failed_migration,monkeypatch,after,signum):
    lab=failed_migration; obj=retry(lab); obj.preflight(); original=dict(obj.data)
    exchange=u.exchange
    def interrupted(a,b):
        if after: exchange(a,b)
        raise u.UpdateError('Interrumpido por señal '+str(signum))
    monkeypatch.setattr(u,'exchange',interrupted)
    with pytest.raises(u.UpdateError): obj.begin_retry()
    assert obj.state.exists() and lab.revision=='old' and obj.current.resolve()==obj.old
    assert json.loads((obj.config/'update-history'/original['operation']/'state.json').read_text())==original
    monkeypatch.setattr(u,'exchange',exchange)
    obj=retry(lab); obj.preflight(); obj.begin_retry(); obj.activate_retry()
    assert lab.revision=='new' and not obj.state.exists() and len(lab.backups)==2


@pytest.mark.parametrize('where', ['migrate','start','health','api'])
def test_new_sensitive_failure_keeps_stopped_state(failed_migration,where):
    lab=failed_migration; obj=retry(lab); obj.preflight(); obj.begin_retry(); lab.fail=where
    with pytest.raises(u.UpdateError): obj.activate_retry()
    obj.failure()
    assert not lab.active and not lab.enabled
    state=json.loads((obj.state/'state.json').read_text())
    assert state['result']=='interrupted_or_failed' and state['parent_operation_id']
    assert all(p.exists() for p in lab.backups) and obj.old.exists() and obj.target.exists()


def test_retry_failure_can_forward_recover_normally(failed_migration):
    lab=failed_migration; obj=retry(lab); obj.preflight(); obj.begin_retry(); lab.fail='health'
    with pytest.raises(u.UpdateError): obj.activate_retry()
    obj.failure(); lab.fail=None
    recovery=lab.recovery(); recovery.preflight(); recovery.begin()
    recovery.prepare(lab.incoming(recovery)); recovery.backup(); recovery.activate()
    assert lab.active and lab.enabled and not recovery.state.exists()
    assert len(lab.backups)==3


def test_existing_modes_still_reject_failed_migration(failed_migration):
    lab=failed_migration
    with pytest.raises(u.UpdateError): lab.obj.validate_resume()
    with pytest.raises(u.UpdateError): lab.recovery().preflight()


def test_normalization_does_not_hide_real_ddl():
    def dump(body, version='17.1', key='ABC'):
        return ('--\n-- PostgreSQL database dump\n--\n\n\\restrict '+key+'\n\n-- Dumped by pg_dump version '+version+'\n\nSET statement_timeout = 0;\n'+body+'\n--\n-- PostgreSQL database dump complete\n--\n\n\\unrestrict '+key+'\n').encode()
    assert u.normalized_schema(dump('SELECT 1;'))==u.normalized_schema(dump('SELECT 1;', '17.2', 'DEF'))
    assert u.normalized_schema(dump('-- user comment\nSELECT 1;'))!=u.normalized_schema(dump('SELECT 1;'))
    assert u.normalized_schema(dump('ALTER TABLE x ADD COLUMN y text;'))!=u.normalized_schema(dump(''))
    assert u.normalized_schema(dump('CREATE FUNCTION x() RETURNS text AS $$\n-- Dumped by pg_dump version X\n$$ LANGUAGE sql;')) != u.normalized_schema(dump('CREATE FUNCTION x() RETURNS text AS $$\n-- Dumped by pg_dump version Y\n$$ LANGUAGE sql;'))
    with pytest.raises(u.UpdateError): u.normalized_schema(b'unknown header')


def test_read_only_commands(failed_migration):
    obj=retry(failed_migration); calls=[]
    obj.run=lambda args,**kw: calls.append(args) or ''
    u.MigrationRetryUpdater.pg(obj,'SELECT 1','ticketyn')
    assert any('default_transaction_read_only=on' in a and 'search_path=pg_catalog' in a for a in calls[0])
    assert '--no-password' in calls[0] and not any('synthetic-secret' in a for a in calls[0])

@pytest.fixture
def schema_database(postgres_engine):
    from uuid import uuid4
    from sqlalchemy import create_engine, text
    name='retry_schema_'+uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        created_role = not admin.scalar(text("SELECT EXISTS (SELECT FROM pg_roles WHERE rolname='ticketyn')"))
        if created_role:
            admin.execute(text('CREATE ROLE ticketyn LOGIN'))
        admin.execute(text('CREATE DATABASE '+name+' OWNER ticketyn ENCODING \'UTF8\''))
    url=postgres_engine.url.set(database=name); engine=create_engine(url)
    with engine.begin() as db:
        db.execute(text('SET ROLE ticketyn'))
        db.execute(text("CREATE TABLE alembic_version(version_num varchar(32) PRIMARY KEY); INSERT INTO alembic_version VALUES ('old')"))
        db.execute(text("CREATE TABLE tickets(id serial PRIMARY KEY, content text NOT NULL); INSERT INTO tickets(content) VALUES ('Datos actuales')"))
    try: yield engine
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE '+name))
            if created_role:
                admin.execute(text('DROP ROLE ticketyn'))


def real_schema_object(lab, engine):
    """Inject only the local connection transport; execute actual pg_dump/pg_restore."""
    from sqlalchemy import text
    from test_restore import components,package
    obj=retry(lab); url=engine.url
    env={'PATH':'/usr/bin:/bin','PGOPTIONS':'-c default_transaction_read_only=on'}
    connection=['--host='+url.query['host'],'--port='+url.query['port'],'--username='+url.username,'--dbname='+url.database,'--no-password']
    archive=subprocess.check_output(['pg_dump',*connection,'--format=custom'],env=env)
    parts=components({'env':obj.env,'release':Path(obj.data['previous'])})
    parts['database.dump']=archive
    for key in ('ticketyn_version','release_name'):
        parts['metadata.txt']=parts['metadata.txt'].replace((key+'=0.1.0\n').encode(),(key+'='+obj.data['source_version']+'\n').encode())
    with engine.connect() as db:
        revision=str(db.scalar(text('SELECT version_num FROM alembic_version')))
    obj.data['source_head']=revision
    parts['metadata.txt']=parts['metadata.txt'].replace(b'0004_nodes_responsibles',revision.encode())
    path=package({'root':obj.backups},parts)
    obj.data['backup']=str(path); obj.data['backup_sha256']=u.digest(path)
    labrun=obj.run
    def run(args,**kwargs):
        args=[str(a) for a in args]
        if args[:2]==['pg_dump','--version']:
            return subprocess.check_output(args,env=env,text=True).strip()
        if args[0]=='pg_restore':
            return subprocess.check_output(args,env=env)
        if args[0]=='runuser' and 'pg_dump' in args:
            assert 'PGOPTIONS=-c default_transaction_read_only=on' in args
            return subprocess.check_output(['pg_dump',*connection,'--format=custom','--schema-only'],env=env)
        return labrun(args,**kwargs)
    obj.run=run
    def pg(sql,database='postgres'):
        with engine.connect() as db:
            db.execute(text('SET TRANSACTION READ ONLY'))
            db.execute(text('SET LOCAL search_path=pg_catalog'))
            return str(db.scalar(text(sql)))
    obj.pg=pg
    obj.schema_proof=u.MigrationRetryUpdater.schema_proof.__get__(obj)
    return obj


def test_real_postgres_equivalent_schema_and_changed_data(failed_migration,schema_database):
    from sqlalchemy import text
    obj=real_schema_object(failed_migration,schema_database)
    with schema_database.begin() as db:
        db.execute(text("INSERT INTO tickets(content) VALUES ('Datos posteriores al backup')"))
    proof=obj.schema_proof(obj.data)
    assert proof['live_schema_sha256']==proof['backup_schema_sha256']
    with schema_database.connect() as db:
        assert db.scalar(text('SELECT count(*) FROM tickets'))==2
        assert db.scalar(text('SELECT version_num FROM alembic_version'))=='old'


@pytest.mark.parametrize('ddl', [
    'ALTER TABLE tickets ADD COLUMN partial_probe text',
    'CREATE INDEX partial_index ON tickets(content)',
    'ALTER TABLE tickets ALTER COLUMN content DROP NOT NULL',
    'CREATE VIEW partial_view AS SELECT * FROM tickets',
    'ALTER SEQUENCE tickets_id_seq INCREMENT BY 2',
])
def test_real_postgres_partial_ddl_same_revision_is_rejected(failed_migration,schema_database,ddl):
    from sqlalchemy import text
    obj=real_schema_object(failed_migration,schema_database)
    with schema_database.begin() as db: db.execute(text(ddl))
    with pytest.raises(u.UpdateError,match='esquema actual difiere'): obj.schema_proof(obj.data)
    with schema_database.connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version'))=='old'
        assert db.scalar(text('SELECT count(*) FROM tickets'))==1


def test_real_postgres_rolled_back_ddl_is_equivalent(failed_migration,schema_database):
    from sqlalchemy import text
    obj=real_schema_object(failed_migration,schema_database)
    with schema_database.connect() as db:
        db.execute(text('ALTER TABLE tickets ADD COLUMN rolled_back text')); db.rollback()
    obj.schema_proof(obj.data)


def test_real_postgres_read_only_blocks_writes(schema_database):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    with schema_database.connect() as db:
        db.execute(text('SET TRANSACTION READ ONLY'))
        with pytest.raises(DBAPIError): db.execute(text("INSERT INTO tickets(content) VALUES ('No permitido')"))
        db.rollback()
    with schema_database.connect() as db: assert db.scalar(text('SELECT count(*) FROM tickets'))==1

@pytest.mark.parametrize('problem',['extension','relation','tool_major','ddl'])
def test_schema_verifier_fails_closed(failed_migration,problem):
    obj=retry(failed_migration)
    obj.schema_proof=u.MigrationRetryUpdater.schema_proof.__get__(obj)
    pg=obj.pg; run=obj.run
    def query(sql,database='postgres'):
        if 'pg_extension' in sql: return 'plpgsql:1.0\nunknown:1.0' if problem=='extension' else 'plpgsql:1.0'
        if 'pg_attribute' in sql: return 'v:ticketyn:1043:false' if problem=='relation' else 'r:ticketyn:1043:false'
        return pg(sql,database)
    def command(args,**kwargs):
        if args[:2]==['pg_dump','--version']: return 'pg_dump (PostgreSQL) 999.0'
        return run(args,**kwargs)
    obj.pg=query;obj.run=command
    with pytest.raises(u.UpdateError): obj.schema_proof(obj.data)


def test_read_only_revision_checks_catalog_before_select(failed_migration):
    obj=retry(failed_migration); queries=[]
    obj.pg=lambda sql,database='postgres': queries.append(sql) or 'v:ticketyn:1043:false'
    with pytest.raises(u.UpdateError): u.MigrationRetryUpdater.db_revision(obj)
    assert len(queries)==1 and 'pg_catalog.pg_class' in queries[0]


@pytest.mark.parametrize('problem',['intent','stage','history'])
def test_transition_tampering_rejected(failed_migration,monkeypatch,problem):
    lab=failed_migration;obj=retry(lab);obj.preflight(); exchange=u.exchange
    monkeypatch.setattr(u,'exchange',lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt): obj.begin_retry()
    monkeypatch.setattr(u,'exchange',exchange)
    intent=obj.config/'migration-retry-transitions'/(obj.data['operation']+'.json')
    content=json.loads(intent.read_text())
    if problem=='intent': intent.write_text('{}')
    elif problem=='stage':
        path=obj.config/('.migration-retry-'+content['child_operation'])/'state.json'
        path.write_text('{}')
    else: (obj.config/'update-history'/obj.data['operation']/'state.json').write_text('{}')
    before=(obj.state/'state.json').read_bytes()
    with pytest.raises((u.UpdateError,KeyError)): obj.begin_retry()
    assert (obj.state/'state.json').read_bytes()==before and lab.revision=='old'


@pytest.mark.parametrize('answer',['','REINTENTAR','"REINTENTAR MIGRACION"'])
def test_cancel_is_innocuous(failed_migration,monkeypatch,answer):
    lab=failed_migration;obj=retry(lab);original=(obj.state/'state.json').read_bytes()
    monkeypatch.setattr('builtins.input',lambda prompt:answer)
    before=len(lab.calls);obj.execute()
    assert (obj.state/'state.json').read_bytes()==original and len(lab.backups)==1
    assert not any('migrate' in c or c[0].endswith('/backup.sh') or c[:2] in (['systemctl','stop'],['systemctl','disable']) for c in lab.calls[before:])


def test_real_020_failed_030_transaction_then_retry_preserves_data(failed_migration,schema_database):
    from sqlalchemy import create_engine,text
    from test_e2e_update_migration import cli
    with schema_database.begin() as db: db.execute(text('DROP TABLE tickets,alembic_version'))
    url=schema_database.url.set(username='ticketyn');engine=create_engine(url)
    try:
        cli(url,'upgrade','0009_ticket_resolution')
        with engine.begin() as db:
            db.execute(text("INSERT INTO customers(customer_code,name) VALUES ('RETRY','Cliente ficticio')"))
            db.execute(text("INSERT INTO circuits(customer_id,circuit_code,description) VALUES (1,'RETRY-C','Conservado')"))
            for table in ('sectors','departments','incident_types','responsibles'):
                db.execute(text(f"INSERT INTO {table}(name) VALUES ('Ficticio')"))
            db.execute(text("INSERT INTO nodes(name) VALUES ('UFINET'),('Ufinet')"))
            db.execute(text("INSERT INTO tickets(ticket_number,reference,title,description,customer_id,circuit_id,sector_id,department_id,incident_type_id,start_at,status) VALUES (1,'RETRY-1','Previo','Preservado',1,1,1,1,1,'2020-01-01T12:00:00Z','OPEN')"))
            db.execute(text("INSERT INTO ticket_updates(ticket_id,content) VALUES (1,'Intervención conservada')"))
            before=db.scalar(text('SELECT to_jsonb(t) FROM tickets t'))
        obj=real_schema_object(failed_migration,engine)
        with pytest.raises(AssertionError,match='unicidad'): cli(url,'upgrade','head')
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version'))=='0009_ticket_resolution'
            assert db.scalar(text("SELECT to_regclass('public.ticket_escalations')")) is None
            assert db.scalar(text("SELECT to_regclass('public.positions')")) is None
        obj.schema_proof(obj.data)
        # Authorized fictional-data conflict correction, not a database restore.
        with engine.begin() as db: db.execute(text("UPDATE nodes SET name='Otro nodo ficticio' WHERE name='Ufinet'"))
        obj.schema_proof(obj.data)
        cli(url,'upgrade','head')
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version'))=='0012_catalog_name_uniqueness'
            assert db.scalar(text('SELECT to_jsonb(t) FROM tickets t'))==before
            assert db.scalar(text('SELECT content FROM ticket_updates'))=='Intervención conservada'
            assert db.scalar(text('SELECT count(*) FROM nodes'))==2
    finally: engine.dispose()


def test_normal_update_cannot_consume_retry_authorization(failed_migration):
    obj=retry(failed_migration);obj.preflight();obj.begin_retry()
    with pytest.raises(u.UpdateError,match='requiere --retry-migration'): u.Updater.validate_resume(obj)


def test_crash_after_success_checkpoint_archives_without_migration(failed_migration,monkeypatch):
    lab=failed_migration;obj=retry(lab);obj.preflight();obj.begin_retry()
    archive=obj.archive_state
    monkeypatch.setattr(obj,'archive_state',lambda: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt): obj.activate_retry()
    assert obj.data['phase']=='complete' and lab.active and lab.enabled
    before=len(lab.calls)
    monkeypatch.setattr(obj,'archive_state',archive)
    obj.execute()
    assert not obj.state.exists() and lab.active and lab.enabled
    assert not any('migrate' in c or c[:2] in (['systemctl','stop'],['systemctl','disable']) for c in lab.calls[before:])


def test_retry_can_resume_verified_activation_without_remigration(failed_migration,monkeypatch):
    lab=failed_migration;obj=retry(lab);obj.preflight();obj.begin_retry();lab.fail='health'
    with pytest.raises(u.UpdateError): obj.activate_retry()
    obj.failure();lab.fail=None
    before=len(lab.calls)
    monkeypatch.setattr('builtins.input',lambda prompt:'REINTENTAR MIGRACION')
    obj.execute()
    assert lab.active and lab.enabled and not obj.state.exists()
    assert not any('migrate' in c for c in lab.calls[before:])


@pytest.mark.parametrize('problem',['env','oid','cluster','revision','site','source'])
def test_identity_changed_after_authorization_prevents_ddl(failed_migration,problem):
    lab=failed_migration;obj=retry(lab);obj.preflight();obj.begin_retry()
    if problem in ('env','site'): getattr(obj,problem).write_text('changed')
    elif problem=='source': (obj.old/'README.md').write_text('changed')
    elif problem=='revision': lab.revision='unexpected'
    else:
        old=obj.pg
        obj.pg=lambda sql,database='postgres': '999' if ('SELECT oid' if problem=='oid' else 'system_identifier') in sql else old(sql,database)
    before=len(lab.calls)
    with pytest.raises((u.UpdateError,u.rs.RestoreError)): obj.activate_retry()
    assert not obj.authorized
    assert not any('migrate' in c or c[:2] in (['systemctl','stop'],['systemctl','disable']) for c in lab.calls[before:])
