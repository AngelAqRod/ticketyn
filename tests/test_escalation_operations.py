from datetime import datetime, timedelta, timezone
from sqlalchemy import text
import pytest
from test_escalations import setup
from test_ticket_exports import pdf_strings


def test_operational_dates_destination_audit_and_closed_ticket(api_client, ticket_payload):
    ticket, _, recipient, reason, _ = setup(api_client, ticket_payload)
    closed = api_client.patch(f"/api/tickets/{ticket['id']}", json={'status': 'CLOSED', 'end_at': '2020-01-01T13:00:00Z'}).json()
    path = f"/api/tickets/{ticket['id']}/escalations"
    response = api_client.post(path, json={'department_id': recipient['department_id'], 'reason_id': reason['id'], 'description': 'Apoyo', 'started_at': '2026-10-12T08:00:00-06:00'})
    assert response.status_code == 201, response.text
    item = response.json(); created = item['created_at']
    assert item['recipient'] is None and item['requester'] is None
    assert api_client.patch(f"{path}/{item['id']}", json={'recipient_id': recipient['id']}).status_code == 200
    assert api_client.post(f"{path}/{item['id']}/finish", json={'finished_at': '2026-10-12T07:59:00-06:00'}).status_code == 422
    finished = api_client.post(f"{path}/{item['id']}/finish", json={'finished_at': '2026-10-12T09:30:00-06:00'}).json()
    assert finished['created_at'] == created
    corrected = api_client.patch(f"{path}/{item['id']}", json={'started_at': '2026-10-12T07:30:00-06:00', 'recipient_id': None}).json()
    assert corrected['created_at'] == created and corrected['updated_at'] >= item['updated_at']
    audit = api_client.get(f"{path}/{item['id']}/audit").json()
    assert [row['event'] for row in audit] == ['created', 'updated', 'finished', 'updated']
    assert all(row['actor'] is None for row in audit)
    assert audit[-1]['changes']['started_at']['before'] != audit[-1]['changes']['started_at']['after']
    assert api_client.get(f"/api/tickets/{ticket['id']}").json() == closed
    for field in ('created_at', 'updated_at', 'actor'):
        assert api_client.patch(f"{path}/{item['id']}", json={field: created}).status_code == 422
    assert api_client.get(f'/api/tickets/999999/escalations/{item["id"]}/audit').status_code == 404


def test_destination_membership_and_assignment(api_client, ticket_payload):
    ticket, _, person, reason, values = setup(api_client, ticket_payload)
    other = api_client.post('/api/departments', json={'name': 'Red externa'}).json()['id']
    path = f"/api/tickets/{ticket['id']}/escalations"
    assert api_client.post(path, json={**values, 'department_id': other}).status_code == 422
    assert api_client.post(path, json={'reason_id': reason['id'], 'description': 'Sin destino'}).status_code == 422
    item = api_client.post(path, json={**values, 'department_id': person['department_id']}).json()
    assert api_client.patch(f"{path}/{item['id']}", json={'department_id': other}).status_code == 422
    changed = api_client.patch(f"{path}/{item['id']}", json={'department_id': other, 'recipient_id': None}).json()
    assert changed['department_id'] == other and changed['recipient'] is None
    assert api_client.post(f"{path}/{item['id']}/finish", json={}).status_code == 200


