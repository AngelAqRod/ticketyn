"""Distribution backend: real authentication and disposable PostgreSQL only."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ticketyn.models import (
    Activation, Circuit, Customer, DistributionAudit, DistributionDevice, DistributionPort,
    Node, Responsible, Sector,
)
from ticketyn.models.security import SecurityRole, SecurityRolePermission
from ticketyn.api import distribution as api
from ticketyn.api.distribution_data import distribution_write, record, validate_circuit_distribution
from ticketyn.schemas.distribution import DeviceCreate, DeviceMove, DistributionStatus, PortMove
from test_fms import operation_payload


def post(client, path, body):
    response = client.post('/api/' + path, json=body)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def topology(api_client, ticket_payload, db_session):
    device = post(api_client, 'distribution-devices', {'node_id': ticket_payload['node_id'], 'name': 'CORE A'})
    other = post(api_client, 'distribution-devices', {'node_id': ticket_payload['node_id'], 'name': 'CORE B'})
    # Unclassified historical ports must remain usable and editable.
    rows = [DistributionPort(distribution_device_id=device['id'], name=name) for name in ('sfp+1', 'sfp+2')]
    db_session.add_all(rows); db_session.commit()
    port, empty = [api_client.get(f'/api/distribution-ports/{row.id}').json() for row in rows]
    return device, other, port, empty


def assign(client, circuit_id, device, port=None):
    return client.patch(f'/api/circuits/{circuit_id}', json={
        'distribution_device_id': device['id'] if device else None,
        'distribution_port_id': port['id'] if port else None,
    })


def test_crud_filters_counts_and_delete_evidence(api_client, ticket_payload, topology, db_session):
    device, other, port, empty = topology
    assert device['port_count'] == device['circuit_count'] == 0
    assert api_client.get(f"/api/distribution-ports/{empty['id']}").json()['circuit_count'] == 0
    assert len(api_client.get('/api/distribution-devices', params={'node_id': ticket_payload['node_id']}).json()) == 2
    assert len(api_client.get('/api/distribution-ports', params={'distribution_device_id': other['id']}).json()) == 0
    assert len(api_client.get('/api/distribution-ports', params={'distribution_device_id': device['id'], 'limit': 1, 'offset': 1}).json()) == 1
    assert api_client.get('/api/distribution-devices?search=CORE%20B').json()[0]['id'] == other['id']
    assert api_client.patch(f"/api/distribution-devices/{device['id']}", json={'name': 'CORE corregido', 'description': 'Distribución'}).status_code == 200
    assert api_client.patch(f"/api/distribution-ports/{port['id']}", json={'name': 'sfp+01', 'description': 'Corregido'}).status_code == 200
    assert api_client.patch(f"/api/distribution-ports/{port['id']}", json={'description': None}).json()['description'] is None
    assert api_client.delete(f"/api/distribution-devices/{device['id']}").status_code == 409
    for row in (port, empty):
        assert api_client.delete(f"/api/distribution-ports/{row['id']}").status_code == 204
    assert api_client.delete(f"/api/distribution-devices/{device['id']}").status_code == 204
    assert api_client.get(f"/api/distribution-devices/{device['id']}").status_code == 404
    evidence = db_session.scalar(select(DistributionAudit).where(DistributionAudit.resource_type == 'DEVICE',
                                DistributionAudit.resource_id == device['id'], DistributionAudit.action == 'DELETE'))
    assert evidence.actor_id and evidence.occurred_at and evidence.before['name'] == 'CORE corregido'
    assert evidence.after is None


@pytest.mark.parametrize('name', [' core a ', 'CoRe A', 'CORE\t A', 'CORE   A'])
def test_conservative_names_scoped_and_unicode(api_client, ticket_payload, topology, db_session, name):
    device, other, port, empty = topology
    assert api_client.post('/api/distribution-devices', json={'node_id': device['node_id'], 'name': name}).status_code == 409
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(DistributionPort(distribution_device_id=device['id'], name=' SFP+1 ')); db_session.flush()
    db_session.add(DistributionPort(distribution_device_id=other['id'], name='sfp+1'))
    for distinct in ('sfpplus1', 'sfp de 10 g 1', 'sfp+01'):
        db_session.add(DistributionPort(distribution_device_id=device['id'], name=distinct))
    db_session.commit()
    node = post(api_client, 'nodes', {'name': 'Otro nodo'})
    post(api_client, 'distribution-devices', {'node_id': node['id'], 'name': name})
    post(api_client, 'distribution-devices', {'node_id': node['id'], 'name': 'ÁRBOL'})
    assert api_client.post('/api/distribution-devices', json={'node_id': node['id'], 'name': ' árbol '}).status_code == 409


def test_optional_assignment_patch_and_shared_ports(api_client, ticket_payload, topology, db_session):
    device, other, port, empty = topology
    cid = ticket_payload['circuit_id']
    original = api_client.get(f'/api/circuits/{cid}').json()
    assert original['distribution_device_id'] is original['distribution_port_id'] is None
    assert assign(api_client, cid, device).status_code == 200
    linked = assign(api_client, cid, device, port)
    assert linked.status_code == 200 and linked.json()['distribution_port']['name'] == 'sfp+1'
    assert api_client.patch(f'/api/circuits/{cid}', json={'description': 'Cambio ajeno'}).json()['distribution_port_id'] == port['id']
    second = post(api_client, 'circuits', {'customer_id': ticket_payload['customer_id'], 'node_id': device['node_id'],
                  'sector_id': ticket_payload['sector_id'], 'circuit_code': 'SECOND', 'description': 'Otro',
                  'distribution_device_id': device['id'], 'distribution_port_id': port['id']})
    assert second['distribution_port_id'] == port['id']
    assert api_client.get(f"/api/distribution-ports/{port['id']}").json()['circuit_count'] == 2
    assert api_client.get(f"/api/distribution-devices/{device['id']}").json()['circuit_count'] == 2
    assert api_client.patch(f"/api/distribution-ports/{port['id']}", json={'name': 'uplink corregido'}).status_code == 200
    assert api_client.get(f'/api/circuits/{cid}').json()['distribution_port']['name'] == 'uplink corregido'
    assert api_client.patch(f'/api/circuits/{cid}', json={'distribution_device_id': None}).status_code == 422
    assert api_client.patch(f'/api/circuits/{cid}', json={'distribution_port_id': None}).json()['distribution_device_id'] == device['id']
    assert assign(api_client, cid, None).status_code == 200
    assert db_session.scalar(select(func.count()).select_from(Activation)) == 0
    assert api_client.get(f'/api/circuits/{cid}').json()['node_id'] == original['node_id']


def test_invalid_relationships_rejected_without_silent_changes(api_client, ticket_payload, topology):
    device, other, port, empty = topology
    cid = ticket_payload['circuit_id']
    assert api_client.patch(f'/api/circuits/{cid}', json={'distribution_port_id': port['id']}).status_code == 422
    assert assign(api_client, cid, other, port).status_code == 422
    assert assign(api_client, cid, {'id': 999999}).status_code == 404
    node = post(api_client, 'nodes', {'name': 'Nodo remoto'})
    remote = post(api_client, 'distribution-devices', {'node_id': node['id'], 'name': 'Remoto'})
    assert assign(api_client, cid, remote).status_code == 422
    assert assign(api_client, cid, device, port).status_code == 200
    assert api_client.patch(f'/api/circuits/{cid}', json={'node_id': node['id']}).status_code == 422
    assert api_client.get(f'/api/circuits/{cid}').json()['distribution_port_id'] == port['id']
    assert api_client.patch(f'/api/circuits/{cid}', json={'node_id': node['id'], 'distribution_device_id': remote['id'], 'distribution_port_id': None}).status_code == 200


@pytest.mark.parametrize('via_port', [False, True])
def test_associations_block_moves_and_deletion_including_inactive_circuits(api_client, ticket_payload, topology, via_port):
    device, other, port, empty = topology
    cid = ticket_payload['circuit_id']
    assert assign(api_client, cid, device, port if via_port else None).status_code == 200
    assert api_client.patch(f'/api/circuits/{cid}', json={'active': False}).status_code == 200
    node = post(api_client, 'nodes', {'name': 'Nodo destino'})
    assert api_client.post(f"/api/distribution-devices/{device['id']}/move", json={'node_id': node['id']}).status_code == 409
    assert api_client.delete(f"/api/distribution-devices/{device['id']}").status_code == 409
    if via_port:
        assert api_client.post(f"/api/distribution-ports/{port['id']}/move", json={'distribution_device_id': other['id']}).status_code == 409
        assert api_client.patch(f"/api/distribution-ports/{port['id']}/status", json={'active': False}).status_code == 409
        assert api_client.delete(f"/api/distribution-ports/{port['id']}").status_code == 409


def test_unassigned_moves_status_and_inactive_reference_preservation(api_client, ticket_payload, topology):
    device, other, port, empty = topology
    node = post(api_client, 'nodes', {'name': 'Nodo destino'})
    assert api_client.post(f"/api/distribution-devices/{device['id']}/move", json={'node_id': node['id']}).json()['node_id'] == node['id']
    assert api_client.post(f"/api/distribution-ports/{port['id']}/move", json={'distribution_device_id': other['id']}).json()['distribution_device_id'] == other['id']
    assert api_client.patch(f"/api/distribution-ports/{port['id']}/status", json={'active': False}).status_code == 200
    assert api_client.get('/api/distribution-ports', params={'distribution_device_id': other['id']}).json() == []
    assert len(api_client.get('/api/distribution-ports', params={'distribution_device_id': other['id'], 'include_inactive': True}).json()) == 1
    cid = ticket_payload['circuit_id']
    assert assign(api_client, cid, other, port).status_code == 422
    assert api_client.patch(f"/api/distribution-ports/{port['id']}/status", json={'active': True}).status_code == 200
    assert assign(api_client, cid, other, port).status_code == 200
    # Device deactivation does not detach circuits; unchanged historical links stay editable.
    assert api_client.patch(f"/api/distribution-devices/{other['id']}/status", json={'active': False}).status_code == 200
    assert api_client.patch(f'/api/circuits/{cid}', json={'description': 'Conservado'}).status_code == 200
    assert api_client.patch(f'/api/circuits/{cid}', json={'distribution_port_id': None}).status_code == 200
    assert assign(api_client, cid, None).status_code == 200
    assert assign(api_client, cid, other, port).status_code == 422


def test_services_projection_zero_ports_pagination_and_no_sensitive_data(api_client, ticket_payload, topology, db_session):
    device, other, port, empty = topology
    cid = ticket_payload['circuit_id']
    db_session.get(Circuit, cid).cpe_configuration = 'CPE-SECRET-NOT-FOR-DISTRIBUTION'; db_session.commit()
    assert assign(api_client, cid, device).status_code == 200
    path = f"/api/distribution-devices/{device['id']}/circuits"
    row = api_client.get(path + '?without_port=true').json()[0]
    assert row['customer_id'] == ticket_payload['customer_id'] and row['circuit_code'] == 'MANUAL-CIRCUIT'
    assert row['service_type_name'] is None and row['distribution_port_id'] is None
    assert 'CPE-SECRET' not in api_client.get(path).text and 'cpe_configuration' not in row
    assert api_client.get(path + '?offset=1').json() == []
    assert api_client.get(path + f"?port_id={port['id']}").json() == []
    assert api_client.get(path + f"?port_id={port['id']}&without_port=true").status_code == 422
    assert len(api_client.get('/api/distribution-ports', params={'distribution_device_id': device['id']}).json()) == 2
    assert assign(api_client, cid, device, port).status_code == 200
    assert api_client.get(path + f"?port_id={port['id']}").json()[0]['distribution_port_name'] == 'sfp+1'
    service = post(api_client, 'service-types', {'name': 'INTERNET Ñ'})
    assert api_client.patch(f'/api/circuits/{cid}', json={'service_type_id': service['id']}).status_code == 200
    assert api_client.get(path).json()[0]['service_type_name'] == 'INTERNET Ñ'


@pytest.mark.parametrize('values', [
    {'distribution_port_id': 'port'},
    {'distribution_device_id': 'device', 'node_id': None},
    {'distribution_device_id': 'other', 'distribution_port_id': 'port'},
    {'distribution_device_id': 'device', 'node_id': 999999},
])
def test_postgresql_rejects_invalid_relations_without_api(db_session, ticket_payload, topology, values):
    device, other, port, empty = topology
    ids = {'device': device['id'], 'other': other['id'], 'port': port['id']}
    values = {key: ids.get(value, value) if isinstance(value, str) else value for key, value in values.items()}
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(update(Circuit).where(Circuit.id == ticket_payload['circuit_id']).values(**values))


def test_audit_failure_rolls_back_resource_and_assignment(api_client, ticket_payload, topology, db_session, monkeypatch, caplog):
    device, other, port, empty = topology
    def broken(*args, **kwargs):
        raise SQLAlchemyError('sensitive-database-diagnostic')
    with monkeypatch.context() as patch:
        patch.setattr(api, 'record', broken)
        response = api_client.post('/api/distribution-devices', json={'node_id': device['node_id'], 'name': 'Rollback'})
        assert response.status_code == 503 and 'sensitive' not in response.text
    assert db_session.scalar(select(DistributionDevice.id).where(DistributionDevice.name == 'Rollback')) is None
    from ticketyn.api import circuits
    with monkeypatch.context() as patch:
        patch.setattr(circuits, 'record', broken)
        assert assign(api_client, ticket_payload['circuit_id'], device, port).status_code == 503
    assert api_client.get(f"/api/circuits/{ticket_payload['circuit_id']}").json()['distribution_device_id'] is None
    assert 'sensitive-database-diagnostic' not in caplog.text


def test_distribution_keeps_fms_snapshots_and_notification_intent(api_client, topology, operation_payload, db_session):
    from ticketyn.models import MailEventConfig
    from ticketyn.notifications.fields import ACTIVATION_EVENT
    event = db_session.get(MailEventConfig, ACTIVATION_EVENT)
    if event is None:
        event = MailEventConfig(event_key=ACTIVATION_EVENT, mode='AUTOMATIC')
        db_session.add(event)
    else:
        event.mode = 'AUTOMATIC'
    db_session.commit()
    activation = post(api_client, 'activations', {**operation_payload, 'activation_notes': 'Notas inmutables\nPUERTO: dato histórico'})
    tables = ('activations', 'activation_interventions', 'capacity_changes', 'circuit_lifecycle_operations', 'mail_notification_requests')
    before = {table: db_session.execute(text(f'SELECT to_jsonb(t) FROM {table} t ORDER BY id')).scalars().all() for table in tables}
    assert len(before['mail_notification_requests']) == 1
    device, other, port, empty = topology
    assert assign(api_client, operation_payload['circuit_id'], device, port).status_code == 200
    assert api_client.patch(f"/api/distribution-ports/{port['id']}", json={'name': 'Puerto corregido'}).status_code == 200
    assert assign(api_client, operation_payload['circuit_id'], other).status_code == 200
    for table in tables:
        assert db_session.execute(text(f'SELECT to_jsonb(t) FROM {table} t ORDER BY id')).scalars().all() == before[table]
    assert api_client.get(f"/api/activations/{activation['id']}").json()['activation_notes'] == 'Notas inmutables\nPUERTO: dato histórico'


def test_inactive_historical_port_is_preserved_but_not_newly_assigned(api_client, topology, ticket_payload, db_session):
    device, other, port, empty = topology
    cid = ticket_payload['circuit_id']
    # Simulate a historical inactive link without going through today's deactivation policy.
    assert assign(api_client, cid, device, port).status_code == 200
    db_session.get(DistributionPort, port['id']).active = False; db_session.commit()
    assert api_client.patch(f'/api/circuits/{cid}', json={'description': 'Conserva la referencia'}).status_code == 200
    assert api_client.get(f'/api/circuits/{cid}').json()['distribution_port_id'] == port['id']
    assert api_client.patch(f'/api/circuits/{cid}', json={'distribution_port_id': None}).status_code == 200
    assert assign(api_client, cid, device, port).status_code == 422


@pytest.mark.parametrize('path,body', [
    ('distribution-devices', {'node_id': 999999, 'name': 'X'}),

])
def test_missing_parent_is_404(api_client, path, body):
    assert api_client.post('/api/' + path, json=body).status_code == 404


@pytest.mark.parametrize('name', ['', ' \t ', 'x' * 256])
def test_invalid_names_are_rejected(api_client, topology, name):
    device, other, port, empty = topology
    assert api_client.post('/api/distribution-devices', json={'node_id': device['node_id'], 'name': name}).status_code == 422
    assert api_client.patch(f"/api/distribution-ports/{port['id']}", json={'name': name}).status_code == 422


@pytest.mark.parametrize('role', ['SUPERADMIN', 'ADMIN', 'OPERATOR', 'AUDITOR', 'CUSTOM'])
def test_roles_combined_fields_and_anonymous_denial(api_client, topology, db_session, role):
    device, other, port, empty = topology
    if role == 'CUSTOM':
        selected = SecurityRole(name='Sin facultades de distribución'); db_session.add(selected); db_session.flush()
    else:
        selected = db_session.scalar(select(SecurityRole).where(SecurityRole.code == role))
    account = db_session.scalar(select(Responsible).where(Responsible.username == 'security-test-superadmin'))
    account.security_role_id = selected.id; db_session.commit()
    root = '/api/distribution-devices'; target = root + '/' + str(device['id'])
    assert api_client.get(root).status_code == (403 if role == 'CUSTOM' else 200)
    expected_write = 403 if role in {'AUDITOR', 'CUSTOM'} else 200
    assert api_client.patch(target, json={'description': 'Autorizado'}).status_code == expected_write
    created = api_client.post(root, json={'node_id': device['node_id'], 'name': 'Nuevo'})
    assert created.status_code == (403 if role in {'AUDITOR', 'CUSTOM'} else 201)
    assert api_client.patch(f"/api/distribution-ports/{port['id']}", json={'name': 'Corregido'}).status_code == expected_write
    for path, method, body in [
        (target + '/move', 'post', {'node_id': device['node_id']}),
        (target + '/status', 'patch', {'active': False}),
        (f"/api/distribution-ports/{port['id']}/move", 'post', {'distribution_device_id': other['id']}),
        (f"/api/distribution-ports/{empty['id']}/status", 'patch', {'active': False}),
    ]:
        assert getattr(api_client, method)(path, json=body).status_code == (200 if role in {'SUPERADMIN', 'ADMIN'} else 403)
    assert api_client.delete(f"/api/distribution-ports/{empty['id']}").status_code == (204 if role in {'SUPERADMIN', 'ADMIN'} else 403)
    if role in {'SUPERADMIN', 'ADMIN', 'OPERATOR'}:
        for body in ({'active': False}, {'node_id': device['node_id']}, {'name': 'Escalado', 'active': False}):
            assert api_client.patch(target, json=body).status_code == 422
        assert api_client.patch(f"/api/distribution-ports/{port['id']}", json={'distribution_device_id': other['id']}).status_code == 422
    api_client.headers.pop('Authorization')
    assert api_client.get(root).status_code == 401
    assert api_client.post(target + '/move', json={'node_id': device['node_id']}).status_code == 401


def test_custom_permissions_immediate_without_catalog_escalation(api_client, topology, db_session):
    device, other, port, empty = topology
    role = SecurityRole(name='Solo edición de equipos'); db_session.add(role); db_session.flush()
    db_session.add_all([SecurityRolePermission(role_id=role.id, permission_code=code)
                       for code in ('distribution_devices.view', 'distribution_devices.edit')])
    person = db_session.scalar(select(Responsible).where(Responsible.username == 'security-test-superadmin'))
    person.security_role_id = role.id; db_session.commit()
    assert api_client.patch(f"/api/distribution-devices/{device['id']}", json={'name': 'Permitido'}).status_code == 200
    assert api_client.post(f"/api/distribution-devices/{device['id']}/move", json={'node_id': device['node_id']}).status_code == 403
    assert api_client.get('/api/security/roles').status_code == 403
    assert api_client.get(f"/api/distribution-devices/{device['id']}/circuits").status_code == 403
    grant = db_session.get(SecurityRolePermission, (role.id, 'distribution_devices.edit'))
    db_session.delete(grant); db_session.commit()
    assert api_client.patch(f"/api/distribution-devices/{device['id']}", json={'name': 'Revocado'}).status_code == 403


@pytest.fixture
def concurrent_topology(postgres_engine):
    # Independent committed records only in the disposable test cluster.
    suffix = uuid4().hex
    with Session(postgres_engine) as session:
        node = Node(name='Distribution race ' + suffix); other_node = Node(name='Destination ' + suffix)
        customer = Customer(name='Distribution customer ' + suffix, customer_code=suffix)
        sector = Sector(name='Distribution sector ' + suffix); actor = Responsible(name='Distribution actor ' + suffix)
        session.add_all([node, other_node, customer, sector, actor]); session.flush()
        device = DistributionDevice(node_id=node.id, name='CORE'); session.add(device); session.flush()
        other = DistributionDevice(node_id=node.id, name='OTHER'); port = DistributionPort(distribution_device_id=device.id, name='1')
        circuit = Circuit(node_id=node.id, customer_id=customer.id, sector_id=sector.id, circuit_code=suffix, description='Concurrent circuit')
        session.add_all([other, port, circuit]); session.flush()
        data = {'engine': postgres_engine, 'node': node.id, 'destination': other_node.id, 'device': device.id,
                'other': other.id, 'port': port.id, 'circuit': circuit.id, 'actor': actor.id,
                'customer': customer.id, 'sector': sector.id}
        session.commit()
    try:
        yield data
    finally:
        with Session(postgres_engine) as session:
            session.execute(delete(DistributionAudit).where(DistributionAudit.actor_id == data['actor']))
            session.execute(delete(Circuit).where(Circuit.id == data['circuit']))
            devices = select(DistributionDevice.id).where(DistributionDevice.node_id.in_([data['node'], data['destination']]))
            session.execute(delete(DistributionPort).where(DistributionPort.distribution_device_id.in_(devices)))
            session.execute(delete(DistributionDevice).where(DistributionDevice.node_id.in_([data['node'], data['destination']])))
            for model, key in ((Responsible, 'actor'), (Customer, 'customer'), (Sector, 'sector')):
                session.execute(delete(model).where(model.id == data[key]))
            session.execute(delete(Node).where(Node.id.in_([data['node'], data['destination']])))
            session.commit()


def request_for(id):
    return SimpleNamespace(state=SimpleNamespace(principal=SimpleNamespace(id=id)))


@pytest.mark.parametrize('action', ['device_move', 'port_move', 'port_status', 'port_delete'])
def test_assignment_race_blocks_structural_change(concurrent_topology, action):
    data = concurrent_topology
    held, release, attempted = Event(), Event(), Event()
    def assign_first():
        with Session(data['engine']) as session, distribution_write(session):
            item = session.get(Circuit, data['circuit'])
            values = {'distribution_device_id': data['device'], 'distribution_port_id': data['port']}
            validate_circuit_distribution(session, values, item)
            for key, value in values.items(): setattr(item, key, value)
            session.flush(); held.set()
            assert release.wait(5)
    def change():
        from fastapi import HTTPException
        attempted.set()
        try:
            with Session(data['engine']) as session:
                request = request_for(data['actor'])
                if action == 'device_move': api.move_device(data['device'], DeviceMove(node_id=data['destination']), session, request)
                elif action == 'port_move': api.move_port(data['port'], PortMove(distribution_device_id=data['other']), session, request)
                elif action == 'port_status': api.port_status(data['port'], DistributionStatus(active=False), session, request)
                else: api.delete_port(data['port'], session, request)
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(assign_first)
        assert held.wait(5)
        second = pool.submit(change)
        try:
            assert attempted.wait(5)
        finally:
            release.set()
        first.result(timeout=10)
        assert second.result(timeout=10) == 409
    with Session(data['engine']) as session:
        assert session.get(DistributionPort, data['port']).active
        assert session.get(Circuit, data['circuit']).distribution_port_id == data['port']


def test_concurrent_duplicate_names_one_commit_one_audit(concurrent_topology):
    data = concurrent_topology; barrier = Barrier(2)
    def create(name):
        from fastapi import HTTPException
        with Session(data['engine']) as session:
            barrier.wait(5)
            try:
                api.create_device(DeviceCreate(node_id=data['node'], name=name), session, request_for(data['actor']))
                return 201
            except HTTPException as error:
                return error.status_code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(create, ['Concurrent Name', ' concurrent   name ']))
    assert sorted(results) == [201, 409]
    with Session(data['engine']) as session:
        assert session.scalar(select(func.count()).select_from(DistributionAudit).where(
            DistributionAudit.actor_id == data['actor'], DistributionAudit.action == 'CREATE')) == 1


def test_completed_move_prevents_assignment_using_old_topology(concurrent_topology):
    from fastapi import HTTPException
    data = concurrent_topology
    with Session(data['engine']) as session:
        api.move_device(data['device'], DeviceMove(node_id=data['destination']), session, request_for(data['actor']))
    with Session(data['engine']) as session:
        with pytest.raises(HTTPException) as error:
            with distribution_write(session):
                item = session.get(Circuit, data['circuit'])
                validate_circuit_distribution(session, {'distribution_device_id': data['device'], 'distribution_port_id': data['port']}, item)
        assert error.value.status_code == 422
        assert session.get(Circuit, data['circuit']).distribution_device_id is None


def test_fk_protects_deletion_even_if_precheck_misses_reference(api_client, topology, ticket_payload, monkeypatch):
    from ticketyn.api import distribution
    device, other, port, empty = topology
    assert assign(api_client, ticket_payload['circuit_id'], device, port).status_code == 200
    with monkeypatch.context() as patch:
        patch.setattr(distribution, 'ensure_unassigned', lambda *args: None)
        assert api_client.delete(f"/api/distribution-ports/{port['id']}").status_code == 409
    assert api_client.get(f"/api/distribution-ports/{port['id']}").status_code == 200


def test_commit_failure_does_not_leave_changes_or_audit(api_client, topology, db_session, monkeypatch):
    device, other, port, empty = topology
    count = db_session.scalar(select(func.count()).select_from(DistributionAudit))
    def broken_commit():
        raise SQLAlchemyError('private-commit-diagnostic')
    with monkeypatch.context() as patch:
        patch.setattr(db_session, 'commit', broken_commit)
        response = api_client.patch(f"/api/distribution-devices/{device['id']}", json={'name': 'No confirmado'})
        assert response.status_code == 503 and 'private-commit' not in response.text
    assert api_client.get(f"/api/distribution-devices/{device['id']}").json()['name'] == device['name']
    assert db_session.scalar(select(func.count()).select_from(DistributionAudit)) == count


@pytest.mark.parametrize('port_total, linked_circuits, inactive_port, inactive_circuits, direct', [
    (0, 0, False, False, False),
    (2, 0, False, False, False),
    (1, 1, False, False, False),
    (3, 2, False, False, False),
    (1, 0, True, False, False),
    (2, 2, False, True, False),
    (2, 0, False, False, True),
])
def test_unassigned_ports_aggregate_matches_detail_and_filters(
    api_client, ticket_payload, db_session, port_total, linked_circuits,
    inactive_port, inactive_circuits, direct, numbered_port,
):
    device = post(api_client, 'distribution-devices', {'node_id': ticket_payload['node_id'], 'name': 'COUNTER'})
    ports = [numbered_port(device['id'], prefix='Port ', number=i) for i in range(port_total)]
    for i in range(linked_circuits + int(direct)):
        post(api_client, 'circuits', {
            'customer_id': ticket_payload['customer_id'], 'node_id': device['node_id'],
            'sector_id': ticket_payload['sector_id'], 'circuit_code': f'COUNT-{i}',
            'description': 'Contador', 'distribution_device_id': device['id'],
            'distribution_port_id': ports[0]['id'] if linked_circuits else None,
        })
    if inactive_port:
        assert api_client.patch(f"/api/distribution-ports/{ports[0]['id']}/status", json={'active': False}).status_code == 200
    if inactive_circuits:
        db_session.execute(update(Circuit).where(Circuit.distribution_device_id == device['id']).values(active=False))
        db_session.flush()
    # Two circuits on one port still occupy just one registered port.
    expected = port_total - int(linked_circuits > 0)
    detail = api_client.get(f"/api/distribution-devices/{device['id']}").json()
    registered = api_client.get('/api/distribution-ports', params={
        'distribution_device_id': device['id'], 'include_inactive': True,
    }).json()
    assert detail['unassigned_port_count'] == expected == sum(p['circuit_count'] == 0 for p in registered)
    assert detail['port_count'] == port_total
    assert detail['circuit_count'] == linked_circuits + int(direct)
    post(api_client, 'distribution-devices', {'node_id': device['node_id'], 'name': 'ZZ OTHER'})
    params = {'node_id': device['node_id'], 'search': 'COUNTER', 'limit': 1, 'offset': 0}
    listed = api_client.get('/api/distribution-devices', params=params).json()
    assert listed == [detail]
    assert api_client.get('/api/distribution-devices', params={**params, 'offset': 1}).json() == []
