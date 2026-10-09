from uuid import uuid4
from sqlalchemy import create_engine, inspect, text
from test_e2e_update_migration import cli


def test_incremental_positions_preserves_legacy_and_nullable_requester(postgres_engine):
    database = 'positions_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE ' + database))
    url = postgres_engine.url.set(database=database)
    engine = create_engine(url)
    try:
        cli(url, 'upgrade', '0010_ticket_escalations')
        with engine.begin() as db:
            db.execute(text("INSERT INTO customers(customer_code,name) VALUES ('OLD','Cliente histórico')"))
            db.execute(text("INSERT INTO circuits(customer_id,circuit_code,description) VALUES (1,'OLD-C','Enlace')"))
            for table in ('sectors', 'departments', 'incident_types'):
                db.execute(text(f"INSERT INTO {table}(name) VALUES ('Histórico')"))
            db.execute(text("INSERT INTO responsibles(name,attention_level) VALUES ('Histórico','N3 libre anterior')"))
            db.execute(text("INSERT INTO tickets(ticket_number,reference,title,description,customer_id,circuit_id,sector_id,department_id,incident_type_id,start_at,status) VALUES (1,'OLD-1','Histórico','Conservar',1,1,1,1,1,'2020-01-01T00:00:00Z','OPEN')"))
            db.execute(text("INSERT INTO escalation_reasons(name) VALUES ('Apoyo')"))
            db.execute(text("INSERT INTO ticket_escalations(ticket_id,requester_id,recipient_id,recipient_level,reason_id,description) VALUES (1,1,1,'N3 histórico',1,'Solicitud antigua')"))
            before = {table: db.scalar(text(f'SELECT to_jsonb(t) FROM {table} t')) for table in ('tickets', 'responsibles', 'ticket_escalations')}
        ticket_fks = inspect(engine).get_foreign_keys('tickets')
        cli(url, 'upgrade', '0011_department_positions')
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0011_department_positions'
            assert db.scalar(text('SELECT count(*) FROM positions')) == 0
            assert db.scalar(text('SELECT to_jsonb(t) FROM tickets t')) == before['tickets']
            person = db.scalar(text('SELECT to_jsonb(t) FROM responsibles t'))
            assert person.pop('department_id') is None
            assert person.pop('position_id') is None
            assert person == before['responsibles']
            escalation = db.scalar(text('SELECT to_jsonb(t) FROM ticket_escalations t'))
            assert escalation.pop('recipient_position_name') is None
            assert escalation.pop('recipient_department_name') is None
            assert escalation == before['ticket_escalations']
            assert inspect(db).get_foreign_keys('tickets') == ticket_fks
        cli(url, 'downgrade', '0010_ticket_escalations')
        with engine.connect() as db:
            for table, value in before.items():
                assert db.scalar(text(f'SELECT to_jsonb(t) FROM {table} t')) == value
        cli(url, 'upgrade', '0011_department_positions')
        with engine.begin() as db:
            db.execute(text("INSERT INTO ticket_escalations(ticket_id,recipient_id,reason_id,description) VALUES (1,1,1,'Sin solicitante')"))
        import pytest
        with pytest.raises(AssertionError, match='existen escalamientos sin solicitante'):
            cli(url, 'downgrade', '0010_ticket_escalations')
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0011_department_positions'
            assert db.scalar(text('SELECT count(*) FROM ticket_escalations WHERE requester_id IS NULL')) == 1
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE ' + database))
