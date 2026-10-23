"""Nomenclature rules, atomic batches and historical compatibility in ephemeral PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ticketyn.api import port_nomenclatures as api
from ticketyn.models import DistributionAudit, DistributionPort, PortNomenclature, Responsible
from ticketyn.models.security import SecurityRole
from ticketyn.schemas.port_nomenclature import PortGeneration
from test_distribution import topology, concurrent_topology, request_for  # noqa: F401


@pytest.fixture
def catalog(api_client):
    response = api_client.post('/api/port-nomenclatures', json={
        'name': 'Interfaces ópticas', 'prefix': 'SFP+', 'formats': ['N', 'X/Y', 'X/Y/Z', 'W/X/Y/Z']})
    assert response.status_code == 201, response.text
    return response.json()


def generation(topology, catalog, **changes):
    return {'distribution_device_id': topology[0]['id'], 'nomenclature_id': catalog['id'],
            'numbering_format': 'N', 'positions': [], 'start': 0, 'end': 3, 'mode': 'complete', **changes}


def preview(client, payload):
    response = client.post('/api/distribution-ports/preview', json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def confirm(client, payload, path='batch'):
    checked = preview(client, payload)
    return client.post('/api/distribution-ports' + ('/batch' if path == 'batch' else ''),
                       json={**payload, 'preview_token': checked['preview_token']})


def test_catalog_lifecycle_prefix_guard_and_history(api_client, topology, catalog):
    body = {key: catalog[key] for key in ('name', 'prefix', 'formats', 'active')}
    assert api_client.post('/api/port-nomenclatures', json={**body, 'prefix': 'sfp+'}).status_code == 409
    updated = api_client.patch(f"/api/port-nomenclatures/{catalog['id']}", json={**body, 'name': 'Nuevo nombre'})
    assert updated.status_code == 200 and updated.json()['name'] == 'Nuevo nombre'
    payload = generation(topology, catalog, start=6, end=6)
    port = confirm(api_client, payload, 'single').json()
    assert port['name'] == 'SFP+6'
    assert api_client.patch(f"/api/port-nomenclatures/{catalog['id']}", json={**body, 'prefix': 'otra'}).status_code == 409
    assert api_client.delete(f"/api/port-nomenclatures/{catalog['id']}").status_code == 409
    assert api_client.patch(f"/api/port-nomenclatures/{catalog['id']}", json={**body, 'active': False, 'formats': []}).status_code == 200
    assert api_client.get('/api/port-nomenclatures').json() == []
    assert api_client.post('/api/distribution-ports/preview', json=payload).status_code == 422
    assert api_client.patch(f"/api/distribution-ports/{port['id']}", json={'description': 'Se conserva'}).status_code == 200
    assert api_client.get(f"/api/distribution-ports/{port['id']}").json()['name'] == 'SFP+6'
    assert api_client.patch(f"/api/port-nomenclatures/{catalog['id']}", json=body).status_code == 200


@pytest.mark.parametrize('prefix,formats', [('', ['N']), ('\n', ['N']), ('X', []), ('X', ['N', 'N']), ('X', ['eval(n)'])])
def test_invalid_catalog(api_client, prefix, formats):
    assert api_client.post('/api/port-nomenclatures', json={'name': 'Test', 'prefix': prefix, 'formats': formats}).status_code == 422


@pytest.mark.parametrize('fmt,positions,start,end,expected', [
    ('N', [], 0, 1, ['SFP+0', 'SFP+1']),
    ('X/Y', [0], 7, 8, ['SFP+0/7', 'SFP+0/8']),
    ('X/Y/Z', [5, 5], 5, 6, ['SFP+5/5/5', 'SFP+5/5/6']),
    ('W/X/Y/Z', [0, 2, 0], 8, 9, ['SFP+0/2/0/8', 'SFP+0/2/0/9']),
])
def test_generator(fmt, positions, start, end, expected):
    assert api.generated_names('SFP+', fmt, positions, start, end) == expected


@pytest.mark.parametrize('prefix', ['GE-', 'sfp', 'Ethernet', 'ge-', 'Gi', 'sfp+/', 'Á+'])
def test_exact_prefix(prefix):
    assert api.generated_names(prefix, 'N', [], 0, 1) == [prefix + '0', prefix + '1']


@pytest.mark.parametrize('changes', [{'end': 256}, {'start': -1}, {'start': True}, {'end': 1.5}, {'start': 4, 'end': 3},
                                   {'positions': [0]}, {'numbering_format': 'X/Y', 'positions': [-1]}])
def test_invalid_generation_rejected_before_execution(api_client, topology, catalog, changes):
    payload = generation(topology, catalog, **changes)
    for path in ('/api/distribution-ports/preview', '/api/distribution-ports/batch'):
        assert api_client.post(path, json=payload).status_code == 422


def test_256_limit_and_atomic_conflicts(api_client, topology, catalog, db_session):
    payload = generation(topology, catalog, start=10, end=265)
    assert preview(api_client, payload)['total'] == 256
    created = confirm(api_client, payload)
    assert created.status_code == 200 and len(created.json()['created']) == 256
    before = db_session.scalar(select(func.count()).select_from(DistributionPort))
    conflict = generation(topology, catalog, start=9, end=11)
    checked = preview(api_client, conflict)
    assert checked['blocked'] and checked['existing_count'] == 2
    assert confirm(api_client, conflict).status_code == 409
    assert db_session.scalar(select(func.count()).select_from(DistributionPort)) == before


def test_missing_keeps_legacy_case_inactive_and_associations(api_client, topology, catalog, ticket_payload, db_session):
    device, _, historical, _ = topology
    db_session.get(DistributionPort, topology[3]['id']).active = False
    db_session.commit()
    assert api_client.patch(f"/api/circuits/{ticket_payload['circuit_id']}", json={
        'distribution_device_id': device['id'], 'distribution_port_id': historical['id']}).status_code == 200
    before = dict(db_session.execute(select(DistributionPort.__table__).where(DistributionPort.id == historical['id'])).mappings().one())
    payload = generation(topology, catalog, mode='missing')
    checked = preview(api_client, payload)
    assert checked['total'] == 4 and checked['existing_count'] == 2 and checked['create_count'] == 2
    assert [row['name'] for row in checked['names'] if row['existing']] == ['SFP+1', 'SFP+2']
    response = confirm(api_client, payload)
    assert response.status_code == 200
    assert [port['name'] for port in response.json()['created']] == ['SFP+0', 'SFP+3']
    after = dict(db_session.execute(select(DistributionPort.__table__).where(DistributionPort.id == historical['id'])).mappings().one())
    assert after == before and after['nomenclature_id'] is None
    assert api_client.get(f"/api/circuits/{ticket_payload['circuit_id']}").json()['distribution_port_id'] == historical['id']
    audit_count = db_session.scalar(select(func.count()).select_from(DistributionAudit))
    assert confirm(api_client, payload).json()['created'] == []
    assert db_session.scalar(select(func.count()).select_from(DistributionAudit)) == audit_count


def test_single_requires_generator_preview_and_does_not_accept_raw_names(api_client, topology, catalog):
    assert api_client.post('/api/distribution-ports', json={'distribution_device_id': topology[0]['id'], 'name': 'bypass'}).status_code == 422
    payload = generation(topology, catalog, start=8, end=8)
    assert api_client.post('/api/distribution-ports', json=payload).status_code == 409
    created = confirm(api_client, payload, 'single')
    assert created.status_code == 201 and created.json()['number_components'] == [8]
    assert created.json()['nomenclature_id'] == catalog['id']
    assert confirm(api_client, payload, 'single').status_code == 409
    assert api_client.post('/api/distribution-ports', json=generation(topology, catalog)).status_code == 422


def test_stale_preview_is_rejected_and_requires_new_confirmation(api_client, topology, catalog):
    payload = generation(topology, catalog, start=10, end=12, mode='missing')
    checked = preview(api_client, payload)
    assert confirm(api_client, {**payload, 'end': 10}, 'single').status_code == 201
    stale = api_client.post('/api/distribution-ports/batch', json={**payload, 'preview_token': checked['preview_token']})
    assert stale.status_code == 409
    assert preview(api_client, payload)['create_count'] == 2
    assert len(confirm(api_client, payload).json()['created']) == 2


@pytest.mark.parametrize('failure', ['audit', 'unique'])
def test_batch_rolls_back_on_failure(api_client, topology, catalog, db_session, monkeypatch, failure):
    before = db_session.scalar(select(func.count()).select_from(DistributionPort))
    audit_count = db_session.scalar(select(func.count()).select_from(DistributionAudit))
    payload = generation(topology, catalog, start=10, end=12)
    original = api.record
    def fail_second(session, actor, item, action, *args, **kwargs):
        if item.name == 'SFP+11':
            if failure == 'unique':
                session.add(DistributionPort(distribution_device_id=item.distribution_device_id, name='sfp+10'))
                session.flush()
            raise SQLAlchemyError('private database diagnostic')
        return original(session, actor, item, action, *args, **kwargs)
    monkeypatch.setattr(api, 'record', fail_second)
    assert confirm(api_client, payload).status_code == (503 if failure == 'audit' else 409)
    assert db_session.scalar(select(func.count()).select_from(DistributionPort)) == before
    assert db_session.scalar(select(func.count()).select_from(DistributionAudit)) == audit_count


def test_direct_db_uniqueness_and_partial_classification(db_session, topology, catalog):
    for values in ({'name': 'SFP+1'}, {'name': 'new', 'nomenclature_id': catalog['id']}):
        with pytest.raises(IntegrityError), db_session.begin_nested():
            db_session.add(DistributionPort(distribution_device_id=topology[0]['id'], **values)); db_session.flush()


def test_explicit_classification_never_renames_legacy(api_client, topology, catalog):
    port = topology[2]
    body = {'nomenclature_id': catalog['id'], 'numbering_format': 'N', 'number_components': [1]}
    response = api_client.patch(f"/api/distribution-ports/{port['id']}", json=body)
    assert response.status_code == 200 and response.json()['name'] == 'sfp+1'
    assert api_client.patch(f"/api/distribution-ports/{port['id']}", json={**body, 'number_components': [7]}).status_code == 422
    assert api_client.patch(f"/api/distribution-ports/{port['id']}", json={'name': 'arbitrary'}).status_code == 422


@pytest.mark.parametrize('role,admin,create', [('SUPERADMIN', True, True), ('ADMIN', True, True), ('OPERATOR', False, True), ('AUDITOR', False, False)])
def test_permissions(api_client, topology, catalog, db_session, role, admin, create):
    account = db_session.scalar(select(Responsible).where(Responsible.username == 'security-test-superadmin'))
    account.security_role_id = db_session.scalar(select(SecurityRole.id).where(SecurityRole.code == role)); db_session.commit()
    assert api_client.get('/api/port-nomenclatures').status_code == 200
    body = {'name': 'Renamed', 'prefix': 'SFP+', 'formats': ['N'], 'active': True}
    assert api_client.patch(f"/api/port-nomenclatures/{catalog['id']}", json=body).status_code == (200 if admin else 403)
    assert api_client.post('/api/port-nomenclatures', json={**body, 'prefix': 'New'}).status_code == (201 if admin else 403)
    payload = generation(topology, catalog, start=10, end=10)
    assert api_client.post('/api/distribution-ports/preview', json=payload).status_code == (200 if create else 403)
    assert api_client.post('/api/distribution-ports/batch', json=payload).status_code == (409 if create else 403)


@pytest.mark.parametrize('mode', ['complete', 'missing'])
def test_concurrent_ranges_never_partially_commit(concurrent_topology, mode):
    data = concurrent_topology
    with Session(data['engine']) as session:
        catalog = PortNomenclature(name='Concurrent', prefix='race+', formats=['N'])
        session.add(catalog); session.commit(); catalog_id = catalog.id
    payload = PortGeneration(distribution_device_id=data['device'], nomenclature_id=catalog_id,
                             numbering_format='N', start=0, end=20, mode=mode)
    with Session(data['engine']) as session:
        checked = api.preview(session, payload)
    barrier = Barrier(2)
    def create():
        with Session(data['engine']) as session:
            barrier.wait(5)
            try:
                return api.create_ports(payload.model_copy(update={'preview_token': checked['preview_token']}), session, request_for(data['actor']))
            except HTTPException as error:
                return error.status_code
    try:
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: create(), range(2)))
        assert sum(isinstance(result, dict) for result in results) == 1
        assert 409 in results
        with Session(data['engine']) as session:
            assert session.scalar(select(func.count()).select_from(DistributionPort).where(DistributionPort.nomenclature_id == catalog_id)) == 21
            fresh = api.preview(session, payload)
        assert fresh['existing_count'] == 21
    finally:
        with Session(data['engine']) as session:
            session.query(DistributionPort).filter_by(nomenclature_id=catalog_id).delete()
            session.query(PortNomenclature).filter_by(id=catalog_id).delete(); session.commit()
