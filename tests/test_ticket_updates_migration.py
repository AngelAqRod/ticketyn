"""Real Alembic upgrade on existing tickets in the disposable test cluster."""
from uuid import uuid4

from sqlalchemy import create_engine, inspect, text

from test_e2e_update_migration import cli


def test_upgrade_existing_tickets_and_roundtrip(postgres_engine):
    database = 'follow_up_'+uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE '+database))
    url = postgres_engine.url.set(database=database)
    engine = create_engine(url)
    try:
        cli(url, 'upgrade', '0007_e2e_recovery_probe')
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO customers(customer_code,name) VALUES ('FOLLOW','Ficticio')"))
            connection.execute(text("INSERT INTO circuits(customer_id,circuit_code,description) VALUES (1,'FOLLOW-C','Enlace')"))
            for table in ('sectors', 'departments', 'incident_types'):
                connection.execute(text(f"INSERT INTO {table}(name) VALUES ('Ficticio')"))
            connection.execute(text("INSERT INTO tickets(ticket_number,reference,title,description,customer_id,circuit_id,sector_id,department_id,incident_type_id,start_at,end_at,status) VALUES (27,'TEST-27','Histórico','Datos previos',1,1,1,1,1,'2020-01-01T12:00:00Z','2020-01-01T13:00:00Z','CLOSED')"))
            before = connection.scalar(text('SELECT to_jsonb(t) FROM tickets t'))
        before_constraints = inspect(engine).get_foreign_keys('tickets')
        before_indexes = inspect(engine).get_indexes('tickets')
        cli(url, 'upgrade', '0008_ticket_updates')
        inspector = inspect(engine)
        assert 'ticket_updates' in inspector.get_table_names()
        assert inspector.get_foreign_keys('tickets') == before_constraints
        assert inspector.get_indexes('tickets') == before_indexes
        assert [index['column_names'] for index in inspector.get_indexes('ticket_updates')] == [['responsible_id'], ['ticket_id', 'occurred_at', 'id']]
        columns = {column['name']: column for column in inspector.get_columns('ticket_updates')}
        assert columns['responsible_id']['nullable']
        assert columns['occurred_at']['type'].timezone and columns['created_at']['type'].timezone
        with engine.begin() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == '0008_ticket_updates'
            assert connection.scalar(text('SELECT to_jsonb(t) FROM tickets t')) == before
            assert connection.scalar(text('SELECT count(*) FROM ticket_updates')) == 0
            # DB defaults also work for writers that omit intervention time.
            row = connection.execute(text("INSERT INTO ticket_updates(ticket_id,content) VALUES (1,'Seguimiento') RETURNING visibility,occurred_at,created_at")).one()
            assert row.visibility == 'INTERNAL' and row.occurred_at.tzinfo and row.created_at.tzinfo
        cli(url, 'downgrade', '0007_e2e_recovery_probe')
        assert 'ticket_updates' not in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT to_jsonb(t) FROM tickets t')) == before
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE '+database))
