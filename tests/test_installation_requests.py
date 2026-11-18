from datetime import datetime, timezone
from ticketyn.models.installation_orders import InstallationRequest, InstallationOrder
from sqlalchemy import select, func


def intake(db_session):
    item=InstallationRequest(mailbox='orders@example.test',folder='INBOX',uidvalidity=1,uid=1,checksum='a'*64,sender='sender@example.test',subject='Install',body='Please install',received_at=datetime.now(timezone.utc))
    db_session.add(item); db_session.commit()
    return item.id


def test_draft_process_and_duplicate(api_client,db_session,ticket_payload):
    id=intake(db_session)
    base=f'/api/installation-requests/{id}'
    response=api_client.put(base+'/draft',json={'version':0,'data':{'notes':'Incomplete'}})
    assert response.status_code==200,response.text
    assert response.json()['draft']['version']==1
    assert api_client.put(base+'/draft',json={'version':0,'data':{}}).status_code==409
    assert db_session.scalar(select(func.count()).select_from(InstallationOrder))==0
    payload={'version':1,'order_type':'NORMAL','customer_id':ticket_payload['customer_id'],'circuit_id':ticket_payload['circuit_id'],'requested_at':'2026-10-28T12:00:00-06:00'}
    response=api_client.post(base+'/process',json=payload)
    assert response.status_code==201,response.text
    assert response.json()['source_request_id']==id and response.json()['order_type']=='NORMAL'
    assert api_client.post(base+'/process',json=payload).status_code==409
    assert db_session.scalar(select(func.count()).select_from(InstallationOrder))==1
    assert api_client.get(base).json()['state']=='PROCESSED'
    assert api_client.get('/api/installation-requests/summary').json()['processed']==1


def test_discard_requires_reason_and_closed_state(api_client,db_session):
    id=intake(db_session); base=f'/api/installation-requests/{id}'
    assert api_client.post(base+'/review').status_code==200
    assert api_client.post(base+'/discard',json={'reason':' '}).status_code==422
    assert api_client.post(base+'/discard',json={'reason':'Not an installation'}).status_code==200
    assert api_client.post(base+'/review').status_code==409
    assert api_client.get(base).json()['discard_reason']=='Not an installation'


def test_process_extraordinary_request_and_failed_validation_keeps_request_open(api_client,db_session,ticket_payload):
    service=api_client.post('/api/service-types',json={'name':'Internet extraordinario'}).json()['id']
    id=intake(db_session); base=f'/api/installation-requests/{id}'
    incomplete={'version':0,'order_type':'EXTRAORDINARY','customer_id':ticket_payload['customer_id'],'description':'Instalación especial','requested_at':'2026-10-28T12:00:00-06:00'}
    assert api_client.post(base+'/process',json=incomplete).status_code==422
    assert api_client.get(base).json()['state']=='PENDING' and db_session.scalar(select(func.count()).select_from(InstallationOrder))==0
    complete={**incomplete,'service_type_id':service,'node_id':ticket_payload['node_id'],'sector_id':ticket_payload['sector_id']}
    response=api_client.post(base+'/process',json=complete)
    assert response.status_code==201,response.text
    order=response.json()
    assert order['order_type']=='EXTRAORDINARY' and order['circuit'] is None and order['source_request_id']==id
    assert api_client.get(base).json()['order_id']==order['id']
    assert api_client.post(base+'/process',json=complete).status_code==409
    assert db_session.scalar(select(func.count()).select_from(InstallationOrder))==1


def test_process_normal_request_needs_a_free_circuit_of_the_customer(api_client,db_session,ticket_payload):
    first=intake(db_session)
    body={'version':0,'order_type':'NORMAL','customer_id':ticket_payload['customer_id'],'requested_at':'2026-10-28T12:00:00-06:00'}
    assert api_client.post(f'/api/installation-requests/{first}/process',json=body).status_code==422
    body['circuit_id']=ticket_payload['circuit_id']
    assert api_client.post(f'/api/installation-requests/{first}/process',json=body).status_code==201
    second=InstallationRequest(mailbox='orders@example.test',folder='INBOX',uidvalidity=1,uid=2,checksum='b'*64,sender='s@example.test',subject='Again',body='again',received_at=datetime.now(timezone.utc))
    db_session.add(second); db_session.commit()
    rejected=api_client.post(f'/api/installation-requests/{second.id}/process',json=body)
    assert rejected.status_code==409 and api_client.get(f'/api/installation-requests/{second.id}').json()['state']=='PENDING'
