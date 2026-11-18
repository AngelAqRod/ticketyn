import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from ticketyn.models.installation_orders import InstallationOrder

BASE = '/api/installation-orders'
WHEN = '2026-10-28T12:00:00-06:00'


def normal(tp, **extra):
    return dict(order_type='NORMAL', customer_id=tp['customer_id'], circuit_id=tp['circuit_id'], requested_at=WHEN, **extra)


@pytest.fixture
def service_id(api_client):
    return api_client.post('/api/service-types', json={'name': 'Internet dedicado'}).json()['id']


def extraordinary(tp, service_id, **extra):
    values = dict(order_type='EXTRAORDINARY', customer_id=tp['customer_id'], description='Instalación en predio sin circuito',
                  service_type_id=service_id, node_id=tp['node_id'], sector_id=tp['sector_id'], requested_at=WHEN)
    return {**values, **extra}


def legacy_order(db_session, tp):
    """Order created before modalities existed: no type, no circuit, free-text service and location."""
    from ticketyn.models import Responsible
    author = db_session.scalar(select(Responsible.id).limit(1))
    order = InstallationOrder(reference='OI-LEGACY', customer_id=tp['customer_id'], service='Internet', location='Oficina', requested_at='2026-10-28T12:00:00-06:00', created_by=author)
    db_session.add(order)
    db_session.commit()
    return order


def test_normal_order_requires_a_circuit_of_the_customer(api_client, ticket_payload):
    assert api_client.post(BASE, json={}).status_code == 422
    missing = {k: v for k, v in normal(ticket_payload).items() if k != 'circuit_id'}
    assert api_client.post(BASE, json=missing).status_code == 422
    assert api_client.post(BASE, json={**normal(ticket_payload), 'description': 'no aplica'}).status_code == 422
    other = api_client.post('/api/customers', json={'customer_code': 'OTHER', 'name': 'Other customer'}).json()
    assert api_client.post(BASE, json={**normal(ticket_payload), 'customer_id': other['id']}).status_code == 409
    response = api_client.post(BASE, json=normal(ticket_payload))
    assert response.status_code == 201, response.text
    order = response.json()
    assert order['order_type'] == 'NORMAL' and order['reference'].startswith('OI-') and order['circuit']['id'] == ticket_payload['circuit_id']
    assert order['author']['id'] and order['service'] is None and order['location'] is None
    assert [e['detail'] for e in order['events'] if e['action'] == 'CREATE'] == [{'order_type': 'NORMAL'}]


def test_circuit_lists_are_filtered_by_customer(api_client, ticket_payload):
    other = api_client.post('/api/customers', json={'customer_code': 'OTHER', 'name': 'Other customer'}).json()
    assert [c['id'] for c in api_client.get('/api/circuits', params={'customer_id': ticket_payload['customer_id']}).json()] == [ticket_payload['circuit_id']]
    assert api_client.get('/api/circuits', params={'customer_id': other['id']}).json() == []


def test_normal_order_reads_technical_data_from_the_circuit(api_client, ticket_payload, service_id, numbered_port):
    c = api_client
    device = c.post('/api/distribution-devices', json={'node_id': ticket_payload['node_id'], 'name': 'CORE A'}).json()
    port = numbered_port(device['id'])
    model = c.post('/api/cpe-models', json={'name': 'CPE X'}).json()
    full = c.post('/api/circuits', json={'customer_id': ticket_payload['customer_id'], 'node_id': ticket_payload['node_id'], 'sector_id': ticket_payload['sector_id'],
                                         'circuit_code': 'FULL', 'description': 'completo', 'service_type_id': service_id, 'cpe_model_id': model['id'],
                                         'distribution_device_id': device['id'], 'distribution_port_id': port['id']})
    assert full.status_code == 201, full.text
    order = c.post(BASE, json=normal({**ticket_payload, 'circuit_id': full.json()['id']})).json()
    technical = order['technical']
    assert technical['service_type']['name'] == 'Internet dedicado' and technical['node']['id'] == ticket_payload['node_id']
    assert technical['sector']['id'] == ticket_payload['sector_id'] and technical['device']['name'] == 'CORE A'
    assert technical['port']['id'] == port['id'] and technical['cpe']['name'] == 'CPE X'
    # The circuit stays the single source: editing it is reflected without touching the order.
    c.patch(f"/api/circuits/{full.json()['id']}", json={'cpe_model_id': None})
    assert c.get(f"{BASE}/{order['id']}").json()['technical']['cpe'] is None


def test_missing_technical_data_is_reported_as_unavailable_not_invented(api_client, ticket_payload):
    order = api_client.post(BASE, json=normal(ticket_payload)).json()
    technical = order['technical']
    assert technical['service_type'] is None and technical['device'] is None and technical['port'] is None and technical['cpe'] is None
    assert technical['node']['id'] == ticket_payload['node_id']


