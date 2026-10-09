from uuid import uuid4

from sqlalchemy import create_engine, inspect, text

from test_e2e_update_migration import cli


def test_upgrade_0008_preserves_existing_tickets_and_followup(postgres_engine):
    database = 'resolution_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE ' + database))
    url = postgres_engine.url.set(database=database)
    engine = create_engine(url)
    fields = ['resolution', 'customer_description', 'customer_resolution']
    try:
        cli(url, 'upgrade', '0008_ticket_updates')
        with engine.begin() as db:
            db.execute(text("INSERT INTO customers(customer_code,name) VALUES ('RES','Ficticio')"))
            db.execute(text("INSERT INTO circuits(customer_id,circuit_code,description) VALUES (1,'RES-C','Enlace')"))
            for table in ('sectors', 'departments', 'incident_types'):
                db.execute(text(f"INSERT INTO {table}(name) VALUES ('Ficticio')"))
            db.execute(text("INSERT INTO tickets(ticket_number,reference,title,description,customer_id,circuit_id,sector_id,department_id,incident_type_id,start_at,end_at,status) VALUES (1,'RES-1','Histórico','Datos previos',1,1,1,1,1,'2020-01-01T12:00:00Z','2020-01-01T13:00:00Z','CLOSED')"))
            db.execute(text("INSERT INTO ticket_updates(ticket_id,content) VALUES (1,'Intervención previa')"))
            before_ticket = db.scalar(text('SELECT to_jsonb(t) FROM tickets t'))
            before_update = db.scalar(text('SELECT to_jsonb(t) FROM ticket_updates t'))
            sequences = db.execute(text('SELECT sequencename,last_value FROM pg_sequences ORDER BY sequencename')).all()
        before_fks = inspect(engine).get_foreign_keys('tickets')
        before_indexes = inspect(engine).get_indexes('tickets')
        cli(url, 'upgrade', '0009_ticket_resolution')
        columns = {column['name']: column for column in inspect(engine).get_columns('tickets')}
        assert all(columns[field]['nullable'] and columns[field]['default'] is None for field in fields)
        assert inspect(engine).get_foreign_keys('tickets') == before_fks
        assert inspect(engine).get_indexes('tickets') == before_indexes
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0009_ticket_resolution'
            row = db.scalar(text('SELECT to_jsonb(t) FROM tickets t'))
            assert {key: value for key, value in row.items() if key not in fields} == before_ticket
            assert all(row[field] is None for field in fields)
            assert db.scalar(text('SELECT to_jsonb(t) FROM ticket_updates t')) == before_update
            assert db.execute(text('SELECT sequencename,last_value FROM pg_sequences ORDER BY sequencename')).all() == sequences
        cli(url, 'downgrade', '0008_ticket_updates')
        with engine.connect() as db:
            assert db.scalar(text('SELECT to_jsonb(t) FROM tickets t')) == before_ticket
            assert db.scalar(text('SELECT to_jsonb(t) FROM ticket_updates t')) == before_update
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE ' + database))
