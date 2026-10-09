from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from test_e2e_update_migration import cli


CATALOGS = ('customers', 'sectors', 'departments', 'positions', 'incident-types', 'escalation-reasons', 'responsibles', 'nodes')


@pytest.mark.parametrize('catalog', CATALOGS)
def test_names_case_trim_create_update(api_client, catalog):
    extra = {}
    if catalog == 'positions':
        extra['department_id'] = api_client.post('/api/departments', json={'name': 'NOC'}).json()['id']
    if catalog == 'customers':
        extra['customer_code'] = 'ONE'
    path = '/api/' + catalog
    original = api_client.post(path, json={'name': '  UFINET  ', **extra})
    assert original.status_code == 201, original.text
    item = original.json()
    assert item['name'] == 'UFINET'
    for value in ('ufinet', 'Ufinet', ' UFINET ', ' ufinet  '):
        duplicate = api_client.post(path, json={'name': value, **extra, **({'customer_code': 'TWO'} if catalog == 'customers' else {})})
        assert duplicate.status_code == 409
        assert 'nombre' in duplicate.json()['detail']
        assert 'IntegrityError' not in duplicate.text and 'uq_' not in duplicate.text
    second = api_client.post(path, json={'name': 'TELXIUS', **extra, **({'customer_code': 'TWO'} if catalog == 'customers' else {})}).json()
    assert api_client.patch(f"{path}/{second['id']}", json={'name': ' uFinet '}).status_code == 409
    assert api_client.get(f"{path}/{second['id']}").json()['name'] == 'TELXIUS'
    assert api_client.patch(f"{path}/{item['id']}", json={'name': ' Ufinet '}).json()['name'] == 'Ufinet'
    assert api_client.patch(f"{path}/{item['id']}", json={'name': 'Ufinet'}).status_code == 200


def test_position_name_scope(api_client):
    first = api_client.post('/api/departments', json={'name': 'NOC'}).json()['id']
    second = api_client.post('/api/departments', json={'name': 'Red Externa'}).json()['id']
    a = api_client.post('/api/positions', json={'name': 'Supervisor', 'department_id': first}).json()
    b = api_client.post('/api/positions', json={'name': 'supervisor', 'department_id': second}).json()
    assert a['id'] != b['id']
    assert api_client.post('/api/positions', json={'name': ' supervisor ', 'department_id': first}).status_code == 409
    assert api_client.patch(f"/api/positions/{b['id']}", json={'department_id': first}).status_code == 409


def test_migration_conflicts_no_changes_and_concurrency(postgres_engine):
    database = 'unique_names_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE ' + database))
    url = postgres_engine.url.set(database=database)
    engine = create_engine(url)
    try:
        cli(url, 'upgrade', '0011_department_positions')
        with engine.begin() as db:
            db.execute(text("INSERT INTO customers(customer_code,name) VALUES ('A','UFINET'), ('B',' ufinet '), ('C','Ufinet')"))
            db.execute(text("INSERT INTO departments(name) VALUES ('NOC'), ('Red Externa')"))
            db.execute(text("INSERT INTO positions(department_id,name) VALUES (1,'Supervisor'),(1,' supervisor '),(2,'Supervisor')"))
            before = {table: db.execute(text(f'SELECT to_jsonb(t) FROM {table} t ORDER BY id')).scalars().all() for table in ('customers','positions')}
        with pytest.raises(AssertionError, match='ids=') as error:
            cli(url, 'upgrade', 'head')
        assert 'customers' in str(error.value) and 'positions' in str(error.value)
        with engine.begin() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0011_department_positions'
            for table, rows in before.items():
                assert db.execute(text(f'SELECT to_jsonb(t) FROM {table} t ORDER BY id')).scalars().all() == rows
            assert db.scalar(text("SELECT count(*) FROM pg_indexes WHERE indexname LIKE '%name_normalized'")) == 0
            # Explicit correction exclusively in this disposable fixture, no merge/delete.
            db.execute(text("UPDATE customers SET name=name || id::text WHERE id>1"))
            db.execute(text("UPDATE positions SET name='Supervisor suplente' WHERE id=2"))
        cli(url, 'upgrade', 'head')
        with engine.connect() as db:
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0012_catalog_name_uniqueness'
            assert db.scalar(text('SELECT count(*) FROM customers')) == 3
            assert db.scalar(text('SELECT count(*) FROM positions')) == 3
        # True simultaneous writes bypass application validation: PostgreSQL arbitrates.
        barrier = Barrier(2)
        def insert(name):
            try:
                with engine.begin() as db:
                    barrier.wait(timeout=10)
                    db.execute(text('INSERT INTO nodes(name) VALUES (:name)'), {'name': name})
                return 'created'
            except IntegrityError:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(insert, ['NODO Concurrente', ' nodo concurrente ']))
        assert sorted(results) == ['conflict', 'created']
        cli(url, 'downgrade', '0011_department_positions')
        with engine.connect() as db:
            assert db.scalar(text('SELECT count(*) FROM customers')) == 3
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE ' + database))


def test_database_conflict_is_controlled_even_if_application_check_races(api_client, monkeypatch):
    from ticketyn.api import crud
    # Emulate both application checks observing no competing row; the unique
    # PostgreSQL index must still arbitrate and save_item must rollback safely.
    monkeypatch.setattr(crud, 'validate_catalog_name', lambda session, item: None)
    assert api_client.post('/api/nodes', json={'name': 'UFINET'}).status_code == 201
    response = api_client.post('/api/nodes', json={'name': 'ufinet'})
    assert response.status_code == 409
    assert 'nombre' in response.json()['detail']
    assert 'uq_' not in response.text and 'INSERT' not in response.text
    assert api_client.post('/api/nodes', json={'name': 'Otro nodo'}).status_code == 201


def test_business_codes_keep_their_existing_case_sensitive_semantics(api_client):
    a = api_client.post('/api/customers', json={'name': 'Cliente Uno', 'customer_code': 'Code'})
    b = api_client.post('/api/customers', json={'name': 'Cliente Dos', 'customer_code': 'code'})
    assert a.status_code == b.status_code == 201
    for code in ('Circuit', 'circuit'):
        response = api_client.post('/api/circuits', json={'customer_id': a.json()['id'], 'circuit_code': code, 'description': 'Descripción compartida'})
        assert response.status_code == 201


def test_unicode_names_are_case_insensitive_even_in_legacy_c_locale(api_client, db_session):
    assert api_client.post('/api/responsibles', json={'name': 'ÁNGEL'}).status_code == 201
    assert api_client.post('/api/responsibles', json={'name': ' ángel '}).status_code == 409
    assert api_client.post('/api/responsibles', json={'name': 'Ángel'}).status_code == 409
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(text("INSERT INTO responsibles(name) VALUES ('ángel')"))
