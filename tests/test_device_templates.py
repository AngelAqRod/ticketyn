"""Template definitions and atomic application, only ephemeral PostgreSQL."""
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from ticketyn.models import DistributionAudit, DistributionDevice, DistributionPort, DistributionDeviceTemplate
from test_port_nomenclatures import catalog  # noqa: F401
from test_distribution import topology  # noqa: F401

BASE = '/api/distribution-device-templates'


def draft(catalog, **changes):
    return {'name': 'Modelo reutilizable', 'groups': [group(catalog)], **changes}


def group(catalog, **changes):
    return {'nomenclature_id': catalog['id'], 'numbering_format': 'N', 'positions': [], 'start': 0, 'end': 2, **changes}


def checked(client, payload, id=None):
    response = client.post(BASE + '/preview' + (f'?template_id={id}' if id else ''), json=payload)
    assert response.status_code == 200, response.text
    return {**payload, 'preview_token': response.json()['preview_token']}


def create(client, payload):
    response = client.post(BASE, json=checked(client, payload))
    assert response.status_code == 201, response.text
    return response.json()


def device(client, template, node_id, name='Nuevo equipo'):
    return client.post('/api/distribution-devices', json={'name': name, 'node_id': node_id,
        'template_id': template['id'], 'template_token': template['preview_token']})


@pytest.mark.parametrize('fmt,positions,expected', [('N', [], 'SFP+0'), ('X/Y', [2], 'SFP+2/0'),
    ('X/Y/Z', [1, 0], 'SFP+1/0/0'), ('W/X/Y/Z', [0, 1, 2], 'SFP+0/1/2/0')])
def test_generate_exact_names_and_natural_order(api_client, catalog, fmt, positions, expected):
    payload = draft(catalog, groups=[group(catalog, numbering_format=fmt, positions=positions, end=11)])
    item = create(api_client, payload)
    assert item['groups'][0]['names'][0] == expected
    assert item['groups'][0]['names'][2].endswith('2')
    assert item['groups'][0]['names'][10].endswith('10')
    assert item['total_ports'] == 12


def test_multiple_groups_apply_and_independence(api_client, catalog, ticket_payload, db_session):
    second = api_client.post('/api/port-nomenclatures', json={'name': 'Cobre', 'prefix': 'ether', 'formats': ['N']}).json()
    payload = draft(catalog, manufacturer='Fabricante informativo', groups=[group(catalog), group(second, start=1, end=1)])
    item = create(api_client, payload)
    created = device(api_client, item, ticket_payload['node_id'])
    assert created.status_code == 201, created.text
    assert created.json()['port_count'] == 4
    ports = api_client.get('/api/distribution-ports', params={'distribution_device_id': created.json()['id']}).json()
    assert {p['name'] for p in ports} == {'SFP+0', 'SFP+1', 'SFP+2', 'ether1'}
    # Future definitions change, never the installed records.
    updated = api_client.patch(BASE + f"/{item['id']}", json=checked(api_client, draft(catalog, groups=[group(catalog, end=5)]), item['id']))
    assert updated.status_code == 200, updated.text
    assert api_client.get(f"/api/distribution-devices/{created.json()['id']}").json()['port_count'] == 4
    assert device(api_client, item, ticket_payload['node_id'], 'Obsoleto').status_code == 409
    assert device(api_client, updated.json(), ticket_payload['node_id'], 'Otro equipo').json()['port_count'] == 6
    audits = db_session.scalars(select(DistributionAudit).where(DistributionAudit.resource_type == 'TEMPLATE')).all()
    assert [a.action for a in audits] == ['CREATE', 'EDIT']
    assert audits[0].after['groups'][0]['start'] == 0
    # Circuit associations can use the ordinary generated records.
    circuit = api_client.patch(f"/api/circuits/{ticket_payload['circuit_id']}", json={
        'distribution_device_id': created.json()['id'], 'distribution_port_id': ports[0]['id']})
    assert circuit.status_code == 200, circuit.text