@pytest.mark.parametrize('days', [1, 7, 15, 30])
def test_coverage_and_events_separate_populations(api_client, ticket_payload, db_session, days):
    ticket, _, person, reason, values = setup(api_client, ticket_payload)
    start = datetime(2026, 10, 12, 6, tzinfo=timezone.utc)
    end = start + timedelta(days=days)
    ids = [ticket['id']] + [api_client.post('/api/tickets', json=ticket_payload).json()['id'] for _ in range(12)]
    for id in ids:
        db_session.execute(text('UPDATE tickets SET start_at=:start WHERE id=:id'), {'start': start, 'id': id})
    old = api_client.post('/api/tickets', json=ticket_payload).json()['id']
    db_session.commit()
    for id in [*ids[:6], ids[0], old]:
        response = api_client.post(f'/api/tickets/{id}/escalations', json={**values, 'started_at': start.isoformat()})
        assert response.status_code == 201, response.text
        assert api_client.post(f"/api/tickets/{id}/escalations/{response.json()['id']}/finish", json={'finished_at': (start+timedelta(minutes=90)).isoformat()}).status_code == 200
    for instant in (start-timedelta(microseconds=1), end):
        assert api_client.post(f'/api/tickets/{ids[7]}/escalations', json={**values, 'started_at': instant.isoformat()}).status_code == 201
    response = api_client.post(f'/api/tickets/{old}/escalations', json={'department_id': person['department_id'], 'reason_id': reason['id'], 'description': 'Sin técnico', 'started_at': start.isoformat()})
    assert response.status_code == 201
    query = {'from': start.isoformat(), 'to': end.isoformat(), 'timezone': 'America/Guatemala'}
    data = api_client.get('/api/escalations/summary', params=query).json()
    assert data['total_tickets'] == 13 and data['escalated_tickets'] == 6
    assert data['escalated_percentage'] == pytest.approx(46.153846)
    assert data['events'] == 9 and data['event_tickets'] == 7
    assert data['finished'] == 8 and data['active'] == 1
    assert data['average_duration_seconds'] == 5400
    assert sum(row['count'] for row in data['trend']) == 9
    assert sum(row['count'] for row in data['recipients']) == 9
    assert next(row for row in data['recipients'] if row['id'] is None)['count'] == 1
    assert data['departments'][0]['count'] == 9
    filtered = api_client.get('/api/escalations/summary', params={**query, 'department_id': person['department_id'], 'recipient_id': person['id'], 'reason_id': reason['id'], 'status': 'FINISHED'}).json()
    assert filtered['events'] == 8 and filtered['escalated_tickets'] == 6
    assert api_client.get('/api/reports/summary', params=query).json()['escalations'] == data


def test_default_dates_and_unchanged_snapshot(api_client, ticket_payload):
    ticket, _, person, _, values = setup(api_client, ticket_payload)
    before = datetime.now(timezone.utc)
    path = f"/api/tickets/{ticket['id']}/escalations"
    item = api_client.post(path, json=values).json()
    assert datetime.fromisoformat(item['started_at']) >= before
    assert item['updated_at'] == item['created_at']
    api_client.patch(f"/api/positions/{person['position_id']}", json={'name': 'Puesto cambiado'})
    changed = api_client.patch(f"{path}/{item['id']}", json={'recipient_id': item['recipient_id'], 'department_id': item['department_id']}).json()
    assert changed == item
    assert len(api_client.get(f"{path}/{item['id']}/audit").json()) == 1
    assert api_client.patch(f"{path}/{item['id']}", json={'finished_at': datetime.now(timezone.utc).isoformat()}).status_code == 422
    assert api_client.patch(f"{path}/{item['id']}", json={'started_at': '2026-10-12T08:00:00'}).status_code == 422


def test_nullable_recipient_exports_and_customer_privacy(api_client, ticket_payload, pdf_strings):
    from io import BytesIO
    from openpyxl import load_workbook
    ticket, _, person, reason, _ = setup(api_client, ticket_payload)
    path = f"/api/tickets/{ticket['id']}/escalations"
    body = {'department_id': person['department_id'], 'reason_id': reason['id'], 'description': 'SOLICITUD-PRIVADA-031', 'started_at': '2026-10-12T08:00:00-06:00'}
    item = api_client.post(path, json=body).json()
    assert api_client.post(f"{path}/{item['id']}/finish", json={'finished_at': '2026-10-12T09:30:00-06:00'}).status_code == 200
    assert api_client.get(f"/api/tickets/{ticket['id']}/reports/internal/pdf").status_code == 200
    assert 'SOLICITUD-PRIVADA-031' in ' '.join(pdf_strings)
    pdf_strings.clear()
    assert api_client.get(f"/api/tickets/{ticket['id']}/reports/customer/pdf").status_code == 200
    assert 'SOLICITUD-PRIVADA-031' not in ' '.join(pdf_strings)
    filters = {'from': '2026-10-12T00:00:00-06:00', 'to': '2026-10-13T00:00:00-06:00', 'timezone': 'America/Guatemala'}
    response = api_client.get('/api/reports/export/xlsx', params=filters)
    assert response.status_code == 200
    workbook = load_workbook(BytesIO(response.content))
    assert workbook['Escalamientos por persona']['B2'].value == 'Sin responsable asignado'
    assert workbook['Escalamientos por departamento']['B2'].value == 'Especialistas'
    assert dict(list(workbook['Escalamientos'].values)[1:])['Duración promedio (segundos)'] == 5400
    workbook.close()
    assert api_client.get('/api/reports/export/pdf', params=filters).status_code == 200
