from uuid import uuid4
from sqlalchemy import create_engine, text
from test_e2e_update_migration import cli


def test_0012_to_0013_preserves_historical_evidence(postgres_engine):
    database = 'operations_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE ' + database))
    url = postgres_engine.url.set(database=database)
    engine = create_engine(url)
    try:
        cli(url, 'upgrade', '0012_catalog_name_uniqueness')
        with engine.begin() as db:
            db.execute(text("INSERT INTO customers(customer_code,name) VALUES ('OP','Ejemplo')"))
            db.execute(text("INSERT INTO circuits(customer_id,circuit_code,description) VALUES (1,'OP-1','Ejemplo')"))
            for table in ('sectors', 'departments', 'incident_types', 'responsibles'):
                db.execute(text(f"INSERT INTO {table}(name) VALUES ('NOC')"))
            db.execute(text("INSERT INTO tickets(ticket_number,reference,title,description,customer_id,circuit_id,sector_id,department_id,incident_type_id,start_at,status) VALUES (1,'OP-1','Histórico','Datos',1,1,1,1,1,'2020-01-01T12:00:00Z','OPEN')"))
            db.execute(text("INSERT INTO escalation_reasons(name) VALUES ('Apoyo')"))
            for name in ('NOC', 'Departamento anterior', None):
                db.execute(text("INSERT INTO ticket_escalations(ticket_id,recipient_id,reason_id,description,recipient_department_name,created_at,finished_at,status) VALUES (1,1,1,'Histórico',:name,'2020-01-02T12:00:00Z','2020-01-02T13:00:00Z','FINISHED')"), {'name': name})
            ticket = db.scalar(text('SELECT to_jsonb(t) FROM tickets t'))
            before = db.execute(text('SELECT to_jsonb(e) FROM ticket_escalations e ORDER BY id')).scalars().all()
            sequences = db.execute(text('SELECT sequencename,last_value FROM pg_sequences WHERE schemaname=\'public\' ORDER BY sequencename')).all()
        cli(url, 'upgrade', '0013_escalation_operations')
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0013_escalation_operations'
            assert db.scalar(text('SELECT to_jsonb(t) FROM tickets t')) == ticket
            after = db.execute(text('SELECT to_jsonb(e) FROM ticket_escalations e ORDER BY id')).scalars().all()
            assert [row['department_id'] for row in after] == [1, None, None]
            for old, new in zip(before, after):
                assert new.pop('started_at') == old['created_at']
                assert new.pop('updated_at') == (old['finished_at'] or old['created_at'])
                new.pop('department_id'); new.pop('legacy_destination')
                assert new == old
            current = dict(db.execute(text('SELECT sequencename,last_value FROM pg_sequences WHERE schemaname=\'public\'')).all())
            assert all(current[name] == value for name, value in sequences)
            assert db.scalar(text('SELECT count(*) FROM escalation_audit')) == 0
        cli(url, 'downgrade', '0012_catalog_name_uniqueness')
        with engine.connect() as db:
            assert db.execute(text('SELECT to_jsonb(e) FROM ticket_escalations e ORDER BY id')).scalars().all() == before
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE ' + database))