def test_second_normal_order_for_a_circuit_is_rejected_with_the_existing_reference(api_client, ticket_payload):
    first = api_client.post(BASE, json=normal(ticket_payload)).json()
    second = api_client.post(BASE, json=normal(ticket_payload))
    assert second.status_code == 409 and first['reference'] in second.json()['detail']
    assert api_client.get(BASE, params={'circuit_id': ticket_payload['circuit_id']}).json()[0]['id'] == first['id']


def test_extraordinary_order_needs_no_circuit_device_port_or_cpe(api_client, ticket_payload, service_id):
    response = api_client.post(BASE, json=extraordinary(ticket_payload, service_id))
    assert response.status_code == 201, response.text
    order = response.json()
    assert order['order_type'] == 'EXTRAORDINARY' and order['circuit'] is None and order['description'].startswith('Instalación')
    technical = order['technical']
    assert technical['service_type']['id'] == service_id and technical['node']['id'] == ticket_payload['node_id'] and technical['sector']['id'] == ticket_payload['sector_id']
    assert technical['device'] is None and technical['port'] is None and technical['cpe'] is None
    # Several extraordinary orders may coexist with the same customer and no circuit.
    assert api_client.post(BASE, json=extraordinary(ticket_payload, service_id)).status_code == 201


@pytest.mark.parametrize('missing', ['description', 'service_type_id', 'node_id', 'sector_id'])
def test_extraordinary_required_fields(api_client, ticket_payload, service_id, missing):
    body = {k: v for k, v in extraordinary(ticket_payload, service_id).items() if k != missing}
    assert api_client.post(BASE, json=body).status_code == 422
    assert api_client.post(BASE, json={**body, missing: None}).status_code == 422


def test_extraordinary_validates_catalog_references_and_rejects_circuit(api_client, ticket_payload, service_id):
    for key in ('service_type_id', 'node_id', 'sector_id'):
        assert api_client.post(BASE, json=extraordinary(ticket_payload, service_id, **{key: 2147000100})).status_code == 404
    assert api_client.post(BASE, json=extraordinary(ticket_payload, service_id, circuit_id=ticket_payload['circuit_id'])).status_code == 422
    api_client.patch(f'/api/service-types/{service_id}', json={'active': False})
    assert api_client.post(BASE, json=extraordinary(ticket_payload, service_id)).status_code == 422
    assert api_client.post(BASE, json={**extraordinary(ticket_payload, service_id), 'service': 'texto libre'}).status_code == 422


def test_type_is_permanent_in_api_and_database(api_client, db_session, ticket_payload, service_id):
    extra = api_client.post(BASE, json=extraordinary(ticket_payload, service_id)).json()
    norm = api_client.post(BASE, json=normal(ticket_payload)).json()
    for order, target in ((extra, 'NORMAL'), (norm, 'EXTRAORDINARY')):
        assert api_client.patch(f"{BASE}/{order['id']}", json={'order_type': target}).status_code == 422
        assert api_client.patch(f"{BASE}/{order['id']}", json={'circuit_id': ticket_payload['circuit_id']}).status_code == 422
    # Circuit operations never reclassify typed orders.
    assert api_client.put(f"{BASE}/{extra['id']}/circuit", json={'circuit_id': ticket_payload['circuit_id']}).status_code == 409
    assert api_client.delete(f"{BASE}/{norm['id']}/circuit").status_code == 409
    assert api_client.get(f"{BASE}/{norm['id']}").json()['circuit']['id'] == ticket_payload['circuit_id']
    # Type-specific fields do not apply to the other modality.
    assert api_client.patch(f"{BASE}/{norm['id']}", json={'description': 'x'}).status_code == 422
    assert api_client.patch(f"{BASE}/{extra['id']}", json={'description': 'Descripción corregida'}).status_code == 200
    assert api_client.patch(f"{BASE}/{extra['id']}", json={'description': None}).status_code == 422
    assert [api_client.get(f"{BASE}/{o['id']}").json()['order_type'] for o in (extra, norm)] == ['EXTRAORDINARY', 'NORMAL']


def test_database_rejects_inconsistent_shapes(db_session, ticket_payload, api_client, service_id):
    order = api_client.post(BASE, json=extraordinary(ticket_payload, service_id)).json()
    for statement in ("UPDATE installation_orders SET circuit_id = :circuit WHERE id = :id",
                      "UPDATE installation_orders SET description = NULL WHERE id = :id",
                      "UPDATE installation_orders SET order_type = 'OTHER' WHERE id = :id"):
        with pytest.raises(IntegrityError):
            with db_session.begin_nested():
                db_session.execute(text(statement), {'circuit': ticket_payload['circuit_id'], 'id': order['id']})


