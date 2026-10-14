"""Reportes de consulta sobre PostgreSQL temporal, nunca bases operativas."""
from decimal import Decimal
import pytest
from test_fms import operation_payload, create
from ticketyn.models import Circuit

BASE = '/api/fms/reports/'
RANGE = {'from': '2020-01-01T06:00:00Z', 'to': '2020-01-02T06:00:00Z', 'timezone': 'America/Guatemala'}


def report(client, kind, **filters):
    response = client.get(BASE + kind + '/summary', params={**RANGE, **filters})
    assert response.status_code == 200, response.text
    return response.json()


def test_activation_distinct_counts_history_and_no_log_duplicates(api_client, operation_payload, db_session):
    first = create(api_client, '/api/activations', operation_payload)
    create(api_client, '/api/activations', operation_payload)
    for content in ['A', 'B']:
        create(api_client, f"/api/activations/{first['id']}/interventions", {'responsible_id': operation_payload['responsible_id'], 'occurred_at': '2020-01-01T18:00:00Z', 'content': content})
    create(api_client, '/api/activations', {**operation_payload, 'effective_at': RANGE['to']})
    circuit = db_session.get(Circuit, operation_payload['circuit_id'])
    other_sector = create(api_client, '/api/sectors', {'name': 'Sector actual diferente'})
    other_node = create(api_client, '/api/nodes', {'name': 'Nodo actual diferente'})
    api_client.patch(f'/api/circuits/{circuit.id}', json={'sector_id': other_sector['id'], 'node_id': other_node['id']})
    for field in ['sector_id', 'node_id', 'responsible_id']:
        summary = report(api_client, 'activations', **{field: first[field]})
        assert summary['kpis'] == {'total': 2, 'distinct_customers': 1, 'distinct_circuits': 1}
        assert summary['customers'] == []
        assert sum(row['count'] for row in summary['trend']) == 2
    assert report(api_client, 'activations', sector_id=other_sector['id'])['kpis']['total'] == 0
    general = report(api_client, 'activations')
    assert general['customers'][0]['count'] == 1
    assert general['period']['granularity'] == 'day'
    details = api_client.get(BASE + 'activations/details', params={**RANGE, 'limit': 1}).json()
    assert len(details) == 1 and details[0]['id'] != first['id']
    second_page = api_client.get(BASE + 'activations/details', params={**RANGE, 'limit': 1, 'offset': 1}).json()
    assert second_page[0]['id'] == first['id']


def test_capacity_decimal_known_variations_and_events(api_client, operation_payload):
    for type, old, old_unit, new, new_unit in [('INCREASE', '500', 'Mbps', '1.5', 'Gbps'), ('DECREASE', '2', 'Gbps', '500', 'Mbps'), ('INCREASE', None, None, '100', 'Mbps')]:
        create(api_client, '/api/capacity-changes', {**operation_payload, 'operation_type': type, 'previous_capacity': old, 'previous_unit': old_unit, 'new_capacity': new, 'new_unit': new_unit})
    summary = report(api_client, 'capacity-changes')
    k = summary['kpis']
    assert (k['increases'], k['decreases'], k['unknown_variations']) == (2, 1, 1)
    assert Decimal(k['known_added_mbps']) == 1000
    assert Decimal(k['known_reduced_mbps']) == 1500
    assert Decimal(k['known_net_mbps']) == -500
    assert sum(x['first'] for x in summary['trend']) == 2
    assert sum(x['second'] for x in summary['trend']) == 1


def test_lifecycle_repeated_events_distinct_circuits_and_inactive_reason(api_client, operation_payload):
    reason = create(api_client, '/api/deactivation-reasons', {'name': 'Solicitud del cliente'})
    for type in ['DEACTIVATE', 'REACTIVATE', 'DEACTIVATE']:
        create(api_client, '/api/circuit-lifecycle', {**operation_payload, 'operation_type': type, **({'reason_id': reason['id']} if type == 'DEACTIVATE' else {})})
    api_client.patch(f"/api/deactivation-reasons/{reason['id']}", json={'active': False})
    summary = report(api_client, 'circuit-lifecycle')
    assert summary['kpis'] == {'deactivations': 2, 'reactivations': 1, 'distinct_deactivated_circuits': 1, 'distinct_reactivated_circuits': 1}
    assert summary['reasons'][0]['count'] == 2
    assert summary['reasons'][0]['label'] == reason['name']
    assert sum(x['count'] for x in summary['trend']) == 3


@pytest.mark.parametrize('kind', ['activations', 'capacity-changes', 'circuit-lifecycle'])
def test_empty_and_invalid_requests(api_client, kind):
    summary = api_client.get(BASE + kind + '/summary').json()
    assert summary['trend'] == []
    assert summary['period']['timezone'] == 'America/Guatemala'
    for filters in [{'from': RANGE['from']}, {'timezone': 'Invalid/zone'}, {'granularity': 'hour'}, {'sector_id': -1}, {'recipient_id': 1}, {'from': RANGE['to'], 'to': RANGE['from']}]:
        assert api_client.get(BASE + kind + '/summary', params=filters).status_code == 422
    assert api_client.get(BASE + kind + '/summary', params={'node_id': 999999}).status_code == 404
    assert api_client.get(BASE + kind + '/details', params={'limit': 201}).status_code == 422


