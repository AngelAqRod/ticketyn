"""Upgrade only a disposable database from the published v0.4.x chain."""
from uuid import uuid4
from sqlalchemy import create_engine, text, inspect
from test_e2e_update_migration import cli

def test_upgrade_preserves_client_tickets_and_adds_null_relation(postgres_engine):
    name='internal_migration_'+uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE '+name))
    engine=create_engine(postgres_engine.url.set(database=name))
    try:
        cli(engine.url,'upgrade','0020_activation_cpe')
        with engine.begin() as db:
            for table in ('nodes','sectors','departments','incident_types'):
                db.execute(text(f"INSERT INTO {table}(id,name) VALUES(1,'Histórico')"))
            db.execute(text("INSERT INTO customers(id,customer_code,name) VALUES(1,'CLIENT','Cliente histórico')"))
            db.execute(text("INSERT INTO circuits(id,customer_id,circuit_code,description,node_id,sector_id) VALUES(1,1,'C-1','Enlace',1,1)"))
            db.execute(text("INSERT INTO tickets(id,ticket_number,reference,title,description,customer_id,circuit_id,node_id,sector_id,department_id,incident_type_id,start_at,status) VALUES(1,1,'TEST-1','Histórico','Conservar',1,1,1,1,1,1,'2026-01-01T12:00:00Z','OPEN')"))
            before=db.execute(text('SELECT to_jsonb(t) FROM tickets t')).scalar_one()
        cli(engine.url,'upgrade','head')
        cli(engine.url,'upgrade','head')
        with engine.connect() as db:
            after=db.execute(text('SELECT to_jsonb(t) FROM tickets t')).scalar_one()
            assert after.pop('internal_ticket_id') is None
            assert after==before
            assert db.execute(text('SELECT count(*) FROM internal_tickets')).scalar_one()==0
            assert db.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0024_default_change_types_upper'
            assert 'providers' in inspect(db).get_table_names()
        import os, subprocess, sys
        refused = subprocess.run([sys.executable, '-m', 'alembic', 'downgrade', '0020_activation_cpe'], env={**os.environ, 'DATABASE_URL':engine.url.render_as_string(hide_password=False)}, text=True, capture_output=True)
        assert refused.returncode != 0 and 'conserva datos operativos' in refused.stderr
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0024_default_change_types_upper'
            assert db.scalar(text('SELECT count(*) FROM tickets')) == 1

    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE '+name))
