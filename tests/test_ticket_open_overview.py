"""Antigüedad de abiertos: límites exactos, filtros de listado, orden y estadísticas del Dashboard."""
from datetime import datetime, timedelta, timezone

import pytest

from test_security_foundation import security_client, make_account, login, authorize  # noqa: F401
from test_tickets import create_ticket
from ticketyn.api.ticket_age import AGE_BUCKETS, open_overview
from ticketyn.api.ticket_data import ticket_statement

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
SECOND = timedelta(seconds=1)
HOUR = timedelta(hours=1)


def make(api_client, payload, age, **extra):
    """Ticket abierto cuya antigüedad respecto a NOW es `age` (negativa = inicio futuro)."""
    return create_ticket(api_client, {**payload, 'start_at': (NOW - age).isoformat(), 'status': 'OPEN', **extra})


@pytest.fixture
def bounds(api_client, ticket_payload):
    ages = {
        'zero': timedelta(0), 'lt1': HOUR - SECOND, 'one': HOUR, 'lt4': 4 * HOUR - SECOND, 'four': 4 * HOUR,
        'day': 24 * HOUR, 'over': 24 * HOUR + SECOND, 'old': 72 * HOUR, 'future': -HOUR,
    }
    return {name: make(api_client, ticket_payload, age)['id'] for name, age in ages.items()}


def bucket_ids(db_session, bucket):
    return {row.id for row in db_session.scalars(ticket_statement({'age_bucket': bucket, 'now': NOW}))}


def test_exact_boundaries_are_exclusive_and_exhaustive(bounds, db_session):
    assert bucket_ids(db_session, 'lt_1h') == {bounds['zero'], bounds['lt1']}
    assert bucket_ids(db_session, '1_to_4h') == {bounds['one'], bounds['lt4']}
    assert bucket_ids(db_session, '4_to_24h') == {bounds['four'], bounds['day']}   # 24 h exactas siguen en 4–24 h
    assert bucket_ids(db_session, 'gt_24h') == {bounds['over'], bounds['old']}     # estrictamente mayor
    sets = [bucket_ids(db_session, bucket) for bucket in AGE_BUCKETS]
    assert sum(map(len, sets)) == len(set().union(*sets))                          # ningún ticket en dos tramos
    overview = open_overview(db_session, NOW)
    assert overview['buckets'] == dict(zip(AGE_BUCKETS, map(len, sets)))
    assert overview['future_start'] == 1 and sum(overview['buckets'].values()) + overview['future_start'] == overview['open']


def test_closed_tickets_do_not_age(api_client, ticket_payload, db_session):
    make(api_client, ticket_payload, 48 * HOUR, status='CLOSED', end_at=(NOW - 47 * HOUR).isoformat())
    assert open_overview(db_session, NOW)['open'] == 0 and bucket_ids(db_session, 'gt_24h') == set()


def test_empty_overview(db_session):
    assert open_overview(db_session, NOW) | {'generated_at': None} == {
        'generated_at': None, 'open': 0, 'future_start': 0, 'unassigned': 0,
        'buckets': {bucket: 0 for bucket in AGE_BUCKETS}, 'sectors': []}


def test_unassigned_is_cross_cutting_and_sectors_have_no_join_duplicates(api_client, ticket_payload, db_session):
    other_sector = api_client.post('/api/sectors', json={'name': 'Otro sector'}).json()['id']
    other_circuit = api_client.post('/api/circuits', json={
        'node_id': ticket_payload['node_id'], 'sector_id': other_sector, 'customer_id': ticket_payload['customer_id'],
        'circuit_code': 'CIRCUITO-2', 'description': 'Otro'}).json()['id']
    for age in (HOUR // 2, 2 * HOUR, 30 * HOUR):
        make(api_client, ticket_payload, age)
    make(api_client, ticket_payload, HOUR // 2, circuit_id=other_circuit, sector_id=other_sector)
    overview = open_overview(db_session, NOW)
    assert overview['open'] == 4 and overview['unassigned'] == 4
    assert [(row['name'], row['count']) for row in overview['sectors']] == [('Sector de prueba', 3), ('Otro sector', 1)]
    assert sum(row['count'] for row in overview['sectors']) == overview['open']
    assert len({row.id for row in db_session.scalars(ticket_statement({'unassigned': True}))}) == 4


def test_listing_filters_total_and_ordering(api_client, ticket_payload):
    now = datetime.now(timezone.utc)
    for index, age in enumerate((timedelta(minutes=30), 2 * HOUR, 5 * HOUR, 30 * HOUR, 40 * HOUR)):
        create_ticket(api_client, {**ticket_payload, 'start_at': (now - age).isoformat(), 'status': 'OPEN'})
    for bucket, expected in (('lt_1h', 1), ('1_to_4h', 1), ('4_to_24h', 1), ('gt_24h', 2)):
        response = api_client.get('/api/tickets', params={'age_bucket': bucket, 'limit': 1})
        assert response.status_code == 200 and int(response.headers['X-Total-Count']) == expected
    overview = api_client.get('/api/tickets/open-overview').json()
    assert overview['buckets'] == {'lt_1h': 1, '1_to_4h': 1, '4_to_24h': 1, 'gt_24h': 2}
    asc = api_client.get('/api/tickets', params={'status': 'OPEN', 'order': 'start_at_asc', 'limit': 5}).json()
    assert [row['start_at'] for row in asc] == sorted(row['start_at'] for row in asc)
    desc = api_client.get('/api/tickets', params={'order': 'start_at_desc'}).json()
    assert [row['id'] for row in desc] == [row['id'] for row in reversed(asc)]
    assert len(api_client.get('/api/tickets', params={'unassigned': 'true'}).json()) == 5


def test_stable_order_on_equal_start(api_client, ticket_payload):
    ids = [create_ticket(api_client, {**ticket_payload, 'start_at': '2020-01-01T00:00:00Z'})['id'] for _ in range(3)]
    asc = [row['id'] for row in api_client.get('/api/tickets', params={'order': 'start_at_asc'}).json()]
    assert asc == sorted(ids)


@pytest.mark.parametrize('params', [
    {'age_bucket': '24h'}, {'age_bucket': 'gt_24h; DROP TABLE tickets'}, {'order': 'created_at'}, {'order': 'start_at; --'},
    {'unassigned': 'true', 'responsible_id': 1}, {'unassigned': 'quizas'},
])
def test_invalid_values_are_rejected(api_client, params):
    assert api_client.get('/api/tickets', params=params).status_code == 422


def test_overview_requires_tickets_view(security_client):
    client, app, factory = security_client
    make_account(factory, role='CUSTOM')
    authorize(client, login(client))
    for path in ('/api/tickets/open-overview', '/api/tickets?age_bucket=gt_24h', '/api/tickets?unassigned=true'):
        response = client.get(path)
        assert response.status_code == 403 and 'sectors' not in response.text and 'X-Total-Count' not in response.headers
