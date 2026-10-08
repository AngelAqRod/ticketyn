"""Production lineage 0.1.6 -> 0.2.0, only in the disposable PostgreSQL cluster."""
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from ticketyn.core.config import get_settings
from ticketyn.db.session import get_session
from test_e2e_update_migration import cli, snapshot


def test_016_to_020_preserves_domain_and_supports_followup(postgres_engine, monkeypatch):
    database = 'release020_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE ' + database))
    url = postgres_engine.url.set(database=database)
    engine = create_engine(url)
    try:
        cli(url, 'upgrade', '0007_e2e_recovery_probe')
        with engine.begin() as db:
            db.execute(text("INSERT INTO customers(customer_code,name) VALUES ('REL020','Cliente ficticio ñ')"))
            db.execute(text("INSERT INTO nodes(name) VALUES ('Nodo histórico')"))
            db.execute(text("INSERT INTO responsibles(name) VALUES ('Responsable histórico')"))
            db.execute(text("INSERT INTO circuits(customer_id,circuit_code,description,node_id) VALUES (1,'REL020-C','Circuito conservado',1)"))
            for table in ['sectors', 'departments', 'incident_types']:
                db.execute(text(f"INSERT INTO {table}(name) VALUES ('Histórico')"))
            for number, status, end in [(1, 'OPEN', None), (2, 'CLOSED', '2020-01-01T13:00:00Z')]:
                db.execute(text("INSERT INTO tickets(ticket_number,reference,title,description,customer_id,circuit_id,sector_id,department_id,incident_type_id,responsible_id,start_at,end_at,status) VALUES (:number,:reference,'Incidente histórico','Descripción conservada',1,1,1,1,1,1,'2020-01-01T12:00:00Z',:end,:status)"),
                    {'number': number, 'reference': f'REL020-{number}', 'end': end, 'status': status})
            db.execute(text("UPDATE tickets SET _ticketyn_e2e_update_probe='Probe conservada', _ticketyn_e2e_postmigration_probe='Dato previo', _ticketyn_e2e_recovery_probe='Dato original' WHERE id=1"))
            before = snapshot(db, [])
        cli(url, 'upgrade', 'head')
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0009_ticket_resolution'
            after = snapshot(db, ['resolution', 'customer_description', 'customer_resolution'])
            assert {table: rows for table, rows in after[0].items() if table != 'ticket_updates'} == before[0]
            assert after[0]['ticket_updates'] == []
            # New table/constraints are additive; every existing constraint, sequence and index survives.
            for old, new in zip(before[1:], after[1:]):
                assert set(old) <= set(new)
            assert db.execute(text('SELECT resolution,customer_description,customer_resolution FROM tickets')).all() == [(None, None, None)] * 2
            actions = db.execute(text("SELECT confdeltype::text FROM pg_constraint WHERE contype='f' AND confrelid IN ('customers'::regclass,'circuits'::regclass,'tickets'::regclass)")).scalars().all()
            assert actions and set(actions) <= {'a', 'r'}  # NO ACTION / RESTRICT; never CASCADE.
            assert inspect(db).get_foreign_keys('ticket_updates')
        monkeypatch.setenv('DATABASE_URL', url.render_as_string(hide_password=False))
        get_settings.cache_clear()
        from ticketyn.main import create_app
        app = create_app()
        def session():
            with Session(engine) as db:
                yield db
        app.dependency_overrides[get_session] = session
        with TestClient(app) as client:
            assert app.version == '0.2.0'
            assert client.get('/health').json() == {'status': 'ok'}
            for id in [1, 2]:
                before_ticket = client.get(f'/api/tickets/{id}').json()
                assert before_ticket['resolution'] is None
                assert before_ticket['description'] == 'Descripción conservada'
                update = client.post(f'/api/tickets/{id}/updates', json={'content': 'Intervención tras upgrade', 'occurred_at': '2019-12-31T12:00:00Z', 'responsible_id': 1})
                assert update.status_code == 201
                assert client.get(f'/api/tickets/{id}').json() == before_ticket
                assert client.get(f'/api/tickets/{id}/updates').json()[0]['content'] == 'Intervención tras upgrade'
                assert client.get(f'/api/tickets/{id}/reports/internal/pdf').status_code == 200
                assert client.get(f'/api/tickets/{id}/reports/customer/pdf').status_code == 200
            assert client.delete('/api/customers/1').status_code == 409
            assert client.delete('/api/circuits/1').status_code == 409
            assert len(client.get('/api/customers').json()) == 1
            assert len(client.get('/api/circuits').json()) == 1
    finally:
        get_settings.cache_clear()
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE ' + database))
