from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import select, text
from ticketyn.models import TicketEscalation


def setup(client, payload):
    requester = client.post('/api/responsibles', json={'name': 'Pedro'}).json()
    department = client.post('/api/departments', json={'name': 'Especialistas'}).json()
    position = client.post('/api/positions', json={'name': 'Especialista BGP', 'department_id': department['id']}).json()
    recipient = client.post('/api/responsibles', json={'name': 'Ángel', 'department_id': department['id'], 'position_id': position['id']}).json()
    reason = client.post('/api/escalation-reasons', json={'name': 'Apoyo técnico', 'description': 'Solicitar colaboración'}).json()
    ticket = client.post('/api/tickets', json={**payload, 'responsible_id': requester['id']}).json()
    values = dict(requester_id=requester['id'], recipient_id=recipient['id'], reason_id=reason['id'], description='Revisar BGP IPv6')
    return ticket, requester, recipient, reason, values


def test_escalation_independent_and_historical(api_client, ticket_payload):
    ticket, requester, recipient, reason, values = setup(api_client, ticket_payload)
    path = f"/api/tickets/{ticket['id']}/escalations"
    first = api_client.post(path, json=values)
    assert first.status_code == 201, first.text
    item = first.json()
    assert item['status'] == 'ACTIVE' and item['finished_at'] is None
    assert item['recipient_position_name'] == 'Especialista BGP'
    assert item['requester']['name'] == 'Pedro'
    assert api_client.get(f"/api/tickets/{ticket['id']}").json() == ticket
    api_client.patch(f"/api/positions/{recipient['position_id']}", json={'name': 'Director'})
    api_client.patch(f"/api/escalation-reasons/{reason['id']}", json={'active': False})
    assert api_client.get(path).json()[0]['recipient_position_name'] == 'Especialista BGP'
    assert api_client.get(path).json()[0]['reason']['active'] is False
    assert api_client.post(path, json=values).status_code == 422
    api_client.patch(f"/api/escalation-reasons/{reason['id']}", json={'active': True})
    assert api_client.post(path, json=values).status_code == 201
    api_client.patch(f"/api/tickets/{ticket['id']}", json={'responsible_id': recipient['id']})
    assert len(api_client.get(path).json()) == 2  # Reassignment does not escalate.
    finished = api_client.post(path + f"/{item['id']}/finish", json={})
    assert finished.status_code == 200, finished.text
    assert finished.json()['status'] == 'FINISHED'
    assert finished.json()['finished_at'] >= item['created_at']
    assert api_client.post(path + f"/{item['id']}/finish").json() == finished.json()
    assert len(api_client.get(path).json()) == 2
    assert api_client.get(f"/api/tickets/{ticket['id']}").json()['department_id'] == ticket['department_id']
    assert api_client.get(f"/api/tickets/{ticket['id']}").json()['status'] == ticket['status']


@pytest.mark.parametrize('field,value,status', [('requester_id', 99999, 404), ('recipient_id', 99999, 404), ('reason_id', 99999, 404), ('description', ' ', 422), ('description', 'x'*10001, 422), ('recipient_id', 0, 422)])
def test_invalid_escalation(api_client, ticket_payload, field, value, status):
    ticket, _, _, _, values = setup(api_client, ticket_payload)
    assert api_client.post(f"/api/tickets/{ticket['id']}/escalations", json={**values, field: value}).status_code == status


def test_inactive_relations_missing_ticket_and_closed_ticket(api_client, ticket_payload):
    ticket, requester, recipient, reason, values = setup(api_client, ticket_payload)
    assert api_client.post('/api/tickets/99999/escalations', json=values).status_code == 404
    for person in [requester, recipient]:
        api_client.patch(f"/api/responsibles/{person['id']}", json={'active': False})
        assert api_client.post(f"/api/tickets/{ticket['id']}/escalations", json=values).status_code == 422
        api_client.patch(f"/api/responsibles/{person['id']}", json={'active': True})
    closed = api_client.patch(f"/api/tickets/{ticket['id']}", json={'status': 'CLOSED', 'end_at': '2020-01-01T13:00:00Z'}).json()
    path = f"/api/tickets/{ticket['id']}/escalations"
    result = api_client.post(path, json=values)
    assert result.status_code == 201
    assert api_client.post(path + f"/{result.json()['id']}/finish").status_code == 200
    assert api_client.get(f"/api/tickets/{ticket['id']}").json() == closed


