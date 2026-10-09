import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def post(client, path, body):
    response = client.post(path, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def catalogs(client):
    a = post(client, '/api/departments', {'name': 'NOC'})
    b = post(client, '/api/departments', {'name': 'Red Externa'})
    p = post(client, '/api/positions', {'name': 'Supervisor', 'department_id': a['id']})
    q = post(client, '/api/positions', {'name': 'Supervisor', 'department_id': b['id']})
    return a, b, p, q


def test_positions_scoped_catalog(api_client):
    a, b, p, q = catalogs(api_client)
    other = post(api_client, '/api/positions', {'name': 'N3', 'department_id': a['id'], 'description': 'Apoyo'})
    assert api_client.post('/api/positions', json={'name': 'Supervisor', 'department_id': a['id']}).status_code == 409
    assert api_client.get('/api/positions', params={'department_id': a['id']}).json() == [other, p]
    assert api_client.get('/api/positions', params={'department_id': b['id'], 'search': 'visor'}).json() == [q]
    assert api_client.get(f"/api/positions/{p['id']}").json() == p
    response = api_client.patch(f"/api/positions/{p['id']}", json={'name': 'Coordinador', 'description': 'Operaciones', 'active': False})
    assert response.status_code == 200
    assert response.json()['description'] == 'Operaciones'
    assert p['id'] not in [x['id'] for x in api_client.get('/api/positions').json()]
    assert p['id'] in [x['id'] for x in api_client.get('/api/positions', params={'include_inactive': True}).json()]
    assert api_client.patch(f"/api/positions/{p['id']}", json={'active': True, 'description': None}).json()['active']
    assert api_client.get('/api/positions/99999').status_code == 404
    assert api_client.delete(f"/api/positions/{p['id']}").status_code == 405


@pytest.mark.parametrize('body', [{'name': ' '}, {'name': 'x'*101}, {'department_id': None}, {'department_id': 0}, {'description': ' '}])
def test_position_validation(api_client, body):
    a = post(api_client, '/api/departments', {'name': 'NOC'})
    assert api_client.post('/api/positions', json={'name': 'N2', 'department_id': a['id'], **body}).status_code == 422


def test_assignments_sharing_history_and_integrity(api_client, db_session):
    a, b, p, q = catalogs(api_client)
    for name in ('Pedro', 'Juan'):
        person = post(api_client, '/api/responsibles', {'name': name, 'department_id': a['id'], 'position_id': p['id']})
        assert person['position']['name'] == 'Supervisor'
        assert person['department']['name'] == 'NOC'
    path = f"/api/responsibles/{person['id']}"
    assert api_client.patch(path, json={'position_id': q['id']}).status_code == 422
    assert api_client.patch(path, json={'department_id': None}).status_code == 422
    assert api_client.patch(f"/api/positions/{p['id']}", json={'department_id': b['id']}).status_code == 409
    api_client.patch(f"/api/positions/{p['id']}", json={'active': False})
    api_client.patch(f"/api/departments/{a['id']}", json={'active': False})
    assert api_client.get(path).json()['position']['active'] is False
    assert api_client.patch(path, json={'name': 'Juan histórico'}).status_code == 200
    assert api_client.post('/api/responsibles', json={'name': 'Nuevo', 'department_id': a['id'], 'position_id': p['id']}).status_code == 422
    assert api_client.patch(path, json={'department_id': b['id'], 'position_id': q['id']}).status_code == 200
    assert api_client.patch(path, json={'position_id': None, 'department_id': None}).json()['position'] is None
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(text('UPDATE responsibles SET department_id=:d, position_id=:p WHERE id=:id'), {'d': a['id'], 'p': q['id'], 'id': person['id']})


def test_assignment_missing_or_inactive(api_client):
    a, b, p, q = catalogs(api_client)
    assert api_client.post('/api/positions', json={'name': 'N1', 'department_id': 99999}).status_code == 404
    assert api_client.post('/api/responsibles', json={'name': 'Pedro', 'position_id': p['id']}).status_code == 422
    assert api_client.post('/api/responsibles', json={'name': 'Pedro', 'department_id': 99999}).status_code == 404
    assert api_client.post('/api/responsibles', json={'name': 'Pedro', 'department_id': a['id'], 'position_id': 99999}).status_code == 404
    api_client.patch(f"/api/positions/{p['id']}", json={'active': False})
    assert api_client.post('/api/responsibles', json={'name': 'Pedro', 'department_id': a['id'], 'position_id': p['id']}).status_code == 422
    api_client.patch(f"/api/departments/{b['id']}", json={'active': False})
    assert api_client.post('/api/positions', json={'name': 'N1', 'department_id': b['id']}).status_code == 422


def test_escalation_without_requester_cross_department_snapshot(api_client, ticket_payload):
    a, b, p, q = catalogs(api_client)
    person = post(api_client, '/api/responsibles', {'name': 'Ángel', 'department_id': b['id'], 'position_id': q['id']})
    reason = post(api_client, '/api/escalation-reasons', {'name': 'Apoyo'})
    ticket = post(api_client, '/api/tickets', ticket_payload)
    path = f"/api/tickets/{ticket['id']}/escalations"
    body = {'recipient_id': person['id'], 'reason_id': reason['id'], 'description': 'Revisar enlace'}
    item = post(api_client, path, body)
    assert item['requester_id'] is None and item['requester'] is None
    assert item['recipient_position_name'] == 'Supervisor'
    assert item['recipient_department_name'] == 'Red Externa'
    assert item['recipient_level'] is None
    api_client.patch(f"/api/positions/{q['id']}", json={'name': 'Fusionador'})
    api_client.patch(f"/api/departments/{b['id']}", json={'name': 'Campo'})
    api_client.patch(f"/api/responsibles/{person['id']}", json={'department_id': None, 'position_id': None})
    historical = api_client.get(path).json()[0]
    assert historical['recipient_position_name'] == 'Supervisor'
    assert historical['recipient_department_name'] == 'Red Externa'
    no_position = post(api_client, path, {**body, 'requester_id': None})
    assert no_position['recipient_position_name'] is None
    assert no_position['recipient_department_name'] is None
    assert api_client.get(f"/api/tickets/{ticket['id']}").json() == ticket
    stats = api_client.get('/api/escalations/summary', params={'recipient_id': person['id']}).json()
    assert stats['escalated_tickets'] == 1 and stats['events'] == 2
    assert stats['active'] == 2
    assert api_client.post(f"/api/tickets/{ticket['id']}/updates", json={'content': 'Intervención', 'responsible_id': person['id'], 'escalation_id': item['id']}).status_code == 201


def test_legacy_level_remains_readonly(api_client, db_session):
    person = post(api_client, '/api/responsibles', {'name': 'Histórico'})
    db_session.execute(text('UPDATE responsibles SET attention_level=:value WHERE id=:id'), {'value': 'N2 anterior', 'id': person['id']})
    db_session.commit()
    result = api_client.get(f"/api/responsibles/{person['id']}").json()
    assert result['attention_level'] == 'N2 anterior' and result['position'] is None
    assert api_client.patch(f"/api/responsibles/{person['id']}", json={'attention_level': 'Otro'}).status_code == 422
    assert api_client.patch(f"/api/responsibles/{person['id']}", json={'name': 'Renombrado'}).json()['attention_level'] == 'N2 anterior'
