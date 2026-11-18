import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

BASE = '/api/circuits'


@pytest.fixture
def body(ticket_payload):
    return dict(customer_id=ticket_payload['customer_id'], node_id=ticket_payload['node_id'], sector_id=ticket_payload['sector_id'], circuit_code='LOC-1', description='Con ubicación')


def test_circuit_without_new_fields_keeps_null_values(api_client, body):
    created = api_client.post(BASE, json=body)
    assert created.status_code == 201, created.text
    data = created.json()
    assert (data['address'], data['latitude'], data['longitude'], data['additional_notes']) == (None, None, None, None)
    assert api_client.get(f"{BASE}/{data['id']}").json() == data


def test_create_with_address_gps_and_notes_and_round_to_six_decimals(api_client, body):
    created = api_client.post(BASE, json={**body, 'address': '  3a calle 5-10 zona 1  ', 'latitude': '14.6349151', 'longitude': '-90.5068829', 'additional_notes': 'Llave en recepción\nSegundo piso'})
    assert created.status_code == 201, created.text
    data = created.json()
    assert data['address'] == '3a calle 5-10 zona 1' and (data['latitude'], data['longitude']) == ('14.634915', '-90.506883')
    assert data['additional_notes'] == 'Llave en recepción\nSegundo piso'


def test_edit_each_field_and_partial_updates_keep_the_rest(api_client, body):
    item = api_client.post(BASE, json={**body, 'address': 'Zona 1', 'latitude': 14.5, 'longitude': -90.5, 'additional_notes': 'Nota'}).json()
    url = f"{BASE}/{item['id']}"
    assert api_client.patch(url, json={'address': 'Zona 10'}).json()['address'] == 'Zona 10'
    assert api_client.patch(url, json={'additional_notes': 'Otra'}).json()['additional_notes'] == 'Otra'
    gps = api_client.patch(url, json={'latitude': '15.25', 'longitude': '-91.75'}).json()
    assert (gps['latitude'], gps['longitude']) == ('15.250000', '-91.750000')
    # Unrelated and unsent fields survive partial updates.
    after = api_client.patch(url, json={'description': 'Renombrado'}).json()
    assert (after['address'], after['latitude'], after['additional_notes']) == ('Zona 10', '15.250000', 'Otra')


def test_each_field_can_be_cleared_without_touching_the_others(api_client, body):
    item = api_client.post(BASE, json={**body, 'address': 'Zona 1', 'latitude': 14.5, 'longitude': -90.5, 'additional_notes': 'Nota'}).json()
    url = f"{BASE}/{item['id']}"
    cleared = api_client.patch(url, json={'latitude': None, 'longitude': None}).json()
    assert (cleared['latitude'], cleared['longitude'], cleared['address'], cleared['additional_notes']) == (None, None, 'Zona 1', 'Nota')
    assert api_client.patch(url, json={'address': None}).json()['address'] is None
    assert api_client.patch(url, json={'additional_notes': None}).json()['additional_notes'] is None
    assert api_client.patch(url, json={'address': '  '}).status_code == 422  # blanks are rejected, null clears


@pytest.mark.parametrize('values', [{'latitude': 90.1, 'longitude': 0}, {'latitude': -90.1, 'longitude': 0}, {'latitude': 0, 'longitude': 180.1}, {'latitude': 0, 'longitude': -180.1}, {'latitude': 'abc', 'longitude': 0}, {'latitude': 'NaN', 'longitude': 0}])
def test_out_of_range_or_invalid_coordinates_are_rejected(api_client, body, values):
    assert api_client.post(BASE, json={**body, **values}).status_code == 422
    item = api_client.post(BASE, json=body).json()
    assert api_client.patch(f"{BASE}/{item['id']}", json=values).status_code == 422


def test_boundaries_are_accepted(api_client, body):
    assert api_client.post(BASE, json={**body, 'latitude': 90, 'longitude': 180}).status_code == 201
    assert api_client.post(BASE, json={**body, 'circuit_code': 'LOC-2', 'latitude': -90, 'longitude': -180}).status_code == 201