def test_guatemala_midnight_monthly_and_all(api_client, operation_payload):
    for at in ['2020-01-01T05:59:59Z', '2020-01-01T06:00:00Z', '2020-01-02T05:59:59Z', '2020-01-02T06:00:00Z']:
        create(api_client, '/api/activations', {**operation_payload, 'effective_at': at})
    assert report(api_client, 'activations')['kpis']['total'] == 2
    summary = api_client.get(BASE + 'activations/summary', params={'from': '2019-12-01T06:00:00Z', 'to': '2020-06-01T06:00:00Z'}).json()
    assert summary['period']['granularity'] == 'month'
    assert len(summary['trend']) == 6
    assert sum(x['count'] for x in summary['trend']) == 4
    all_data = api_client.get(BASE + 'activations/summary').json()
    assert all_data['kpis']['total'] == 4
    assert sum(x['count'] for x in all_data['trend']) == 4
    assert all_data['period']['from_at'] is None


@pytest.mark.parametrize('kind', ['activations', 'capacity-changes', 'circuit-lifecycle'])
def test_details_all_pages_combined_filters_preserve_records(api_client, operation_payload, kind):
    extra = {'operation_type': 'INCREASE', 'new_capacity': '1', 'new_unit': 'Gbps'} if kind == 'capacity-changes' else {'operation_type': 'REACTIVATE'} if kind == 'circuit-lifecycle' else {}
    rows = [create(api_client, '/api/' + kind, {**operation_payload, **extra}) for _ in range(51)]
    query = {**RANGE, **{field: rows[0][field] for field in ['sector_id', 'node_id', 'responsible_id']}}
    summary = api_client.get(BASE + kind + '/summary', params=query)
    assert summary.status_code == 200, summary.text
    assert sum(row['count'] for row in summary.json()['trend']) == 51
    first = api_client.get(BASE + kind + '/details', params=query)
    assert first.status_code == 200, first.text
    second = api_client.get(BASE + kind + '/details', params={**query, 'offset': 50}).json()
    ids = [row['id'] for row in first.json() + second]
    assert ids == [row['id'] for row in reversed(rows)]
    # Reports have not changed administrative state, numbering or records.
    assert api_client.get('/api/' + kind, params={'limit': 100}).json() == list(reversed(rows))


def test_activation_top_ten_distinct_circuits_not_event_ranking(api_client, operation_payload, ticket_payload):
    first = create(api_client, '/api/activations', operation_payload)
    for index in range(11):
        customer = create(api_client, '/api/customers', {'name': f'Cliente ranking {index}', 'customer_code': f'R{index}'})
        circuit = create(api_client, '/api/circuits', {'customer_id': customer['id'], 'circuit_code': f'RC{index}', 'description': 'Circuito ranking', 'sector_id': first['sector_id'], 'node_id': first['node_id']})
        create(api_client, '/api/activations', {**operation_payload, 'circuit_id': circuit['id']})
    circuit = create(api_client, '/api/circuits', {'customer_id': first['circuit']['customer_id'], 'circuit_code': 'RC-second', 'description': 'Segundo circuito', 'sector_id': first['sector_id'], 'node_id': first['node_id']})
    create(api_client, '/api/activations', {**operation_payload, 'circuit_id': circuit['id']})
    summary = report(api_client, 'activations')
    assert summary['kpis'] == {'total': 13, 'distinct_customers': 12, 'distinct_circuits': 13}
    assert len(summary['customers']) == 10
    assert summary['customers'][0]['count'] == 2


@pytest.mark.parametrize('kind', ['activations', 'capacity-changes', 'circuit-lifecycle'])
def test_legacy_missing_assignments_remain_general_only(api_client, operation_payload, db_session, kind):
    from ticketyn.api.fms_reports import MODELS
    extra = {'operation_type': 'INCREASE', 'new_capacity': '1', 'new_unit': 'Gbps'} if kind == 'capacity-changes' else {'operation_type': 'REACTIVATE'} if kind == 'circuit-lifecycle' else {}
    row = create(api_client, '/api/' + kind, {**operation_payload, **extra})
    operation = db_session.get(MODELS[kind], row['id'])
    operation.node_id = None
    operation.sector_id = None
    db_session.flush()
    db_session.expire_all()
    general = report(api_client, kind)
    assert sum(x['count'] for x in general['trend']) == 1
    for field in ['sector_id', 'node_id']:
        assert sum(x['count'] for x in report(api_client, kind, **{field: row[field]})['trend']) == 0
    details = api_client.get(BASE + kind + '/details', params=RANGE).json()
    assert details[0]['sector'] is None and details[0]['node'] is None
