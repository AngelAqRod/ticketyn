"""Natural port ordering is owned by PostgreSQL, before filtering pages reach React."""
import pytest
from sqlalchemy import select

from ticketyn.models import DistributionPort


def device(client, node_id, name='Natural order'):
    response = client.post('/api/distribution-devices', json={'node_id': node_id, 'name': name})
    assert response.status_code == 201, response.text
    return response.json()['id']


@pytest.mark.parametrize('names,expected', [
    (['SFP10', 'SFP2', 'SFP1'], ['SFP1', 'SFP2', 'SFP10']),
    (['Gi2/0/1', 'Gi1/0/10', 'Gi1/0/2'], ['Gi1/0/2', 'Gi1/0/10', 'Gi2/0/1']),
    (['ge-0/0/10', 'ge-0/0/1', 'ge-0/0/2'], ['ge-0/0/1', 'ge-0/0/2', 'ge-0/0/10']),
    (['SFP10', 'sfp3', 'SFP2', 'SFP01', 'SFP0', 'SFP1'], ['SFP0', 'SFP01', 'SFP1', 'SFP2', 'sfp3', 'SFP10']),
    (['SFP' + '1' + '0' * 50, 'SFP' + '9' * 50], ['SFP' + '9' * 50, 'SFP' + '1' + '0' * 50]),
    (['10/2', '2/10', '2/2', '2/0'], ['2/0', '2/2', '2/10', '10/2']),
])
def test_historical_ports_use_integer_segments_without_renaming(api_client, ticket_payload, db_session, names, expected):
    device_id = device(api_client, ticket_payload['node_id'])
    db_session.add_all([DistributionPort(distribution_device_id=device_id, name=name) for name in names])
    db_session.commit()
    before = db_session.execute(select(DistributionPort.id, DistributionPort.name, DistributionPort.nomenclature_id).order_by(DistributionPort.id)).all()
    response = api_client.get('/api/distribution-ports', params={'distribution_device_id': device_id})
    assert response.status_code == 200, response.text
    assert [row['name'] for row in response.json()] == expected
    assert db_session.execute(select(DistributionPort.id, DistributionPort.name, DistributionPort.nomenclature_id).order_by(DistributionPort.id)).all() == before


def test_24_ports_sort_before_pagination_and_keep_inactive_rows(api_client, ticket_payload, db_session):
    device_id = device(api_client, ticket_payload['node_id'])
    db_session.add_all([DistributionPort(distribution_device_id=device_id, name=f'SFP{number}', active=number != 6)
                        for number in range(24, 0, -1)])
    db_session.commit()
    query = {'distribution_device_id': device_id, 'include_inactive': True, 'limit': 5}
    rows = [row for offset in range(0, 25, 5)
            for row in api_client.get('/api/distribution-ports', params={**query, 'offset': offset}).json()]
    assert [row['name'] for row in rows] == [f'SFP{number}' for number in range(1, 25)]
    assert len({row['id'] for row in rows}) == 24
    assert rows[5]['active'] is False and all(row['nomenclature_id'] is None for row in rows)
    active = api_client.get('/api/distribution-ports', params={'distribution_device_id': device_id}).json()
    assert [row['name'] for row in active] == [f'SFP{number}' for number in range(1, 25) if number != 6]
    filtered = api_client.get('/api/distribution-ports', params={**query, 'search': 'SFP1', 'offset': 1, 'limit': 3}).json()
    assert [row['name'] for row in filtered] == ['SFP10', 'SFP11', 'SFP12']


def test_equal_names_in_different_devices_have_deterministic_id_tie_break(api_client, ticket_payload, db_session):
    for name in ('Second', 'First'):
        device_id = device(api_client, ticket_payload['node_id'], name)
        db_session.add(DistributionPort(distribution_device_id=device_id, name='SFP2'))
        db_session.commit()
    first = api_client.get('/api/distribution-ports?limit=1&offset=0').json()[0]
    second = api_client.get('/api/distribution-ports?limit=1&offset=1').json()[0]
    assert first['id'] < second['id']
    assert api_client.get('/api/distribution-ports?limit=1&offset=0').json()[0] == first


def test_bulk_preview_preserves_numeric_sequence_for_all_formats(api_client, ticket_payload):
    device_id = device(api_client, ticket_payload['node_id'])
    catalog = api_client.post('/api/port-nomenclatures', json={
        'name': 'Preview', 'prefix': 'Gi', 'formats': ['N', 'X/Y', 'X/Y/Z', 'W/X/Y/Z']}).json()
    for fmt, positions in [('N', []), ('X/Y', [0]), ('X/Y/Z', [1, 0]), ('W/X/Y/Z', [0, 1, 0])]:
        response = api_client.post('/api/distribution-ports/preview', json={
            'distribution_device_id': device_id, 'nomenclature_id': catalog['id'],
            'numbering_format': fmt, 'positions': positions, 'start': 0, 'end': 24})
        assert response.status_code == 200, response.text
        assert [row['name'] for row in response.json()['names']] == [
            'Gi' + '/'.join(map(str, [*positions, number])) for number in range(25)]