def test_incomplete_pair_is_rejected_on_create_and_update(api_client, body):
    assert api_client.post(BASE, json={**body, 'latitude': 14.5}).status_code == 422
    assert api_client.post(BASE, json={**body, 'longitude': -90.5}).status_code == 422
    assert api_client.post(BASE, json={**body, 'latitude': 14.5, 'longitude': None}).status_code == 422
    item = api_client.post(BASE, json={**body, 'latitude': 14.5, 'longitude': -90.5}).json()
    url = f"{BASE}/{item['id']}"
    assert api_client.patch(url, json={'latitude': None}).status_code == 422  # would leave longitude alone
    assert api_client.patch(url, json={'longitude': None}).status_code == 422
    assert api_client.patch(url, json={'latitude': 10}).json()['longitude'] == '-90.500000'  # a valid single-coordinate edit keeps the pair complete
    bare = api_client.post(BASE, json={**body, 'circuit_code': 'LOC-3'}).json()
    assert api_client.patch(f"{BASE}/{bare['id']}", json={'latitude': 14.5}).status_code == 422
    assert api_client.get(url).json()['latitude'] == '10.000000'


def test_database_enforces_pair_and_ranges(api_client, body, db_session):
    item = api_client.post(BASE, json=body).json()
    for statement in ('UPDATE circuits SET latitude = 1 WHERE id = :id', 'UPDATE circuits SET latitude = 91, longitude = 0 WHERE id = :id', 'UPDATE circuits SET latitude = 0, longitude = -181 WHERE id = :id'):
        with pytest.raises(IntegrityError):
            with db_session.begin_nested():
                db_session.execute(text(statement), {'id': item['id']})


def test_quick_creation_permission_and_new_fields(api_client, body):
    # Contextual creation reuses the same endpoint and schema, so the fields are available to it as well.
    created = api_client.post(BASE, json={**body, 'address': 'Zona 1'})
    assert created.status_code == 201 and created.json()['address'] == 'Zona 1'


def test_normal_order_reads_location_from_the_circuit_without_copying(api_client, ticket_payload):
    api_client.patch(f"{BASE}/{ticket_payload['circuit_id']}", json={'address': 'Zona 1', 'latitude': 14.5, 'longitude': -90.5, 'additional_notes': 'Acceso por el portón'})
    order = api_client.post('/api/installation-orders', json=dict(order_type='NORMAL', customer_id=ticket_payload['customer_id'], circuit_id=ticket_payload['circuit_id'], requested_at='2026-10-28T12:00:00-06:00')).json()
    assert order['circuit_location'] == {'address': 'Zona 1', 'latitude': '14.500000', 'longitude': '-90.500000', 'additional_notes': 'Acceso por el portón'}
    assert 'address' not in order and 'latitude' not in order
    api_client.patch(f"{BASE}/{ticket_payload['circuit_id']}", json={'address': None, 'latitude': 15.25, 'longitude': -91.75})
    moved = api_client.get(f"/api/installation-orders/{order['id']}").json()['circuit_location']
    assert (moved['address'], moved['latitude'], moved['longitude']) == (None, '15.250000', '-91.750000')  # the order follows the circuit
    api_client.patch(f"{BASE}/{ticket_payload['circuit_id']}", json={'latitude': None, 'longitude': None})
    assert api_client.get(f"/api/installation-orders/{order['id']}").json()['circuit_location']['latitude'] is None
    service = api_client.post('/api/service-types', json={'name': 'Internet'}).json()['id']
    extra = api_client.post('/api/installation-orders', json=dict(order_type='EXTRAORDINARY', customer_id=ticket_payload['customer_id'], description='x', service_type_id=service, node_id=ticket_payload['node_id'], sector_id=ticket_payload['sector_id'], requested_at='2026-10-28T12:00:00-06:00')).json()
    assert extra['circuit_location'] is None


def test_migration_keeps_historic_circuits_null_and_is_reversible(postgres_engine):
    spec = importlib.util.spec_from_file_location('circuit_location_migration', Path(__file__).parents[1] / 'alembic/versions/0046_circuit_location.py')
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        schema = 'circuit_location_' + uuid4().hex
        connection.execute(text(f'CREATE SCHEMA {schema}'))
        connection.execute(text(f'SET LOCAL search_path TO {schema}'))
        connection.execute(text('CREATE TABLE circuits (id integer PRIMARY KEY)'))
        connection.execute(text('INSERT INTO circuits VALUES (1), (2)'))
        try:
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                row = connection.execute(text('SELECT address, latitude, longitude, additional_notes FROM circuits WHERE id = 1')).one()
                assert tuple(row) == (None, None, None, None)
                columns = {c['name']: c for c in inspect(connection).get_columns('circuits', schema=schema)}
                assert all(columns[name]['nullable'] for name in ('address', 'latitude', 'longitude', 'additional_notes'))
                with pytest.raises(IntegrityError):
                    with connection.begin_nested():
                        connection.execute(text('UPDATE circuits SET latitude = 1 WHERE id = 1'))
                migration.downgrade()
                assert 'latitude' not in {c['name'] for c in inspect(connection).get_columns('circuits', schema=schema)}
        finally:
            transaction.rollback()
