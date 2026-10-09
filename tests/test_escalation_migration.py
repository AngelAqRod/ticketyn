from uuid import uuid4
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
import pytest
from test_e2e_update_migration import cli


def test_upgrade_0009_preserves_ticket_update_and_responsible(postgres_engine):
    database = 'escalations_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE ' + database))
    url = postgres_engine.url.set(database=database)
    engine = create_engine(url)
    try:
        cli(url, 'upgrade', '0009_ticket_resolution')
        with engine.begin() as db:
            db.execute(text("INSERT INTO customers(customer_code,name) VALUES ('ESC','Ficticio')"))
            db.execute(text("INSERT INTO circuits(customer_id,circuit_code,description) VALUES (1,'ESC-C','Enlace')"))
            for table in ('sectors', 'departments', 'incident_types', 'responsibles'):
                db.execute(text(f"INSERT INTO {table}(name) VALUES ('Ficticio')"))
            for number in (1, 2):
                db.execute(text("INSERT INTO tickets(ticket_number,reference,title,description,customer_id,circuit_id,sector_id,department_id,incident_type_id,responsible_id,start_at,status,resolution) VALUES (:number,:reference,'Histórico','Datos previos',1,1,1,1,1,1,'2020-01-01T12:00:00Z','OPEN','Resolución previa')"), {'number': number, 'reference': f'ESC-{number}'})
            db.execute(text("INSERT INTO ticket_updates(ticket_id,content) VALUES (1,'Intervención previa')"))
            before_tickets = db.execute(text('SELECT to_jsonb(t) FROM tickets t ORDER BY id')).scalars().all()
            before_update = db.scalar(text('SELECT to_jsonb(t) FROM ticket_updates t'))
            before_person = db.scalar(text('SELECT to_jsonb(t) FROM responsibles t'))
        old_fks = inspect(engine).get_foreign_keys('tickets')
        cli(url, 'upgrade', '0010_ticket_escalations')
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0010_ticket_escalations'
            assert db.execute(text('SELECT to_jsonb(t) FROM tickets t ORDER BY id')).scalars().all() == before_tickets
            update = db.scalar(text('SELECT to_jsonb(t) FROM ticket_updates t'))
            assert update.pop('escalation_id') is None and update == before_update
            person = db.scalar(text('SELECT to_jsonb(t) FROM responsibles t'))
            assert person.pop('attention_level') is None and person == before_person
            assert db.scalar(text('SELECT count(*) FROM ticket_escalations')) == 0
            assert db.scalar(text('SELECT count(*) FROM escalation_reasons')) == 0
            assert inspect(db).get_foreign_keys('tickets') == old_fks
        with engine.begin() as db:
            db.execute(text("INSERT INTO escalation_reasons(name) VALUES ('Colaboración')"))
            db.execute(text("INSERT INTO ticket_escalations(ticket_id,requester_id,recipient_id,reason_id,description) VALUES (1,1,1,1,'Apoyo')"))
        with pytest.raises(IntegrityError):
            with engine.begin() as db:
                db.execute(text("INSERT INTO ticket_updates(ticket_id,escalation_id,content) VALUES (2,1,'Otro ticket')"))
        with pytest.raises(IntegrityError):
            with engine.begin() as db:
                db.execute(text('DELETE FROM tickets WHERE id=1'))
        # Isolated downgrade quality check: only new structures/columns disappear.
        cli(url, 'downgrade', '0009_ticket_resolution')
        with engine.connect() as db:
            assert db.execute(text('SELECT to_jsonb(t) FROM tickets t ORDER BY id')).scalars().all() == before_tickets
            assert db.scalar(text('SELECT to_jsonb(t) FROM ticket_updates t')) == before_update
            assert db.scalar(text('SELECT to_jsonb(t) FROM responsibles t')) == before_person
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE ' + database))
