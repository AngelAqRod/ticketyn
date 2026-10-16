import re
import pytest
from sqlalchemy import event
from test_internal_tickets import payload
from test_ticket_exports import pdf_strings


def report(client, id, **params):
    return client.get(f'/api/internal-tickets/{id}/reports/internal/pdf', params=params)


@pytest.mark.parametrize('closed', [False, True])
@pytest.mark.parametrize('assigned', [False, True])
def test_individual_report_optional_classification(api_client, closed, assigned, pdf_strings):
    p = payload(api_client)
    if assigned:
        p['provider_id'] = api_client.post('/api/providers', json={'name':'Transporte histórico'}).json()['id']
        p['node_id'] = api_client.post('/api/nodes', json={'name':'Nodo NOC'}).json()['id']
        p['resolution'] = 'Servicio restablecido'
    if closed:
        p.update(status='CLOSED', end_at='2026-10-15T10:00:00-06:00')
    item = api_client.post('/api/internal-tickets', json=p).json()
    if assigned:
        api_client.patch(f"/api/providers/{p['provider_id']}", json={'active':False})
    before = api_client.get(f"/api/internal-tickets/{item['id']}").json()
    response = report(api_client, item['id'], timezone='America/Guatemala')
    assert response.status_code == 200, response.text
    assert response.content.startswith(b'%PDF-') and b'%%EOF' in response.content
    assert response.headers['content-type'] == 'application/pdf'
    assert f"Ticket_Interno_{item['id']}.pdf" in response.headers['content-disposition']
    assert response.headers['cache-control'] == 'no-store'
    text = ' '.join(pdf_strings)
    for word in ['Reporte interno de incidencia', item['reference'], p['title'], p['description'], '15/10/2026 08:00:00 -0600', 'Sin tickets de clientes relacionados', 'Sin escalamientos registrados.']:
        assert word in text
    assert ('Cambio de resolución documentada' if assigned else 'Sin intervenciones registradas.') in text
    assert ('Duración del incidente' if closed else 'Tiempo transcurrido al emitir') in text
    if closed: assert '2 h' in text
    assert ('Transporte histórico' if assigned else 'Ninguno') in text
    assert ('Servicio restablecido' if assigned else 'Sin resolución documentada.') in text
    if assigned: assert 'Nodo NOC' in text
    for forbidden in ['Contenido autorizado', 'Visible para cliente', 'Seguimiento público', 'Descripción autorizada', 'Circuito']:
        assert forbidden not in text
    assert api_client.get(f"/api/internal-tickets/{item['id']}").json() == before


def test_complete_histories_and_related_no_pagination(api_client, ticket_payload, db_session, pdf_strings):
    p = payload(api_client)
    p['description'] = 'Descripción extensa con saltos\n' * 250
    item = api_client.post('/api/internal-tickets', json=p).json()
    id = item['id']
    reason = api_client.post('/api/escalation-reasons', json={'name':'Apoyo de transporte'}).json()
    escalation = api_client.post(f'/api/internal-tickets/{id}/escalations', json={'department_id':p['department_id'], 'reason_id':reason['id'], 'description':'Diagnóstico de transporte', 'started_at':p['start_at']})
    assert escalation.status_code == 201, escalation.text
    for index in range(55):
        result = api_client.post(f'/api/internal-tickets/{id}/updates', json={'content':f'Intervención única {index:03} ' + ('Texto extenso\n' * 30), 'escalation_id':escalation.json()['id']})
        assert result.status_code == 201, result.text
    for index in range(52):
        result = api_client.post('/api/tickets', json={**ticket_payload, 'internal_ticket_id':id, 'title':f'Cliente vinculado {index:03}'})
        assert result.status_code == 201, result.text
    queries=[]
    def capture(_conn,_cursor,statement,*_): queries.append(statement)
    engine=db_session.get_bind(); event.listen(engine,'before_cursor_execute',capture)
    try:
        response=report(api_client,id)
    finally: event.remove(engine,'before_cursor_execute',capture)
    assert response.status_code==200,response.text
    assert len(queries)<12
    text=' '.join(pdf_strings)
    for word in ['Intervención única 000','Intervención única 054','Cliente vinculado 000','Cliente vinculado 051','Total: 52','Diagnóstico de transporte','Apoyo de transporte']:
        assert word in text
    assert 'Pública' not in text and 'Visible para cliente' not in text
    assert len(re.findall(rb'/Type\s*/Page\b',response.content))>3


def test_report_validation_and_safe_errors(api_client, monkeypatch):
    assert report(api_client,999999).status_code==404
    assert report(api_client,0).status_code==422
    assert report(api_client,1,timezone='invalid/zone').status_code==422
    from ticketyn.api import internal_tickets
    def fail(*args): raise RuntimeError('SQL SECRET')
    monkeypatch.setattr(internal_tickets,'internal_ticket_pdf',fail)
    response=report(api_client,1)
    assert response.status_code==500 and 'SQL SECRET' not in response.text