@pytest.mark.parametrize('changes', [
    {'groups': []}, {'groups': [{'nomenclature_id': 999999, 'numbering_format': 'N', 'positions': [], 'start': 0, 'end': 1}]},
    {'name': ' '},
])
def test_invalid_definition(api_client, catalog, changes):
    assert api_client.post(BASE + '/preview', json=draft(catalog, **changes)).status_code == 422


@pytest.mark.parametrize('change', [{'end': -1}, {'start': 3, 'end': 2}, {'end': 256}, {'start': True},
    {'numbering_format': 'other'}, {'positions': [1]}, {'start': 1.5}])
def test_invalid_ranges(api_client, catalog, change):
    payload = draft(catalog, groups=[group(catalog, **change)])
    assert api_client.post(BASE + '/preview', json=payload).status_code == 422


def test_cross_group_duplicates_and_limits(api_client, catalog):
    for groups in ([group(catalog), group(catalog)], [group(catalog, end=127), group(catalog, start=128, end=256)],
                   [group(catalog, start=i, end=i) for i in range(17)]):
        response = api_client.post(BASE + '/preview', json=draft(catalog, groups=groups))
        assert response.status_code == 422
    duplicate = api_client.post(BASE + '/preview', json=draft(catalog, groups=[group(catalog), group(catalog)]))
    assert 'grupos 1 y 2' in duplicate.text
    item = create(api_client, draft(catalog, groups=[group(catalog, end=255)]))
    assert item['total_ports'] == 256


def test_nomenclature_deactivation_and_reactivation(api_client, catalog, ticket_payload):
    payload = draft(catalog)
    item = create(api_client, payload)
    body = {k: catalog[k] for k in ('name', 'prefix', 'formats', 'active')}
    assert api_client.delete(f"/api/port-nomenclatures/{catalog['id']}").status_code == 409
    assert api_client.patch(f"/api/port-nomenclatures/{catalog['id']}", json={**body, 'active': False}).status_code == 200
    assert not api_client.get(BASE + f"/{item['id']}").json()['usable']
    assert device(api_client, item, ticket_payload['node_id']).status_code == 422
    assert api_client.post(BASE + '/preview', json=payload).status_code == 422
    inactive = {**payload, 'active': False}
    saved = api_client.patch(BASE + f"/{item['id']}", json=checked(api_client, inactive, item['id']))
    assert saved.status_code == 200
    assert api_client.patch(BASE + f"/{item['id']}", json=checked(api_client, payload, item['id'])).status_code == 422


def test_preview_required_and_unique_name(api_client, catalog, ticket_payload, db_session):
    item = create(api_client, draft(catalog))
    assert api_client.post(BASE, json=draft(catalog)).status_code == 409
    assert api_client.post(BASE, json=checked(api_client, draft(catalog, name=' MODELO  REUTILIZABLE '))).status_code == 409
    assert device(api_client, {**item, 'preview_token': 'a' * 64}, ticket_payload['node_id']).status_code == 409
    assert db_session.scalar(select(func.count()).select_from(DistributionDevice)) == 0


def test_all_or_nothing_when_port_or_audit_fails(api_client, catalog, ticket_payload, db_session, monkeypatch):
    from ticketyn.api import port_nomenclatures
    item = create(api_client, draft(catalog))
    original = port_nomenclatures.record
    def fail_second(session, actor_id, port, action, **kwargs):
        if port.name.endswith('1'):
            raise SQLAlchemyError('simulated failure after inserting ports')
        return original(session, actor_id, port, action, **kwargs)
    monkeypatch.setattr(port_nomenclatures, 'record', fail_second)
    result = device(api_client, item, ticket_payload['node_id'])
    assert result.status_code == 503, result.text
    assert db_session.scalar(select(func.count()).select_from(DistributionDevice)) == 0
    assert db_session.scalar(select(func.count()).select_from(DistributionPort)) == 0
    assert db_session.scalar(select(func.count()).select_from(DistributionAudit).where(DistributionAudit.resource_type.in_(['DEVICE', 'PORT']))) == 0
    monkeypatch.setattr(port_nomenclatures, 'record', original)
    assert device(api_client, item, ticket_payload['node_id']).status_code == 201
    assert device(api_client, item, ticket_payload['node_id']).status_code == 409
    assert db_session.scalar(select(func.count()).select_from(DistributionDevice)) == 1


