"""Only disposable PostgreSQL; never an existing installation or DEV records."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ticketyn.api.crud import delete_unreferenced
from ticketyn.models import Circuit, Customer, Ticket, TicketUpdate
from test_ticket_updates import ticket, create


def customer(client, **values):
    response = client.post('/api/customers', json={'customer_code': 'DELETE-TEST', 'name': 'Creado por error', **values})
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize('active', [True, False])
def test_delete_unreferenced_customer(api_client, active):
    item = customer(api_client, active=active)
    response = api_client.delete(f"/api/customers/{item['id']}")
    assert response.status_code == 204 and response.content == b''
    assert api_client.get(f"/api/customers/{item['id']}").status_code == 404
    assert api_client.delete(f"/api/customers/{item['id']}").status_code == 404
    assert customer(api_client)['customer_code'] == item['customer_code']


@pytest.mark.parametrize('active', [True, False])
def test_delete_unreferenced_circuit_preserves_parent_and_node(api_client, ticket_payload, active):
    node = api_client.post('/api/nodes', json={'name': 'Nodo conservado'}).json()
    cid = ticket_payload['circuit_id']
    api_client.patch(f'/api/circuits/{cid}', json={'node_id': node['id'], 'active': active})
    response = api_client.delete(f'/api/circuits/{cid}')
    assert response.status_code == 204 and response.content == b''
    assert api_client.get(f'/api/circuits/{cid}').status_code == 404
    assert api_client.get(f"/api/customers/{ticket_payload['customer_id']}").status_code == 200
    assert api_client.get(f"/api/nodes/{node['id']}").status_code == 200
    assert api_client.delete(f'/api/circuits/{cid}').status_code == 404


@pytest.mark.parametrize('resource', ['customers', 'circuits'])
def test_delete_missing(api_client, resource):
    assert api_client.delete(f'/api/{resource}/999999').status_code == 404
    assert api_client.delete(f'/api/{resource}/0').status_code == 422


def test_customer_with_inactive_circuit_rejected(api_client, ticket_payload):
    api_client.patch(f"/api/circuits/{ticket_payload['circuit_id']}", json={'active': False})
    response = api_client.delete(f"/api/customers/{ticket_payload['customer_id']}")
    assert response.status_code == 409 and 'desactiv' in response.json()['detail']
    assert api_client.get(f"/api/circuits/{ticket_payload['circuit_id']}").status_code == 200


@pytest.mark.parametrize('status', ['OPEN', 'CLOSED'])
def test_tickets_and_followup_survive_rejected_deletions(api_client, ticket_payload, status):
    item = ticket(api_client, ticket_payload, status=status, end_at='2020-01-01T13:00:00Z' if status == 'CLOSED' else None)
    update = create(api_client, item)
    before = api_client.get(f"/api/tickets/{item['id']}").json()
    for resource, id in [('customers', item['customer_id']), ('circuits', item['circuit_id'])]:
        response = api_client.delete(f'/api/{resource}/{id}')
        assert response.status_code == 409 and 'desactiv' in response.json()['detail']
        assert api_client.get(f'/api/{resource}/{id}').status_code == 200
    assert api_client.get(f"/api/tickets/{item['id']}").json() == before
    assert api_client.get(f"/api/tickets/{item['id']}/updates").json()[0]['id'] == update['id']


def test_customer_ticket_dependency_checked_independently(api_client, ticket_payload):
    # Ticket.customer_id is a separate FK: do not rely only on circuits.customer_id.
    item = ticket(api_client, ticket_payload)
    other = customer(api_client)
    api_client.patch(f"/api/circuits/{item['circuit_id']}", json={'customer_id': other['id']})
    response = api_client.delete(f"/api/customers/{item['customer_id']}")
    assert response.status_code == 409
    assert api_client.get(f"/api/tickets/{item['id']}").json()['customer_id'] == item['customer_id']


@pytest.mark.parametrize('resource', ['customers', 'circuits'])
def test_fk_is_final_guard_and_transaction_recovers(api_client, ticket_payload, db_session, monkeypatch, resource):
    item = ticket(api_client, ticket_payload)
    original = db_session.scalar
    def omit_precheck(statement, *args, **kwargs):
        # Simulate a dependency missed by a precheck: the real PostgreSQL FK must reject DELETE.
        if 'EXISTS' in str(statement):
            return False
        return original(statement, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(db_session, 'scalar', omit_precheck)
        response = api_client.delete(f"/api/{resource}/{item['customer_id'] if resource == 'customers' else item['circuit_id']}")
        assert response.status_code == 409
    assert api_client.get(f"/api/tickets/{item['id']}").status_code == 200
    assert db_session.scalar(select(TicketUpdate.id)) is None
    assert customer(api_client)['id'] > 0  # rollback left the session usable


def test_concurrent_fk_insert_blocks_delete_and_preserves_both(postgres_engine):
    # Independent real transactions in the disposable cluster, with committed test-only records.
    with Session(postgres_engine) as session:
        item = Customer(customer_code=f'RACE-{uuid4().hex}', name='Concurrency test')
        session.add(item); session.commit(); cid = item.id
    started = Event()
    def remove():
        with Session(postgres_engine) as session:
            started.set()
            try:
                delete_unreferenced(session, Customer, cid, dependent_columns=(Circuit.customer_id, Ticket.customer_id), conflict_detail='Tiene dependencias')
            except HTTPException as error:
                return error.status_code
            return 204
    try:
        with Session(postgres_engine) as writer, ThreadPoolExecutor(max_workers=1) as executor:
            writer.add(Circuit(customer_id=cid, circuit_code=f'RACE-{uuid4().hex}', description='Concurrent circuit'))
            writer.flush()  # holds PostgreSQL FK KEY SHARE before deletion attempts FOR UPDATE
            pending = executor.submit(remove)
            assert started.wait(5)
            writer.commit()
            assert pending.result(timeout=10) == 409
        with Session(postgres_engine) as check:
            assert check.get(Customer, cid) is not None
            assert check.scalar(select(Circuit.id).where(Circuit.customer_id == cid)) is not None
    finally:
        with Session(postgres_engine) as cleanup:
            cleanup.execute(delete(Circuit).where(Circuit.customer_id == cid))
            cleanup.execute(delete(Customer).where(Customer.id == cid)); cleanup.commit()


def test_delete_not_exposed_for_tickets_updates_or_other_catalogs(api_client):
    for resource in ['tickets', 'nodes', 'responsibles', 'sectors', 'departments', 'incident-types']:
        assert api_client.delete(f'/api/{resource}/999999').status_code == 405
    assert api_client.delete('/api/tickets/999999/updates').status_code == 405


@pytest.mark.parametrize('sqlstate', ['40001', '40P01', '55P03'])
def test_concurrency_errors_rollback_with_safe_conflict(api_client, db_session, monkeypatch, sqlstate):
    from sqlalchemy.exc import OperationalError
    item = customer(api_client)
    class Conflict(Exception):
        pass
    error = Conflict('PRIVATE-SQL-DIAGNOSTIC')
    error.sqlstate = sqlstate
    with monkeypatch.context() as patch:
        def fail(*args, **kwargs):
            raise OperationalError('PRIVATE-SQL', {}, error)
        patch.setattr(db_session, 'scalar', fail)
        response = api_client.delete(f"/api/customers/{item['id']}")
        assert response.status_code == 409
        assert 'concurrente' in response.json()['detail'] and 'PRIVATE-' not in response.text
    assert api_client.get(f"/api/customers/{item['id']}").status_code == 200
