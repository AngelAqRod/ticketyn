from datetime import datetime, timedelta, timezone
from io import BytesIO

from openpyxl import load_workbook
from sqlalchemy import text
from test_ticket_exports import pdf_strings
from test_escalations import setup


def test_internal_history_snapshots_links_customer_privacy(api_client, ticket_payload, db_session, pdf_strings):
    ticket, _, recipient, _, values = setup(api_client, ticket_payload)
    path = f"/api/tickets/{ticket['id']}"
    a = api_client.post(path + '/escalations', json=values).json()
    b = api_client.post(path + '/escalations', json={**values, 'requester_id': None, 'description': 'Escalamiento segundo'}).json()
    api_client.post(path + f"/escalations/{a['id']}/finish")
    api_client.patch(f"/api/positions/{recipient['position_id']}", json={'name': 'PUESTO-ACTUAL-NO-SNAPSHOT'})
    api_client.patch(f"/api/departments/{recipient['department_id']}", json={'name': 'DEPTO-ACTUAL-NO-SNAPSHOT'})
    for visibility, content in [('INTERNAL', 'PRIVADO-ESC-UPDATE'), ('PUBLIC', 'PUBLICO-ESC-UPDATE')]:
        assert api_client.post(path + '/updates', json={'content': content, 'visibility': visibility, 'escalation_id': a['id'], 'responsible_id': recipient['id'], 'occurred_at': '2020-01-01T00:00:00Z'}).status_code == 201
    result = api_client.get(path + '/reports/internal/pdf', params={'timezone': 'America/Guatemala'})
    assert result.status_code == 200
    words = ' '.join(pdf_strings)
    assert 'Historial de escalamientos' in words
    assert 'Especialista BGP' in words and 'Especialistas' in words
    assert 'PUESTO-ACTUAL-NO-SNAPSHOT' not in words and 'DEPTO-ACTUAL-NO-SNAPSHOT' not in words
    assert f"Escalamiento #{a['id']}" in words and f"Escalamiento #{b['id']}" in words
    assert 'Activo' in words and 'Finalizado' in words and 'Duración:' in words
    assert words.count('PRIVADO-ESC-UPDATE') == 1 and words.count('PUBLICO-ESC-UPDATE') == 1
    assert words.index('Revisar BGP IPv6') < words.index('Escalamiento segundo')
    pdf_strings.clear()
    assert api_client.get(path + '/reports/customer/pdf').status_code == 200
    words = ' '.join(pdf_strings)
    assert 'PUBLICO-ESC-UPDATE' in words
    for private in ('Escalamiento #', 'Historial de escalamientos', 'PRIVADO-ESC-UPDATE', 'Especialistas', 'Especialista BGP', 'Ángel', 'Apoyo técnico'):
        assert private not in words


def test_internal_empty_escalations(api_client, ticket_payload, pdf_strings):
    ticket = api_client.post('/api/tickets', json=ticket_payload).json()
    assert api_client.get(f"/api/tickets/{ticket['id']}/reports/internal/pdf").status_code == 200
    assert 'Sin escalamientos registrados.' in ' '.join(pdf_strings)


def test_large_escalation_description_is_complete_and_paginated(api_client, ticket_payload, pdf_strings):
    ticket, _, _, _, body = setup(api_client, ticket_payload)
    content = '\n'.join(f'LINEA-ESC-{n:03} · <técnico> & intervención' for n in range(150))
    assert api_client.post(f"/api/tickets/{ticket['id']}/escalations", json={**body, 'description': content}).status_code == 201
    response = api_client.get(f"/api/tickets/{ticket['id']}/reports/internal/pdf")
    assert response.status_code == 200
    words = ' '.join(pdf_strings)
    assert 'LINEA-ESC-000' in words and 'LINEA-ESC-149' in words
    assert 'Página 2 /' in words


def test_report_shared_statistics_period_exports(api_client, ticket_payload, db_session, pdf_strings):
    ticket, _, recipient, reason, values = setup(api_client, ticket_payload)
    start = datetime(2020, 1, 1, 6, tzinfo=timezone.utc)
    ids = []
    for delta in (0, 1, 24, -1):
        result = api_client.post(f"/api/tickets/{ticket['id']}/escalations", json={**values, 'requester_id': None}).json()
        ids.append(result['id'])
        db_session.execute(text('UPDATE ticket_escalations SET created_at=:start WHERE id=:id'), {'start': start + timedelta(hours=delta), 'id': result['id']})
    db_session.execute(text("UPDATE ticket_escalations SET status='FINISHED', finished_at=created_at + interval '2 hours' WHERE id=:id"), {'id': ids[0]})
    db_session.commit()
    filters = {'from': start.isoformat(), 'to': (start + timedelta(days=1)).isoformat(), 'timezone': 'America/Guatemala', 'recipient_id': recipient['id']}
    data = api_client.get('/api/reports/summary', params=filters).json()
    direct = api_client.get('/api/escalations/summary', params=filters).json()
    assert data['escalations'] == direct
    assert (direct['events'], direct['escalated_tickets'], direct['active'], direct['finished']) == (2, 1, 1, 1)
    assert direct['average_duration_seconds'] == 7200
    assert sum(row['count'] for row in direct['trend']) == 2
    other = api_client.post('/api/responsibles', json={'name': 'Sin escalamientos'}).json()['id']
    excluded = api_client.get('/api/reports/summary', params={**filters, 'recipient_id': other}).json()
    assert excluded['kpis'] == data['kpis']  # Recipient never scopes incident statistics.
    assert excluded['escalations']['events'] == 0
    response = api_client.get('/api/reports/export/xlsx', params=filters)
    assert response.status_code == 200, response.text
    workbook = load_workbook(BytesIO(response.content))
    rows = dict(list(workbook['Escalamientos'].values)[1:])
    assert rows['Eventos totales de escalamiento'] == 2
    assert rows['Tickets únicos escalados'] == 1
    assert rows['Duración promedio (segundos)'] == 7200
    assert workbook['Escalamientos por persona']['C2'].value == 2
    assert sum(row[1] for row in list(workbook['Evolución escalamientos'].values)[1:]) == 2
    workbook.close()
    assert api_client.get('/api/reports/export/pdf', params=filters).status_code == 200
    words = ' '.join(pdf_strings)
    assert 'Estadísticas de escalamientos' in words and 'Escalamientos recibidos por persona' in words
    assert 'Evolución de escalamientos' in words and recipient['name'] in words
    for fmt in ('pdf', 'xlsx'):
        assert api_client.get(f'/api/reports/export/{fmt}', params={'timezone': 'America/Guatemala'}).status_code == 200
    all_time = api_client.get('/api/reports/summary', params={'timezone': 'America/Guatemala'}).json()
    assert all_time['escalations']['events'] == 4
    assert all_time['period']['from_at'] is None and all_time['period']['to_exclusive'] is None
    assert sum(row['count'] for row in all_time['trend']) == all_time['kpis']['started']


def test_all_time_closed_without_end_keeps_original_duration_semantics(api_client, ticket_payload, db_session):
    # Historical CLOSED without Fin never contributes to valid closure metrics.
    ticket = api_client.post('/api/tickets', json=ticket_payload).json()
    db_session.execute(text("UPDATE tickets SET status='CLOSED' WHERE id=:id"), {'id': ticket['id']})
    db_session.commit()
    data = api_client.get('/api/reports/summary').json()
    assert data['kpis']['started'] == 1
    assert data['kpis']['closed'] == 0
    assert data['kpis']['average_duration_seconds'] is None