@pytest.mark.parametrize('role', ['SUPERADMIN', 'ADMIN', 'OPERATOR', 'AUDITOR', 'CUSTOM'])
def test_permissions_no_catalog_escalation(api_client, catalog, ticket_payload, db_session, role):
    from ticketyn.models import Responsible
    from ticketyn.models.security import SecurityRole, SecurityRolePermission
    item = create(api_client, draft(catalog))
    if role == 'CUSTOM':
        selected = SecurityRole(name='Creador de equipos sin administración'); db_session.add(selected); db_session.flush()
        db_session.add(SecurityRolePermission(role_id=selected.id, permission_code='distribution_devices.create'))
    else:
        selected = db_session.scalar(select(SecurityRole).where(SecurityRole.code == role))
    account = db_session.scalar(select(Responsible).where(Responsible.username == 'security-test-superadmin'))
    account.security_role_id = selected.id; db_session.commit()
    assert api_client.get(BASE).status_code == 200
    assert api_client.get(BASE + f"/{item['id']}/preview").status_code == 200
    assert api_client.post(BASE + '/preview', json=draft(catalog)).status_code == (200 if role in ('SUPERADMIN', 'ADMIN') else 403)
    assert api_client.post(BASE, json=checked_body(item)).status_code == (409 if role in ('SUPERADMIN', 'ADMIN') else 403)
    body = checked_body(item)
    body['active'] = False
    assert api_client.patch(BASE + f"/{item['id']}", json=body).status_code == (200 if role in ('SUPERADMIN', 'ADMIN') else 403)
    if role in ('SUPERADMIN', 'ADMIN'):
        body['active'] = True
        assert api_client.patch(BASE + f"/{item['id']}", json=body).status_code == 200
    assert device(api_client, item, ticket_payload['node_id']).status_code == (403 if role == 'AUDITOR' else 201)
    api_client.headers.pop('Authorization')
    assert api_client.get(BASE).status_code == 401
    assert api_client.post(BASE, json=body).status_code == 401


def checked_body(item):
    return {key: value for key, value in item.items() if key in ('name', 'manufacturer', 'description', 'active', 'preview_token')} | {
        'groups': [{key: g[key] for key in ('nomenclature_id', 'numbering_format', 'positions', 'start', 'end')} for g in item['groups']]}


@pytest.fixture
def committed_template(concurrent_topology):
    from sqlalchemy.orm import Session
    from sqlalchemy import delete
    from ticketyn.models import PortNomenclature, DistributionDeviceTemplateGroup
    data = concurrent_topology
    with Session(data['engine']) as session:
        nomenclature = PortNomenclature(name='Race', prefix='race', formats=['N']); session.add(nomenclature); session.flush()
        item = DistributionDeviceTemplate(name='Concurrent model', groups=[DistributionDeviceTemplateGroup(
            position=0, nomenclature_id=nomenclature.id, definition={'numbering_format': 'N', 'positions': [], 'start': 0, 'end': 2})])
        session.add(item); session.commit()
        ids = item.id, nomenclature.id
    try:
        yield data, ids[0]
    finally:
        with Session(data['engine']) as session:
            session.execute(delete(DistributionDeviceTemplate).where(DistributionDeviceTemplate.id == ids[0]))
            # Generated ports are removed by the enclosing isolated topology fixture.
            session.execute(delete(DistributionPort).where(DistributionPort.nomenclature_id == ids[1]))
            session.execute(delete(PortNomenclature).where(PortNomenclature.id == ids[1])); session.commit()


from test_distribution import concurrent_topology, request_for  # noqa: F401,E402