def test_list_shows_and_filters_modalities(api_client, db_session, ticket_payload, service_id):
    api_client.post(BASE, json=normal(ticket_payload))
    api_client.post(BASE, json=extraordinary(ticket_payload, service_id))
    legacy_order(db_session, ticket_payload)
    listed = api_client.get(BASE)
    assert listed.headers['X-Total-Count'] == '3' and {o['order_type'] for o in listed.json()} == {'NORMAL', 'EXTRAORDINARY', None}
    for kind, expected in (('NORMAL', 1), ('EXTRAORDINARY', 1), ('UNCLASSIFIED', 1)):
        assert api_client.get(BASE, params={'order_type': kind}).headers['X-Total-Count'] == str(expected)
    assert api_client.get(BASE, params={'order_type': 'BOGUS'}).status_code == 422
    assert api_client.get(BASE, params={'q': 'predio sin circuito'}).headers['X-Total-Count'] == '1'


def test_legacy_unclassified_order_keeps_working_and_is_classified_only_by_linking(api_client, db_session, ticket_payload):
    order = legacy_order(db_session, ticket_payload)
    base = f'{BASE}/{order.id}'
    detail = api_client.get(base).json()
    assert detail['order_type'] is None and detail['technical'] is None and detail['service'] == 'Internet' and detail['location'] == 'Oficina'
    assert api_client.patch(base, json={'description': 'x'}).status_code == 422
    assert api_client.patch(base, json={'notes': 'nota'}).status_code == 200
    assert api_client.get(base).json()['order_type'] is None
    assert api_client.put(base + '/circuit', json={'circuit_id': ticket_payload['circuit_id']}).status_code == 200
    linked = api_client.get(base).json()
    assert linked['order_type'] == 'NORMAL' and linked['technical']['node']['id'] == ticket_payload['node_id'] and linked['service'] == 'Internet'
    assert api_client.delete(base + '/circuit').status_code == 409


def test_legacy_circuit_creation_is_atomic_and_preserves_existing_behavior(api_client, ticket_payload, db_session):
    from ticketyn.models import Circuit
    from ticketyn.models.fms import Activation
    order = legacy_order(db_session, ticket_payload)
    circuit = dict(customer_id=ticket_payload['customer_id'], sector_id=ticket_payload['sector_id'], node_id=ticket_payload['node_id'], circuit_code='ORDER-CIRCUIT', description='Installation')
    before = db_session.scalar(select(func.count()).select_from(Circuit))
    assert api_client.post(f'{BASE}/{order.id}/circuit', json={**circuit, 'node_id': 2147483000}).status_code == 404
    assert db_session.scalar(select(func.count()).select_from(Circuit)) == before
    response = api_client.post(f'{BASE}/{order.id}/circuit', json=circuit)
    assert response.status_code == 201, response.text
    assert response.json()['circuit']['circuit_code'] == 'ORDER-CIRCUIT' and response.json()['order_type'] == 'NORMAL'
    assert db_session.scalar(select(func.count()).select_from(Activation)) == 0
    assert api_client.post(f'{BASE}/{order.id}/circuit', json={**circuit, 'circuit_code': 'NO-SECOND'}).status_code == 409
    assert db_session.scalar(select(func.count()).select_from(Circuit)) == before + 1


def test_customer_consistency(api_client, ticket_payload, service_id):
    order = api_client.post(BASE, json=normal(ticket_payload)).json()
    other = api_client.post('/api/customers', json={'customer_code': 'OTHER', 'name': 'Other customer'}).json()
    assert api_client.patch(f"{BASE}/{order['id']}", json={'customer_id': other['id']}).status_code == 409
    assert api_client.patch(f"{BASE}/{order['id']}", json={'requested_at': None}).status_code == 422
    extra = api_client.post(BASE, json=extraordinary(ticket_payload, service_id)).json()
    assert api_client.patch(f"{BASE}/{extra['id']}", json={'customer_id': other['id']}).status_code == 200


def test_documents_and_events_survive_edits(api_client, ticket_payload, tmp_path, monkeypatch):
    monkeypatch.setenv('INSTALLATION_STORAGE_DIR', str(tmp_path / 'files'))
    order = api_client.post(BASE, json=normal(ticket_payload)).json()
    assert api_client.post(f"{BASE}/{order['id']}/documents", params={'filename': 'orden.pdf'}, content=b'%PDF-1.7\n').status_code == 201
    api_client.patch(f"{BASE}/{order['id']}", json={'notes': 'actualizada'})
    detail = api_client.get(f"{BASE}/{order['id']}").json()
    assert len(detail['documents']) == 1 and {'CREATE', 'EDIT'} <= {e['action'] for e in detail['events']}