def test_linked_interventions(api_client, ticket_payload):
    ticket, _, _, _, values = setup(api_client, ticket_payload)
    id = api_client.post(f"/api/tickets/{ticket['id']}/escalations", json=values).json()['id']
    path = f"/api/tickets/{ticket['id']}/updates"
    body = {'content': 'Ruta corregida', 'escalation_id': id, 'occurred_at': '2010-01-01T00:00:00-06:00'}
    result = api_client.post(path, json=body)
    assert result.status_code == 201, result.text
    assert result.json()['escalation_id'] == id
    api_client.post(path, json={'content': 'Intervención independiente'})
    assert len(api_client.get(path).json()) == 2
    assert len(api_client.get(path, params={'escalation_id': id}).json()) == 1
    other = api_client.post('/api/tickets', json=ticket_payload).json()['id']
    assert api_client.post(f'/api/tickets/{other}/updates', json=body).status_code == 422
    assert api_client.post(path, json={**body, 'escalation_id': 99999}).status_code == 422


def test_reason_catalog_and_level(api_client):
    path = '/api/escalation-reasons'
    item = api_client.post(path, json={'name': 'Autorización'}).json()
    assert api_client.post(path, json={'name': 'Autorización'}).status_code == 409
    assert api_client.get(path, params={'search': 'toriz'}).json()[0]['id'] == item['id']
    assert api_client.patch(f"{path}/{item['id']}", json={'active': False, 'description': 'Detalle'}).status_code == 200
    assert api_client.get(path).json() == []
    assert api_client.get(path, params={'include_inactive': True}).json()[0]['description'] == 'Detalle'
    assert api_client.patch(f"{path}/{item['id']}", json={'active': True, 'description': None}).status_code == 200
    assert api_client.get(path + '/99999').status_code == 404
    assert api_client.delete(f"{path}/{item['id']}").status_code == 405
    assert api_client.post('/api/responsibles', json={'name': 'Prueba', 'attention_level': 'x'*101}).status_code == 422
    person = api_client.post('/api/responsibles', json={'name': 'Director'}).json()
    assert api_client.patch(f"/api/responsibles/{person['id']}", json={'attention_level': None}).status_code == 422


def test_statistics_unique_tickets_events_duration_boundaries(api_client, ticket_payload, db_session):
    ticket, _, recipient, _, values = setup(api_client, ticket_payload)
    second = api_client.post('/api/tickets', json=ticket_payload).json()['id']
    third = api_client.post('/api/tickets', json=ticket_payload).json()['id']
    start = datetime(2026, 10, 9, 6, tzinfo=timezone.utc)  # Guatemala local midnight.
    for ticket_id, delta, finished in [(ticket['id'], 0, True), (ticket['id'], 1, False), (second, 2, True), (third, 24, False), (third, -1, False)]:
        response = api_client.post(f'/api/tickets/{ticket_id}/escalations', json=values)
        assert response.status_code == 201
        item = db_session.get(TicketEscalation, response.json()['id'])
        item.created_at = start + timedelta(hours=delta)
        if finished:
            item.status = 'FINISHED'; item.finished_at = item.created_at + timedelta(hours=2)
        db_session.commit()
    query = {'from': start.isoformat(), 'to': (start+timedelta(days=1)).isoformat(), 'timezone': 'America/Guatemala', 'recipient_id': recipient['id']}
    response = api_client.get('/api/escalations/summary', params=query)
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data['escalated_tickets'], data['events'], data['active'], data['finished']) == (2, 3, 1, 2)
    assert data['average_duration_seconds'] == 7200
    assert data['total_tickets'] == 3
    assert data['escalated_percentage'] == pytest.approx(200/3)
    assert len(data['trend']) == 24 and sum(x['count'] for x in data['trend']) == 3
    assert data['recipients'][0]['count'] == 3
    assert {x['id'] for x in api_client.get('/api/escalations/tickets', params=query).json()} == {ticket['id'], second}
    assert api_client.get('/api/escalations/summary', params={**query, 'responsible_id': recipient['id']}).json()['events'] == 0  # Recipient is not principal.
    assert api_client.get('/api/escalations/summary', params={'from': start.isoformat()}).status_code == 422
    assert api_client.get('/api/escalations/summary', params={'timezone': 'Invalid/Zone'}).status_code == 422
    all_data = api_client.get('/api/escalations/summary', params={'timezone': 'America/Guatemala'}).json()
    assert all_data['events'] == 5
    assert sum(bucket['count'] for bucket in all_data['trend']) == 5
