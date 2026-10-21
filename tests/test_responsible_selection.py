import pytest
from test_fms import operation_payload
from test_changes import payload as change_payload
from test_internal_tickets import payload as internal_payload


def unavailable(client, id):
    r=client.patch(f'/api/responsibles/{id}',json={'operational_selectable':False})
    assert r.status_code==200,r.text


@pytest.mark.parametrize('path,extra', [('/api/activations',{}),('/api/capacity-changes',{'operation_type':'INCREASE','new_capacity':'200','new_unit':'Mbps'}),('/api/circuit-lifecycle',{'operation_type':'REACTIVATE'})])
def test_fms_rejects_new_unavailable_assignments(api_client,operation_payload,path,extra):
    unavailable(api_client,operation_payload['responsible_id'])
    r=api_client.post(path,json={**operation_payload,**extra})
    assert r.status_code==422,r.text
    assert 'asignaciones' in r.text


def test_fms_existing_and_new_interventions(api_client,operation_payload):
    c=api_client
    activation=c.post('/api/activations',json=operation_payload).json()
    unavailable(c,operation_payload['responsible_id'])
    assert c.get(f"/api/activations/{activation['id']}").json()['responsible_id']==operation_payload['responsible_id']
    assert c.post(f"/api/activations/{activation['id']}/interventions",json={'responsible_id':operation_payload['responsible_id'],'occurred_at':operation_payload['effective_at'],'content':'Una intervención'}).status_code==422
    assert c.get('/api/activations',params={'responsible_id':operation_payload['responsible_id']}).json()


@pytest.mark.parametrize('internal',[False,True])
def test_tickets_keep_historical_but_reject_changed_assignment(api_client,ticket_payload,internal):
    c=api_client
    person=c.post('/api/responsibles',json={'name':'Asignado histórico'}).json()['id']
    other=c.post('/api/responsibles',json={'name':'No asignable'}).json()['id']
    path='/api/internal-tickets' if internal else '/api/tickets'
    p=internal_payload(c) if internal else ticket_payload
    r=c.post(path,json={**p,'responsible_id':person}); assert r.status_code==201,r.text
    item=r.json()
    unavailable(c,person);unavailable(c,other)
    # An explicit unchanged id is also valid; ordinary editors submit complete values.
    r=c.patch(f"{path}/{item['id']}",json={'title':'Corrección de título','responsible_id':person})
    assert r.status_code==200,r.text
    assert r.json()['responsible_id']==person
    assert c.patch(f"{path}/{item['id']}",json={'responsible_id':other}).status_code==422
    assert c.post(path,json={**p,'responsible_id':person}).status_code==422
    assert c.get(path,params={'responsible_id':person}).json()
    assert c.post(f"{path}/{item['id']}/updates",json={'responsible_id':person,'content':'Seguimiento','occurred_at':'2026-10-20T12:00:00Z'}).status_code==422


def test_changes_retained_manager_and_support_then_reject_reassignment(api_client):
    c=api_client;p=change_payload(c)
    support=c.post('/api/responsibles',json={'name':'Apoyo histórico'}).json()['id']
    other=c.post('/api/responsibles',json={'name':'Nuevo no disponible'}).json()['id']
    r=c.post('/api/changes',json={**p,'support_ids':[support]}); assert r.status_code==201,r.text
    id=r.json()['id']
    for pid in (p['manager_id'],support,other):unavailable(c,pid)
    r=c.patch(f'/api/changes/{id}',json={'title':'Título corregido','manager_id':p['manager_id'],'support_ids':[support]})
    assert r.status_code==200,r.text
    assert r.json()['manager_name']=='Encargado cambios' and r.json()['support'][0]['id']==support
    assert c.patch(f'/api/changes/{id}',json={'support_ids':[other]}).status_code==422
    assert c.patch(f'/api/changes/{id}',json={'manager_id':other}).status_code==422
    assert c.post(f'/api/changes/{id}/updates',json={'responsible_id':support,'content':'Seguimiento','occurred_at':'2026-10-20T12:00:00Z'}).status_code==422


@pytest.mark.parametrize('internal',[False,True])
def test_escalations_reject_new_requester_or_recipient(api_client,ticket_payload,internal):
    c=api_client
    path='/api/internal-tickets' if internal else '/api/tickets'
    item=c.post(path,json=internal_payload(c) if internal else ticket_payload).json()
    area=c.post('/api/departments',json={'name':'Área técnica'}).json()['id']
    person=c.post('/api/responsibles',json={'name':'Técnico no disponible','department_id':area}).json()['id']
    reason=c.post('/api/escalation-reasons',json={'name':'Apoyo'}).json()['id']
    p={'department_id':area,'recipient_id':person,'reason_id':reason,'description':'Revisar'}
    response=c.post(f"{path}/{item['id']}/escalations",json=p);assert response.status_code==201,response.text
    unavailable(c,person)
    assert c.patch(f"{path}/{item['id']}/escalations/{response.json()['id']}",json={'started_at':'2026-10-19T12:00:00Z'}).status_code==200
    assert c.post(f"{path}/{item['id']}/escalations",json=p).status_code==422
    assert c.post(f"{path}/{item['id']}/escalations",json={**p,'recipient_id':None,'requester_id':person}).status_code==422
