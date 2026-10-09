"""Stable 0.2.0 -> 0.3.0 preservation in the disposable PostgreSQL cluster."""
from uuid import uuid4
from sqlalchemy import create_engine, text
from test_e2e_update_migration import cli, snapshot


def test_020_to_030_preserves_existing_domain(postgres_engine):
    name = 'release030_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE ' + name))
    url = postgres_engine.url.set(database=name)
    engine = create_engine(url)
    try:
        cli(url, 'upgrade', '0009_ticket_resolution')
        with engine.begin() as db:
            db.execute(text("INSERT INTO customers(customer_code,name) VALUES ('R030','Cliente ficticio')"))
            db.execute(text("INSERT INTO circuits(customer_id,circuit_code,description) VALUES (1,'R030-C','Circuito ficticio')"))
            for table in ('sectors', 'departments', 'incident_types', 'responsibles', 'nodes'):
                db.execute(text(f"INSERT INTO {table}(name) VALUES ('Ejemplo')"))
            db.execute(text("INSERT INTO tickets(ticket_number,reference,title,description,customer_id,circuit_id,sector_id,department_id,incident_type_id,responsible_id,start_at,end_at,status,resolution,customer_description) VALUES (1,'R030-1','Histórico','Descripción',1,1,1,1,1,1,'2020-01-01T12:00:00Z','2020-01-01T13:00:00Z','CLOSED','Resolución','Texto público')"))
            db.execute(text("INSERT INTO ticket_updates(ticket_id,content,visibility,occurred_at) VALUES (1,'Intervención histórica','PUBLIC','2019-12-31T12:00:00Z')"))
            before = snapshot(db, [])
        cli(url, 'upgrade', 'head')
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0012_catalog_name_uniqueness'
            after = snapshot(db, ['attention_level', 'department_id', 'position_id', 'escalation_id'])
            # Remove only additive fields in the corresponding historical tables.
            for table, rows in before[0].items():
                expected = rows
                if table == 'responsibles':
                    actual = after[0][table]
                elif table == 'ticket_updates':
                    actual = db.execute(text('SELECT to_jsonb(t) - \'escalation_id\' FROM ticket_updates t ORDER BY id')).scalars().all()
                else:
                    actual = db.execute(text(f'SELECT to_jsonb(t) FROM "{table}" t ORDER BY id')).scalars().all()
                assert actual == expected
            for old, new in zip(before[1:], after[1:]):
                assert set(old) <= set(new)
            assert db.scalar(text('SELECT count(*) FROM ticket_escalations')) == 0
            assert db.scalar(text('SELECT count(*) FROM positions')) == 0
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE ' + name))
