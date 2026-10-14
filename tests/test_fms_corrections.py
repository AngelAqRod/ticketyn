from decimal import Decimal
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from ticketyn.models import ServiceType
from test_fms import operation_payload, create


def test_activation_checks_customer_circuit_without_consuming_number(api_client, operation_payload, ticket_payload):
    other = create(api_client, '/api/customers', {'name': 'Otro cliente', 'customer_code': 'OTHER'})
    response = api_client.post('/api/activations', json={**operation_payload, 'customer_id': other['id']})
    assert response.status_code == 422
    assert 'cliente seleccionado' in response.json()['detail']
    assert api_client.get('/api/activations').json() == []
    assert api_client.get('/api/settings/activation-number').json()['next_number'] == 1
    activation = create(api_client, '/api/activations', {**operation_payload, 'customer_id': ticket_payload['customer_id']})
    assert activation['reference'] == 'ACT-000001'
    # Historical consumers without client context keep working.
    assert create(api_client, '/api/activations', operation_payload)['reference'] == 'ACT-000002'
    assert 'customer_id' not in operation_payload


def test_service_types_crud_and_normalized_names(api_client, db_session):
    first = create(api_client, '/api/service-types', {'name': '  Internet  '})
    second = create(api_client, '/api/service-types', {'name': 'Transporte'})
    assert first['name'] == 'Internet'
    assert api_client.get(f"/api/service-types/{first['id']}").json() == first
    assert api_client.post('/api/service-types', json={'name': ' INTERNET '}).status_code == 409
    assert api_client.patch(f"/api/service-types/{first['id']}", json={'name': ' internet '}).status_code == 200
    assert api_client.patch(f"/api/service-types/{second['id']}", json={'name': 'INTERNET'}).status_code == 409
    assert api_client.patch(f"/api/service-types/{first['id']}", json={'name': 'Internet', 'active': False}).status_code == 200
    assert [row['id'] for row in api_client.get('/api/service-types').json()] == [second['id']]
    assert len(api_client.get('/api/service-types', params={'include_inactive': True}).json()) == 2
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(ServiceType(name=' INTERNET ')); db_session.flush()
    assert api_client.get('/api/service-types/999').status_code == 404
    assert api_client.get('/api/service-types', params={'search': 'transp'}).json()[0]['id'] == second['id']


def test_circuit_service_type_optional_and_historical(api_client, operation_payload, ticket_payload):
    id = operation_payload['circuit_id']
    original = api_client.get(f'/api/circuits/{id}').json()
    assert original['service_type_id'] is None and original['service_type'] is None
    type = create(api_client, '/api/service-types', {'name': 'Internet'})
    assert api_client.patch(f'/api/circuits/{id}', json={'service_type_id': type['id']}).status_code == 200
    activation = create(api_client, '/api/activations', operation_payload)
    assert activation['circuit']['description'] == original['description']
    assert activation['circuit']['service_type']['name'] == 'Internet'
    api_client.patch(f"/api/service-types/{type['id']}", json={'active': False})
    updated = api_client.patch(f'/api/circuits/{id}', json={'description': 'Corregido', 'service_type_id': type['id']})
    assert updated.status_code == 200 and updated.json()['service_type']['active'] is False
    assert api_client.get(f'/api/circuits/{id}/operational-detail').json()['circuit']['service_type']['name'] == 'Internet'
    assert api_client.get('/api/activations').json()[0]['circuit']['service_type']['name'] == 'Internet'
    body = {'node_id': ticket_payload['node_id'], 'sector_id': ticket_payload['sector_id'], 'customer_id': ticket_payload['customer_id'], 'circuit_code': 'NEW', 'description': 'Nuevo', 'service_type_id': type['id']}
    assert api_client.post('/api/circuits', json=body).status_code == 422
    assert api_client.post('/api/circuits', json={'node_id': ticket_payload['node_id'], 'sector_id': ticket_payload['sector_id'], **body, 'service_type_id': 999}).status_code == 404
    assert api_client.patch(f'/api/circuits/{id}', json={'service_type_id': None}).status_code == 200
    assert api_client.patch(f'/api/circuits/{id}', json={'service_type_id': type['id']}).status_code == 422
    # Service belongs to the circuit, never to the activation.
    assert api_client.post('/api/activations', json={**operation_payload, 'service_type_id': type['id']}).status_code == 422
    ticket = create(api_client, '/api/tickets', ticket_payload)
    assert ticket['circuit_id'] == id
    assert api_client.delete(f'/api/circuits/{id}').status_code == 409


@pytest.mark.parametrize('unit,value', [('Mbps', '250.125'), ('Gbps', '2.5')])
def test_capacity_suggestion_endpoint_uses_current_then_initial(api_client, operation_payload, unit, value):
    id = operation_payload['circuit_id']
    path = f'/api/circuits/{id}/operational-detail'
    assert api_client.get(path).json()['current_capacity'] is None
    patch = api_client.patch(f'/api/circuits/{id}', json={'initial_capacity': value, 'initial_capacity_unit': unit})
    assert patch.status_code == 200
    assert Decimal(patch.json()['initial_capacity']) == Decimal(value)
    assert Decimal(api_client.get(path).json()['current_capacity']) == Decimal(value)
    assert api_client.get(path).json()['current_capacity_unit'] == unit
    create(api_client, '/api/capacity-changes', {**operation_payload, 'operation_type': 'INCREASE', 'new_capacity': '5', 'new_unit': 'Gbps'})
    api_client.patch(f'/api/circuits/{id}', json={'initial_capacity': '1', 'initial_capacity_unit': 'Mbps'})
    assert Decimal(api_client.get(path).json()['current_capacity']) == 5
    assert api_client.get(path).json()['current_capacity_unit'] == 'Gbps'


def test_administrable_deactivation_reason_remains_visible_in_history(api_client, operation_payload):
    reason = create(api_client, '/api/deactivation-reasons', {'name': 'Otro motivo definido por NOC', 'description': 'No predefinido'})
    create(api_client, '/api/circuit-lifecycle', {**operation_payload, 'operation_type': 'DEACTIVATE', 'reason_id': reason['id']})
    api_client.patch(f"/api/deactivation-reasons/{reason['id']}", json={'name': 'Motivo corregido', 'active': False})
    assert api_client.get('/api/deactivation-reasons').json() == []
    assert api_client.get('/api/circuit-lifecycle').json()[0]['reason']['name'] == 'Motivo corregido'
    assert api_client.post('/api/circuit-lifecycle', json={**operation_payload, 'operation_type': 'DEACTIVATE', 'reason_id': reason['id']}).status_code == 422
