from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from ticketyn.models import Circuit, Sector, Ticket
from ticketyn.models.fms import Activation
from ticketyn.api.fms_data import create_operation
from test_ticket_concurrency import concurrent_database
from test_e2e_update_migration import cli
from test_fms import operation_payload


def sector(api_client, name='Sector nuevo'):
    response = api_client.post('/api/sectors', json={'name': name})
    assert response.status_code == 201
    return response.json()['id']


def test_circuit_sector_create_edit_and_legacy(api_client, ticket_payload, db_session):
    body = {'node_id': ticket_payload['node_id'], 'customer_id': ticket_payload['customer_id'], 'circuit_code': 'SECTOR', 'description': 'Circuito'}
    assert api_client.post('/api/circuits', json=body).status_code == 422
    assert api_client.post('/api/circuits', json={'node_id': ticket_payload['node_id'], **body, 'sector_id': 99999}).status_code == 404
    sid = sector(api_client)
    row = api_client.post('/api/circuits', json={'node_id': ticket_payload['node_id'], **body, 'sector_id': sid}).json()
    assert row['sector_id'] == sid and row['sector']['name'] == 'Sector nuevo'
    circuit = db_session.get(Circuit, row['id']); circuit.sector_id = None; db_session.commit()
    assert api_client.get(f"/api/circuits/{row['id']}").json()['sector_id'] is None
    assert api_client.patch(f"/api/circuits/{row['id']}", json={'description': 'Cambio'}).status_code == 422
    assert api_client.patch(f"/api/circuits/{row['id']}", json={'sector_id': None}).status_code == 422
    assert api_client.patch(f"/api/circuits/{row['id']}", json={'sector_id': sid}).status_code == 200


@pytest.mark.parametrize('path,extra', [
    ('activations', {}),
    ('capacity-changes', {'operation_type': 'INCREASE', 'new_capacity': '500', 'new_unit': 'Mbps'}),
    ('capacity-changes', {'operation_type': 'DECREASE', 'previous_capacity': '1', 'previous_unit': 'Gbps', 'new_capacity': '500', 'new_unit': 'Mbps'}),
    ('circuit-lifecycle', {'operation_type': 'DEACTIVATE'}),
    ('circuit-lifecycle', {'operation_type': 'REACTIVATE'}),
])
def test_all_fms_require_assign_and_snapshot_sector(api_client, operation_payload, ticket_payload, db_session, path, extra):
    extra = dict(extra)
    if extra.get('operation_type') == 'DEACTIVATE':
        extra['reason_id'] = api_client.post('/api/deactivation-reasons', json={'name': 'Prueba'}).json()['id']
    circuit = db_session.get(Circuit, operation_payload['circuit_id']); circuit.sector_id = None; db_session.commit()
    body = {**operation_payload, **extra}
    assert api_client.post('/api/' + path, json=body).status_code == 422
    assert api_client.post('/api/' + path, json={**body, 'sector_id': 999999}).status_code == 404
    sid = ticket_payload['sector_id']
    response = api_client.post('/api/' + path, json={**body, 'sector_id': sid})
    assert response.status_code == 201, response.text
    row = response.json()
    assert row['sector_id'] == sid
    assert api_client.get(f"/api/circuits/{circuit.id}").json()['sector_id'] == sid
    other = sector(api_client)
    assert api_client.post('/api/' + path, json={**body, 'sector_id': other}).status_code == 409
    assert api_client.patch(f'/api/circuits/{circuit.id}', json={'sector_id': other}).status_code == 200
    assert next(item for item in api_client.get('/api/' + path).json() if item['id'] == row['id'])['sector_id'] == sid
    assert api_client.get(f'/api/circuits/{circuit.id}').json()['active']
    assert db_session.scalar(select(Ticket.id)) is None


def test_ticket_automatic_assignment_and_history(api_client, ticket_payload, db_session):
    body = {k: v for k, v in ticket_payload.items() if k != 'sector_id'}
    ticket = api_client.post('/api/tickets', json=body).json()
    assert ticket['sector_id'] == ticket_payload['sector_id']
    cid = ticket_payload['circuit_id']; new = sector(api_client)
    assert api_client.patch(f'/api/circuits/{cid}', json={'sector_id': new}).status_code == 200
    response = api_client.patch(f"/api/tickets/{ticket['id']}", json={'title': 'Corregido', 'sector_id': new})
    assert response.status_code == 200 and response.json()['sector_id'] == ticket['sector_id']
    assert api_client.post('/api/tickets', json=ticket_payload).status_code == 409
    assert api_client.post('/api/tickets', json=body).json()['sector_id'] == new
    circuit = db_session.get(Circuit, cid); circuit.sector_id = None; db_session.commit()
    assert api_client.post('/api/tickets', json=body).status_code == 422
    assert api_client.post('/api/tickets', json={**body, 'sector_id': new}).status_code == 201
    assert api_client.get(f'/api/circuits/{cid}').json()['sector_id'] == new


