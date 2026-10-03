from datetime import datetime, timezone

import pytest
from sqlalchemy import event

from ticketyn.api.ticket_data import ticket_statement
from test_tickets import create_ticket, RELATED_PATHS


def ids(response):
    assert response.status_code == 200, response.text
    return [row['id'] for row in response.json()]


def test_start_range_boundaries_and_retroactive_tickets(api_client, ticket_payload):
    rows = [create_ticket(api_client, {**ticket_payload, 'start_at': value}) for value in (
        '2020-01-01T05:59:59Z', '2020-01-01T06:00:00Z',
        '2020-01-02T05:59:59Z', '2020-01-02T06:00:00Z')]
    params = {'from': '2020-01-01T00:00:00-06:00', 'to': '2020-01-02T00:00:00-06:00'}
    assert ids(api_client.get('/api/tickets', params=params)) == [rows[2]['id'], rows[1]['id']]
    assert ids(api_client.get('/api/tickets', params={**params, 'status': 'OPEN', 'customer_id': ticket_payload['customer_id'], 'limit': 1, 'offset': 1})) == [rows[1]['id']]
    assert len(ids(api_client.get('/api/tickets', params={'from': params['from']}))) == 3
    assert len(ids(api_client.get('/api/tickets', params={'to': params['to']}))) == 3


@pytest.mark.parametrize('params', [
    {'from': '2020-01-01T00:00:00'}, {'to': 'invalid'},
    {'from': '2020-01-02T00:00:00Z', 'to': '2020-01-01T00:00:00Z'},
    {'from': '2020-01-01T00:00:00Z', 'to': '2020-01-01T00:00:00Z'},
])
def test_invalid_date_filters(api_client, params):
    assert api_client.get('/api/tickets', params=params).status_code == 422


def test_number_search_and_unpaginated_reusable_query(api_client, ticket_payload, db_session):
    api_client.patch('/api/settings/ticket-number', json={'prefix': 'REF', 'next_number': 123})
    item = create_ticket(api_client, ticket_payload)
    assert ids(api_client.get('/api/tickets', params={'search': '123'})) == [item['id']]
    query = ticket_statement({'from_at': datetime(2020, 1, 1, tzinfo=timezone.utc), 'customer_id': item['customer_id'], 'limit': 0, 'offset': 999})
    assert [row.id for row in db_session.scalars(query)] == [item['id']]


def test_summaries_historical_and_single_sql_query(api_client, ticket_payload, db_session):
    for _ in range(3):
        create_ticket(api_client, ticket_payload)
    expected = {}
    for field, path in RELATED_PATHS.items():
        expected[field] = api_client.get(f'{path}/{ticket_payload[field]}').json()
        assert api_client.patch(f'{path}/{ticket_payload[field]}', json={'active': False}).status_code == 200
    statements = []
    connection = db_session.connection()
    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)
    event.listen(connection, 'before_cursor_execute', record)
    try:
        response = api_client.get('/api/tickets')
    finally:
        event.remove(connection, 'before_cursor_execute', record)
    assert response.status_code == 200
    assert len(statements) == 1
    assert len(response.json()) == 3
    row = response.json()[0]
    assert row['customer'] == {key: expected['customer_id'][key] for key in ('id', 'customer_code', 'name')}
    assert row['circuit'] == {key: expected['circuit_id'][key] for key in ('id', 'circuit_code', 'description')}
    for key in ('sector', 'department', 'incident_type'):
        assert row[key] == {field: expected[key + '_id'][field] for field in ('id', 'name')}


def test_circuit_combined_filters_and_compatibility(api_client):
    customer = api_client.post('/api/customers', json={'customer_code': 'C', 'name': 'Customer'}).json()
    other = api_client.post('/api/customers', json={'customer_code': 'D', 'name': 'Other'}).json()
    rows = []
    for code, active, owner in [('ABC-1', True, customer), ('ABC-2', False, customer), ('DEF', True, other)]:
        response = api_client.post('/api/circuits', json={'customer_id': owner['id'], 'circuit_code': code, 'description': 'Internet principal', 'active': active})
        assert response.status_code == 201
        rows.append(response.json())
    assert ids(api_client.get('/api/circuits')) == [rows[0]['id'], rows[2]['id']]
    assert len(ids(api_client.get('/api/circuits', params={'include_inactive': True}))) == 3
    assert ids(api_client.get('/api/circuits', params={'customer_id': customer['id'], 'search': 'abc', 'active': False})) == [rows[1]['id']]
    assert ids(api_client.get('/api/circuits', params={'search': 'INTERNET', 'active': True, 'include_inactive': True, 'limit': 1, 'offset': 1})) == [rows[2]['id']]
