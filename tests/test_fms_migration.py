from uuid import uuid4
from sqlalchemy import create_engine, text, inspect
from test_e2e_update_migration import cli


def test_0013_to_0014_preserves_circuits_and_tickets(postgres_engine):
    database = 'fms_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE ' + database))
    url = postgres_engine.url.set(database=database); engine = create_engine(url)
    try:
        cli(url, 'upgrade', '0013_escalation_operations')
        with engine.begin() as db:
            db.execute(text("INSERT INTO customers(customer_code,name) VALUES ('FMS','Cliente histórico')"))
            db.execute(text("INSERT INTO circuits(customer_id,circuit_code,description,active) VALUES (1,'FMS-1','Histórico',false)"))
            for table in ('sectors','departments','incident_types'):
                db.execute(text(f"INSERT INTO {table}(name) VALUES ('Ejemplo')"))
            db.execute(text("INSERT INTO tickets(ticket_number,reference,title,description,customer_id,circuit_id,sector_id,department_id,incident_type_id,start_at,status) VALUES (1,'OLD-1','Histórico','Datos',1,1,1,1,1,'2020-01-01T12:00:00Z','OPEN')"))
            tickets = db.scalar(text('SELECT to_jsonb(t) FROM tickets t'))
            circuit = db.scalar(text('SELECT to_jsonb(c) FROM circuits c'))
            seqs = dict(db.execute(text("SELECT sequencename,last_value FROM pg_sequences WHERE schemaname='public'")).all())
        cli(url, 'upgrade', '0014_circuit_operations')
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0014_circuit_operations'
            assert db.scalar(text('SELECT to_jsonb(t) FROM tickets t')) == tickets
            after = db.scalar(text('SELECT to_jsonb(c) FROM circuits c'))
            assert after.pop('initial_capacity') is None and after.pop('initial_capacity_unit') is None
            assert after == circuit
            current = dict(db.execute(text("SELECT sequencename,last_value FROM pg_sequences WHERE schemaname='public'")).all())
            assert all(current[name] == value for name,value in seqs.items())
            assert db.scalar(text('SELECT count(*) FROM deactivation_reasons')) == 5
            assert db.scalar(text('SELECT count(*) FROM activations')) == 0
            assert db.scalar(text('SELECT next_number FROM activation_number_config')) == 1
            for table in ('activations','capacity_changes','circuit_lifecycle_operations'):
                assert all(fk['options'].get('ondelete') != 'CASCADE' for fk in inspect(engine).get_foreign_keys(table))
        cli(url, 'downgrade', '0013_escalation_operations')
        with engine.connect() as db:
            assert db.scalar(text('SELECT to_jsonb(c) FROM circuits c')) == circuit
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE ' + database))


def test_migration_refuses_downgrade_with_fms_data(postgres_engine):
    database = 'fms_downgrade_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE ' + database))
    url = postgres_engine.url.set(database=database); engine = create_engine(url)
    try:
        cli(url, 'upgrade', '0014_circuit_operations')
        with engine.begin() as db:
            db.execute(text("INSERT INTO customers(customer_code,name) VALUES ('KEEP','Conservar')"))
            db.execute(text("INSERT INTO circuits(customer_id,circuit_code,description,initial_capacity,initial_capacity_unit) VALUES (1,'KEEP','Conservar',500,'Mbps')"))
        import os, subprocess, sys
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, '-B', '-m', 'alembic', '-c', str(root / 'alembic.ini'), 'downgrade', '0013_escalation_operations'], cwd=root, env={**os.environ, 'DATABASE_URL': url.render_as_string(hide_password=False)}, capture_output=True, text=True)
        assert result.returncode != 0 and 'Downgrade inseguro' in result.stderr
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0014_circuit_operations'
            assert db.scalar(text('SELECT initial_capacity FROM circuits')) == 500
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE ' + database))
