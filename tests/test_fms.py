from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import pytest
from test_ticket_concurrency import concurrent_database
from ticketyn.api.fms_data import create_operation
from ticketyn.models import Circuit, Ticket, TicketNumberConfig, Responsible
from ticketyn.models.fms import Activation, ActivationNumberConfig, CapacityChange


@pytest.fixture
def operation_payload(api_client, ticket_payload):
    person = api_client.post('/api/responsibles', json={'name': 'Operador FMS'}).json()
    return {'circuit_id': ticket_payload['circuit_id'], 'responsible_id': person['id'], 'effective_at': '2020-01-01T12:00:00-06:00'}


def create(api_client, path, payload):
    response = api_client.post(path, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_initial_capacity_and_history_are_independent(api_client, operation_payload):
    id = operation_payload['circuit_id']
    detail = lambda: api_client.get(f'/api/circuits/{id}/operational-detail').json()
    assert detail()['current_capacity'] is None
    assert detail()['initial_activation'] is None
    patch = lambda body: api_client.patch(f'/api/circuits/{id}', json=body)
    assert patch({'initial_capacity': '200', 'initial_capacity_unit': 'Mbps'}).status_code == 200
    assert Decimal(detail()['current_capacity']) == 200
    row = create(api_client, '/api/capacity-changes', {**operation_payload, 'operation_type': 'INCREASE', 'previous_capacity': '500', 'previous_unit': 'Mbps', 'new_capacity': '1', 'new_unit': 'Gbps'})
    assert patch({'initial_capacity': '250', 'initial_capacity_unit': 'Mbps'}).status_code == 200
    assert detail()['current_capacity_unit'] == 'Gbps'
    assert Decimal(detail()['current_capacity']) == 1
    persisted = api_client.get('/api/capacity-changes').json()[0]
    assert {k: v for k, v in persisted.items() if k != 'circuit'} == {k: v for k, v in row.items() if k != 'circuit'}
    # Deterministic tie: later ID wins; future operations do not become current yet.
    create(api_client, '/api/capacity-changes', {**operation_payload, 'operation_type': 'DECREASE', 'previous_capacity': '1', 'previous_unit': 'Gbps', 'new_capacity': '750', 'new_unit': 'Mbps'})
    create(api_client, '/api/capacity-changes', {**operation_payload, 'effective_at': '2099-01-01T00:00:00Z', 'operation_type': 'INCREASE', 'new_capacity': '10', 'new_unit': 'Gbps'})
    assert Decimal(detail()['current_capacity']) == 750
    assert patch({'initial_capacity': None, 'initial_capacity_unit': None}).status_code == 200
    assert Decimal(detail()['current_capacity']) == 750


@pytest.mark.parametrize('body', [{'initial_capacity': 0, 'initial_capacity_unit': 'Mbps'}, {'initial_capacity': 1}, {'initial_capacity_unit': 'Gbps'}, {'initial_capacity': 1, 'initial_capacity_unit': 'Kbps'}, {'initial_capacity': 'NaN', 'initial_capacity_unit': 'Mbps'}])
def test_invalid_initial_capacity(api_client, ticket_payload, body):
    response = api_client.patch(f"/api/circuits/{ticket_payload['circuit_id']}", json=body)
    assert response.status_code == 422


@pytest.mark.parametrize('type,old,old_unit,new,new_unit,status', [
    ('INCREASE', None, None, '500', 'Mbps', 201),
    ('INCREASE', '500', 'Mbps', '1', 'Gbps', 201),
    ('DECREASE', '1', 'Gbps', '500', 'Mbps', 201),
    ('INCREASE', '1000', 'Mbps', '1', 'Gbps', 422),
    ('DECREASE', '1', 'Gbps', '1000', 'Mbps', 422),
    ('DECREASE', None, None, '500', 'Mbps', 422),
    ('INCREASE', None, 'Mbps', '500', 'Mbps', 422),
    ('INCREASE', '1', 'Gbps', '500', 'Mbps', 422),
    ('DECREASE', '500', 'Mbps', '1', 'Gbps', 422),
])
def test_capacity_validation(api_client, operation_payload, type, old, old_unit, new, new_unit, status):
    response = api_client.post('/api/capacity-changes', json={**operation_payload, 'operation_type': type, 'previous_capacity': old, 'previous_unit': old_unit, 'new_capacity': new, 'new_unit': new_unit})
    assert response.status_code == status, response.text


def test_activation_numbering_and_optional_interventions(api_client, operation_payload, ticket_payload, db_session):
    preview = api_client.get('/api/settings/activation-number').json()
    assert preview['next_number'] == 1 and preview['prefix'] == 'ACT' and preview['padding'] == 6
    before = api_client.get('/api/settings/ticket-number').json()
    first = create(api_client, '/api/activations', operation_payload)
    second = create(api_client, '/api/activations', {**operation_payload, 'effective_at': '2019-01-01T12:00:00Z'})
    assert first['reference'] == 'ACT-000001' and second['reference'] == 'ACT-000002'
    assert api_client.get('/api/settings/ticket-number').json() == before
    assert db_session.scalar(select(Ticket.id)) is None
    assert api_client.get(f"/api/activations/{first['id']}/interventions").json() == []
    for at, content in [('2020-01-02T12:00:00Z', 'Segunda'), ('2019-01-02T12:00:00Z', 'Primera'), ('2019-01-02T12:00:00Z', 'Primera bis')]:
        create(api_client, f"/api/activations/{first['id']}/interventions", {'responsible_id': operation_payload['responsible_id'], 'occurred_at': at, 'content': content})
    assert [row['content'] for row in api_client.get(f"/api/activations/{first['id']}/interventions").json()] == ['Primera', 'Primera bis', 'Segunda']
    assert api_client.get(f"/api/circuits/{operation_payload['circuit_id']}/operational-detail").json()['initial_activation']['id'] == second['id']
    assert api_client.patch('/api/settings/activation-number', json={'next_number': 1}).status_code == 409
    assert api_client.patch('/api/settings/activation-number', json={'prefix': 'NEW', 'padding': 3}).status_code == 200
    assert create(api_client, '/api/activations', operation_payload)['reference'] == 'NEW-003'
    assert api_client.get(f"/api/activations/{first['id']}").json()['reference'] == 'ACT-000001'
    create(api_client, '/api/tickets', ticket_payload)
    assert api_client.get('/api/settings/ticket-number').json()['next_number'] == before['next_number'] + 1


def test_lifecycle_repetition_preserves_tickets_and_administrative_state(api_client, operation_payload, ticket_payload):
    ticket = create(api_client, '/api/tickets', ticket_payload)
    reason = create(api_client, '/api/deactivation-reasons', {'name': 'Falta de pago'})
    for type in ['DEACTIVATE', 'REACTIVATE', 'DEACTIVATE', 'REACTIVATE']:
        create(api_client, '/api/circuit-lifecycle', {**operation_payload, 'operation_type': type, **({'reason_id': reason['id']} if type == 'DEACTIVATE' else {})})
    assert api_client.patch(f"/api/deactivation-reasons/{reason['id']}", json={'active': False}).status_code == 200
    assert api_client.get('/api/deactivation-reasons').json() == []
    assert len(api_client.get('/api/circuit-lifecycle').json()) == 4
    assert api_client.get('/api/circuit-lifecycle', params={'operation_type': 'DEACTIVATE'}).json()[0]['reason']['name'] == 'Falta de pago'
    assert api_client.post('/api/circuit-lifecycle', json={**operation_payload, 'operation_type': 'DEACTIVATE', 'reason_id': reason['id']}).status_code == 422
    assert api_client.get(f"/api/circuits/{operation_payload['circuit_id']}").json()['active'] is True
    assert api_client.get(f"/api/tickets/{ticket['id']}").json() == ticket
    assert api_client.delete(f"/api/circuits/{operation_payload['circuit_id']}").status_code == 409


@pytest.mark.parametrize('path,extra', [('/api/activations', {}), ('/api/capacity-changes', {'operation_type': 'INCREASE', 'new_capacity': '1', 'new_unit': 'Gbps'}), ('/api/circuit-lifecycle', {'operation_type': 'REACTIVATE'})])
def test_fms_prevents_circuit_deletion_even_without_tickets(api_client, operation_payload, path, extra):
    create(api_client, path, {**operation_payload, **extra})
    assert api_client.delete(f"/api/circuits/{operation_payload['circuit_id']}").status_code == 409


def test_listing_filters_and_pagination(api_client, operation_payload):
    for index in range(23):
        create(api_client, '/api/capacity-changes', {**operation_payload, 'operation_type': 'INCREASE', 'new_capacity': str(index + 1), 'new_unit': 'Mbps'})
    page1 = api_client.get('/api/capacity-changes', params={'circuit_id': operation_payload['circuit_id'], 'limit': 10}).json()
    page2 = api_client.get('/api/capacity-changes', params={'limit': 10, 'offset': 10}).json()
    assert len(page1) == len(page2) == 10
    assert not set(r['id'] for r in page1) & set(r['id'] for r in page2)
    assert len(api_client.get('/api/capacity-changes').json()) == 23
    assert api_client.get('/api/capacity-changes', params={'customer_id': 999}).json() == []
    assert api_client.get('/api/capacity-changes', params={'operation_type': 'DECREASE'}).json() == []
    assert len(api_client.get('/api/capacity-changes', params={'from_at': '2020-01-01T18:00:00Z', 'to_at': '2020-01-01T18:00:01Z'}).json()) == 23
    assert api_client.get('/api/capacity-changes', params={'to_at': '2020-01-01T18:00:00Z'}).json() == []
    assert api_client.get('/api/capacity-changes', params={'from_at': '2020-01-01T12:00:00', 'to_at': '2020-01-02T12:00:00Z'}).status_code == 422


def test_relations_and_readonly_fields(api_client, operation_payload):
    assert api_client.post('/api/activations', json={**operation_payload, 'circuit_id': 999}).status_code == 404
    assert api_client.post('/api/activations', json={**operation_payload, 'responsible_id': 999}).status_code == 404
    assert api_client.post('/api/activations', json={**operation_payload, 'reference': 'OWN'}).status_code == 422
    assert api_client.post('/api/activations', json={**operation_payload, 'created_at': operation_payload['effective_at']}).status_code == 422
    api_client.patch(f"/api/responsibles/{operation_payload['responsible_id']}", json={'active': False})
    assert api_client.post('/api/activations', json=operation_payload).status_code == 422


def test_reason_names_case_insensitive(api_client):
    create(api_client, '/api/deactivation-reasons', {'name': '  Solicitud  '})
    assert api_client.post('/api/deactivation-reasons', json={'name': 'solicitud'}).status_code == 409


def test_activation_number_concurrency(concurrent_database):
    engine, ticket = concurrent_database
    with Session(engine) as session:
        person = Responsible(name='Operador')
        session.add(person); session.commit(); person_id = person.id
    def worker(index):
        with Session(engine) as session:
            row = create_operation(session, Activation, {'node_id': ticket['node_id'], 'sector_id': ticket['sector_id'], 'circuit_id': ticket['circuit_id'], 'responsible_id': person_id, 'effective_at': datetime(2020, 1, 1, tzinfo=timezone.utc)})
            return row.reference
    with ThreadPoolExecutor(max_workers=6) as pool:
        refs = list(pool.map(worker, range(12)))
    assert len(set(refs)) == 12
    with Session(engine) as session:
        assert session.get(ActivationNumberConfig, 1).next_number == 13
        assert session.get(TicketNumberConfig, 1) is None


def test_capacity_db_constraints(db_session, operation_payload):
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(CapacityChange(**{**operation_payload, 'effective_at': datetime.now(timezone.utc)}, operation_type='DECREASE', previous_capacity=None, previous_unit='Mbps', new_capacity=1, new_unit='Mbps'))
            db_session.flush()


def test_inactive_circuit_can_retain_operational_history(api_client, operation_payload):
    api_client.patch(f"/api/circuits/{operation_payload['circuit_id']}", json={'active': False})
    create(api_client, '/api/activations', operation_payload)
    create(api_client, '/api/circuit-lifecycle', {**operation_payload, 'operation_type': 'REACTIVATE'})
    assert api_client.get(f"/api/circuits/{operation_payload['circuit_id']}").json()['active'] is False


def test_activation_failure_does_not_consume_counter(api_client, operation_payload):
    api_client.get('/api/settings/activation-number')
    assert api_client.post('/api/activations', json={**operation_payload, 'responsible_id': 999}).status_code == 404
    assert api_client.get('/api/settings/activation-number').json()['next_number'] == 1
    assert create(api_client, '/api/activations', operation_payload)['reference'] == 'ACT-000001'


def test_rollback_does_not_consume_activation_number(concurrent_database):
    engine, ticket = concurrent_database
    with Session(engine) as session:
        person = Responsible(name='Operador rollback'); session.add(person); session.commit(); id = person.id
    # A failed commit must roll back both the record and the independent counter.
    from unittest.mock import patch
    with Session(engine) as session:
        with patch.object(session, 'commit', side_effect=RuntimeError('fallo simulado')):
            with pytest.raises(RuntimeError):
                create_operation(session, Activation, {'node_id': ticket['node_id'], 'sector_id': ticket['sector_id'], 'circuit_id': ticket['circuit_id'], 'responsible_id': id, 'effective_at': datetime.now(timezone.utc)})
        assert session.scalar(select(Activation.id)) is None
        assert session.get(ActivationNumberConfig, 1) is None
        row = create_operation(session, Activation, {'node_id': ticket['node_id'], 'sector_id': ticket['sector_id'], 'circuit_id': ticket['circuit_id'], 'responsible_id': id, 'effective_at': datetime.now(timezone.utc)})
        assert row.reference == 'ACT-000001'


def test_operations_list_query_count(api_client, operation_payload, db_session):
    from sqlalchemy import event
    for _ in range(4):
        create(api_client, '/api/activations', operation_payload)
    connection = db_session.get_bind(); queries = []
    def count(*args): queries.append(args[2])
    event.listen(connection, 'before_cursor_execute', count)
    try:
        assert len(api_client.get('/api/activations').json()) == 4
    finally:
        event.remove(connection, 'before_cursor_execute', count)
    assert len(queries) == 1


def test_deactivation_reason_database_uniqueness(api_client, db_session):
    from ticketyn.models.fms import DeactivationReason
    create(api_client, '/api/deactivation-reasons', {'name': 'Proveedor'})
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(DeactivationReason(name=' proveedor '))
            db_session.flush()


def test_references_cannot_be_reused_after_configuration_change(api_client, operation_payload):
    # Different number/padding/prefix combinations can produce identical text.
    api_client.patch('/api/settings/activation-number', json={'prefix': 'ACT-1', 'separator': '', 'padding': 0, 'next_number': 2})
    assert create(api_client, '/api/activations', operation_payload)['reference'] == 'ACT-12'
    config = api_client.get('/api/settings/activation-number').json()
    assert api_client.patch('/api/settings/activation-number', json={'prefix': 'ACT', 'separator': '-', 'padding': 0, 'next_number': 12}).status_code == 409
    assert api_client.get('/api/settings/activation-number').json() == config
    assert api_client.get('/api/activations').json()[0]['reference'] == 'ACT-12'


@pytest.mark.parametrize('field', ['initial', 'new', 'previous'])
def test_database_rejects_nan_capacity(api_client, operation_payload, db_session, field):
    from decimal import Decimal
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            if field == 'initial':
                db_session.execute(text("UPDATE circuits SET initial_capacity = 'NaN'::numeric, initial_capacity_unit='Mbps' WHERE id=:id"), {'id': operation_payload['circuit_id']})
            else:
                db_session.add(CapacityChange(circuit_id=operation_payload['circuit_id'], responsible_id=operation_payload['responsible_id'], effective_at=datetime.now(timezone.utc), operation_type='INCREASE', previous_capacity=Decimal('NaN') if field == 'previous' else None, previous_unit='Mbps' if field == 'previous' else None, new_capacity=Decimal('NaN') if field == 'new' else 1, new_unit='Gbps'))
                db_session.flush()