def test_failed_ticket_and_fms_leave_legacy_sector_null(api_client, ticket_payload, operation_payload, db_session):
    circuit = db_session.get(Circuit, ticket_payload['circuit_id']); circuit.sector_id = None; db_session.commit()
    assert api_client.post('/api/tickets', json={**ticket_payload, 'department_id': 999999}).status_code == 404
    assert api_client.get(f'/api/circuits/{circuit.id}').json()['sector_id'] is None
    assert api_client.post('/api/activations', json={**operation_payload, 'sector_id': ticket_payload['sector_id'], 'responsible_id': 999999}).status_code == 404
    assert api_client.get(f'/api/circuits/{circuit.id}').json()['sector_id'] is None


def test_concurrent_assignment_never_overwrites(concurrent_database):
    engine, payload = concurrent_database
    with Session(engine) as session:
        from ticketyn.models import Responsible
        person = Responsible(name='Operador'); other = Sector(name='Otro')
        session.add_all([person, other]); session.commit()
        person_id, other_id = person.id, other.id
    barrier = Barrier(2)
    def create(sid):
        with Session(engine) as session:
            barrier.wait(timeout=10)
            try:
                return create_operation(session, Activation, {'circuit_id': payload['circuit_id'], 'sector_id': sid, 'responsible_id': person_id, 'effective_at': payload['start_at']}).sector_id
            except HTTPException as error:
                assert error.status_code == 409
                return None
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(create, [payload['sector_id'], other_id]))
    assert sum(result is not None for result in results) == 1
    with Session(engine) as session:
        assert session.get(Circuit, payload['circuit_id']).sector_id == next(result for result in results if result is not None)
        assert len(list(session.scalars(select(Activation)))) == 1


def test_migration_infers_only_unambiguous_ticket_sector(postgres_engine):
    name = 'sector_' + uuid4().hex
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        admin.execute(text('CREATE DATABASE ' + name))
    engine = create_engine(postgres_engine.url.set(database=name))
    try:
        cli(engine.url, 'upgrade', '0015_circuit_service_types')
        with engine.begin() as db:
            db.execute(text("INSERT INTO customers(id,customer_code,name) VALUES(1,'C','Cliente')"))
            db.execute(text("INSERT INTO sectors(id,name) VALUES(1,'Norte'),(2,'Sur')"))
            db.execute(text("INSERT INTO departments(id,name) VALUES(1,'NOC')"))
            db.execute(text("INSERT INTO incident_types(id,name) VALUES(1,'Incidente')"))
            db.execute(text("INSERT INTO responsibles(id,name) VALUES(1,'Operador')"))
            for cid in (1,2,3):
                db.execute(text("INSERT INTO circuits(id,customer_id,circuit_code,description) VALUES(:id,1,:code,'Anterior')"), {'id': cid, 'code': str(cid)})
            for tid,cid,sid in [(1,1,1),(2,1,1),(3,2,1),(4,2,2)]:
                db.execute(text("INSERT INTO tickets(id,ticket_number,reference,title,description,customer_id,circuit_id,sector_id,department_id,incident_type_id,start_at,status) VALUES(:id,:id,:ref,'Histórico','Conservar',1,:cid,:sid,1,1,'2020-01-01T00:00:00Z','OPEN')"), {'id':tid,'ref':str(tid),'cid':cid,'sid':sid})
            db.execute(text("INSERT INTO activations(circuit_id,responsible_id,effective_at,activation_number,reference) VALUES(1,1,'2020-01-01T00:00:00Z',1,'ACT-1')"))
            before = db.execute(text('SELECT * FROM tickets ORDER BY id')).all()
        cli(engine.url, 'upgrade', '0016_circuit_sectors')
        with engine.connect() as db:
            assert db.execute(text('SELECT sector_id FROM circuits ORDER BY id')).scalars().all() == [1,None,None]
            assert db.execute(text('SELECT * FROM tickets ORDER BY id')).all() == before
            assert db.scalar(text('SELECT sector_id FROM activations')) is None
            assert db.scalar(text('SELECT version_num FROM alembic_version')) == '0016_circuit_sectors'
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text('DROP DATABASE ' + name))


def test_legacy_ticket_edit_assigns_current_without_rewriting_history(api_client, ticket_payload, db_session):
    ticket = api_client.post('/api/tickets', json={**ticket_payload, 'status': 'CLOSED'}).json()
    circuit = db_session.get(Circuit, ticket_payload['circuit_id']); circuit.sector_id = None; db_session.commit()
    assert api_client.patch(f"/api/tickets/{ticket['id']}", json={'title': 'Corregido'}).status_code == 422
    current = sector(api_client)
    response = api_client.patch(f"/api/tickets/{ticket['id']}", json={'title': 'Corregido', 'sector_id': current})
    assert response.status_code == 200
    updated = response.json()
    assert updated['sector_id'] == ticket['sector_id']
    assert updated['start_at'] == ticket['start_at'] and updated['end_at'] == ticket['end_at'] and updated['status'] == 'CLOSED'
    assert api_client.get(f'/api/circuits/{circuit.id}').json()['sector_id'] == current
    other = api_client.post('/api/circuits', json={'node_id': ticket_payload['node_id'], 'customer_id': ticket_payload['customer_id'], 'circuit_code': 'OTHER-SECTOR', 'description': 'Otro', 'sector_id': current}).json()
    switched = api_client.patch(f"/api/tickets/{ticket['id']}", json={'circuit_id': other['id']})
    assert switched.status_code == 200
    assert switched.json()['sector_id'] == current