def test_simultaneous_requests_cannot_duplicate_equipment(committed_template):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    from fastapi import HTTPException
    from ticketyn.api.device_templates import get_template
    from ticketyn.api.distribution import create_device
    from ticketyn.schemas.distribution import DeviceCreate
    data, id = committed_template
    with Session(data['engine']) as session:
        token = get_template(id, session).preview_token
    barrier = Barrier(2)
    def run():
        with Session(data['engine']) as session:
            barrier.wait(5)
            try:
                create_device(DeviceCreate(node_id=data['node'], name='Concurrent generated', template_id=id, template_token=token), session, request_for(data['actor']))
                return 201
            except HTTPException as error:
                return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: run(), range(2))) == [201, 409]
    with Session(data['engine']) as session:
        item = session.scalar(select(DistributionDevice).where(DistributionDevice.name == 'Concurrent generated'))
        assert session.scalar(select(func.count()).select_from(DistributionPort).where(DistributionPort.distribution_device_id == item.id)) == 3


def test_template_changed_while_application_waits(committed_template):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from sqlalchemy.orm import Session
    from fastapi import HTTPException
    from ticketyn.api.device_templates import get_template
    from ticketyn.api.distribution_data import distribution_write
    from ticketyn.api.distribution import create_device
    from ticketyn.schemas.distribution import DeviceCreate
    data, id = committed_template
    with Session(data['engine']) as session:
        token = get_template(id, session).preview_token
    held, attempted, release = Event(), Event(), Event()
    def edit():
        with Session(data['engine']) as session, distribution_write(session):
            item = session.get(DistributionDeviceTemplate, id)
            item.groups[0].definition = {**item.groups[0].definition, 'end': 3}
            session.flush(); held.set(); assert release.wait(5)
    def apply():
        assert held.wait(5)
        with Session(data['engine']) as session:
            attempted.set()
            try:
                create_device(DeviceCreate(node_id=data['node'], name='Stale application', template_id=id, template_token=token), session, request_for(data['actor']))
            except HTTPException as error:
                return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(edit); assert held.wait(5)
        consumer = pool.submit(apply); assert attempted.wait(5); release.set()
        writer.result(); assert consumer.result() == 409
    with Session(data['engine']) as session:
        assert session.scalar(select(DistributionDevice.id).where(DistributionDevice.name == 'Stale application')) is None


def test_catalog_changes_require_new_preview_and_disabled_template_cannot_apply(api_client, catalog, ticket_payload):
    item = create(api_client, draft(catalog))
    body = {key: catalog[key] for key in ('name', 'prefix', 'formats', 'active')}
    assert api_client.patch(f"/api/port-nomenclatures/{catalog['id']}", json={**body, 'prefix': 'GE-'}).status_code == 200
    assert device(api_client, item, ticket_payload['node_id']).status_code == 409
    refreshed = api_client.get(BASE + f"/{item['id']}/preview").json()
    assert refreshed['groups'][0]['names'] == ['GE-0', 'GE-1', 'GE-2']
    inactive = {**checked_body(refreshed), 'active': False}
    assert api_client.patch(BASE + f"/{item['id']}", json=inactive).status_code == 200
    assert device(api_client, refreshed, ticket_payload['node_id']).status_code == 422
    assert api_client.get(BASE).json() == []
    assert len(api_client.get(BASE, params={'include_inactive': True, 'limit': 1}).json()) == 1
    assert api_client.get(BASE, params={'include_inactive': True, 'offset': 1}).json() == []


def test_disabled_format_blocks_new_groups_and_application(api_client, catalog, ticket_payload):
    item = create(api_client, draft(catalog))
    body = {key: catalog[key] for key in ('name', 'prefix', 'formats', 'active')}
    assert api_client.patch(f"/api/port-nomenclatures/{catalog['id']}", json={**body, 'formats': ['X/Y']}).status_code == 200
    assert device(api_client, item, ticket_payload['node_id']).status_code == 422
    assert api_client.post(BASE + '/preview', json=draft(catalog)).status_code == 422
    old = api_client.get(BASE + f"/{item['id']}").json()
    assert old['groups'][0]['warning']
