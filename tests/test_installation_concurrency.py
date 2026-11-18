"""Public API regressions with independent concurrent PostgreSQL transactions."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from ticketyn.models import Circuit
from ticketyn.models.installation_orders import InstallationRequest, InstallationOrder, InstallationEvent, InstallationDocument

@pytest.fixture
def concurrency_engine(postgres_engine):
    from uuid import uuid4
    from sqlalchemy import create_engine, text
    from ticketyn.db.base import Base
    schema='installation_concurrency_'+uuid4().hex
    with postgres_engine.begin() as connection:
        connection.execute(text('CREATE SCHEMA '+schema))
    engine=create_engine(postgres_engine.url,connect_args={'options':'-csearch_path='+schema})
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()

@pytest.fixture
def real_clients(concurrency_engine, monkeypatch):
    from ticketyn.core.config import get_settings
    from ticketyn.db.session import get_session
    from security_helpers import authenticate_test_client
    monkeypatch.setenv('DATABASE_URL','postgresql+psycopg://unused:unused@127.0.0.1:1/unused')
    get_settings.cache_clear()
    from ticketyn.main import create_app
    app=create_app(start_notifications=False)
    def database():
        with Session(concurrency_engine) as session: yield session
    app.dependency_overrides[get_session]=database
    with TestClient(app) as one, TestClient(app) as two:
        _, token=authenticate_test_client(app,one,concurrency_engine)
        two.headers['Authorization']='Bearer '+token
        yield one,two
    get_settings.cache_clear()

def parallel(clients, method, urls, payloads):
    gate=Barrier(2)
    def call(i):
        gate.wait(timeout=10)
        return getattr(clients[i],method)(urls[i],json=payloads[i])
    with ThreadPoolExecutor(2) as pool: return list(pool.map(call,range(2)))

def order_payload(customer,circuit):
    return dict(order_type='NORMAL',customer_id=customer,circuit_id=circuit,requested_at='2026-10-28T12:00:00-06:00')

def test_real_concurrent_transactions(real_clients,concurrency_engine,tmp_path,monkeypatch):
    monkeypatch.setenv('INSTALLATION_STORAGE_DIR',str(tmp_path/'private'))
    one,two=real_clients
    customer=one.post('/api/customers',json={'customer_code':'VERIFY','name':'Verify'}).json()['id']
    node=one.post('/api/nodes',json={'name':'Verify node'}).json()['id']
    sector=one.post('/api/sectors',json={'name':'Verify sector'}).json()['id']
    circuit_data=dict(customer_id=customer,node_id=node,sector_id=sector,circuit_code='VERIFY-C',description='verify')
    circuit=one.post('/api/circuits',json=circuit_data).json()['id']
    other_circuit=one.post('/api/circuits',json={**circuit_data,'circuit_code':'VERIFY-D'}).json()['id']
    data=order_payload(customer,circuit)
    with Session(concurrency_engine) as s:
        request=InstallationRequest(mailbox='verify',folder='INBOX',uidvalidity=1,uid=88,checksum='c'*64,sender='v@example.test',subject='verify',body='immutable',received_at=datetime.now(timezone.utc))
        s.add(request);s.commit();id=request.id
        from ticketyn.incoming.storage import save_document
        document=save_document(s,content=b'%PDF-1.7\nimmutable',name='original.pdf',request_id=id);s.commit();doc_id=document.id;original_key=document.storage_key
    base=f'/api/installation-requests/{id}'
    results=parallel(real_clients,'put',[base+'/draft']*2,[{'version':0,'data':{'notes':'one'}},{'version':0,'data':{'notes':'two'}}])
    assert sorted(r.status_code for r in results)==[200,409],[(r.status_code,r.text) for r in results]
    results=parallel(real_clients,'put',[base+'/draft']*2,[{'version':1,'data':{'notes':'three'}},{'version':1,'data':{'notes':'four'}}])
    assert sorted(r.status_code for r in results)==[200,409]
    results=parallel(real_clients,'post',[base+'/process']*2,[{**data,'version':2}]*2)
    assert sorted(r.status_code for r in results)==[201,409],[(r.status_code,r.text) for r in results]
    with Session(concurrency_engine) as s:
        assert s.scalar(select(func.count()).select_from(InstallationOrder))==1
        assert s.scalar(select(func.count()).select_from(InstallationEvent).where(InstallationEvent.request_id==id,InstallationEvent.action=='PROCESS'))==1
        document=s.get(InstallationDocument,doc_id)
        assert (document.request_id,document.order_id,document.storage_key)==(id,None,original_key)
        from ticketyn.incoming.storage import document_path
        assert document_path(document).read_bytes()==b'%PDF-1.7\nimmutable'
    first=next(r.json()['id'] for r in results if r.status_code==201)
    urls=['/api/installation-orders']*2
    results=parallel(real_clients,'post',urls,[order_payload(customer,other_circuit)]*2)
    assert sorted(r.status_code for r in results)==[201,409],[(r.status_code,r.text) for r in results]
    with Session(concurrency_engine) as s:
        assert s.scalar(select(func.count()).select_from(InstallationOrder).where(InstallationOrder.circuit_id==other_circuit))==1
        before=s.scalar(select(func.count()).select_from(Circuit))
    rejected=one.post(f'/api/installation-orders/{first}/circuit',json={**circuit_data,'circuit_code':'MUST-NOT-EXIST'})
    assert rejected.status_code==409
    with Session(concurrency_engine) as s: assert s.scalar(select(func.count()).select_from(Circuit))==before

def test_granular_permission_boundaries(api_client,db_session,ticket_payload):
    from ticketyn.models import Responsible
    from ticketyn.models.security import SecurityRole,SecurityRolePermission
    from security_helpers import fixture_password
    data=order_payload(ticket_payload['customer_id'],ticket_payload['circuit_id'])
    order=api_client.post('/api/installation-orders',json=data).json()['id']
    from test_installation_orders import legacy_order
    legacy_id=legacy_order(db_session,ticket_payload).id
    item=InstallationRequest(mailbox='perm',folder='INBOX',uidvalidity=1,uid=7,checksum='d'*64,sender='x',subject='x',body='x',received_at=datetime.now(timezone.utc))
    db_session.add(item);db_session.commit();rid=item.id
    original=api_client.headers['Authorization']
    for idx,perms in enumerate([['installation_orders.view'],['installation_orders.link'],['installation_requests.process'],['installation_requests.review']]):
        role=SecurityRole(name=f'Verifier role {idx}');db_session.add(role);db_session.flush()
        for perm in perms: db_session.add(SecurityRolePermission(role_id=role.id,permission_code=perm))
        person=Responsible(name=f'Verifier {idx}',username=f'verifier-{idx}',password_hash=fixture_password(),access_granted=True,security_role_id=role.id,password_change_required=False)
        db_session.add(person);db_session.commit()
        api_client.headers['Authorization']=original
        token=api_client.post('/api/auth/login',json={'username':person.username,'password':'test-only-password'}).json()['token']
        api_client.headers['Authorization']='Bearer '+token
        assert api_client.post('/api/installation-orders',json=data).status_code==403
        assert api_client.post(f'/api/installation-requests/{rid}/process',json={**data,'version':0}).status_code==403
        if idx!=1:
            assert api_client.put(f'/api/installation-orders/{order}/circuit',json={'circuit_id':ticket_payload['circuit_id']}).status_code==403
        else:
            circuit=dict(customer_id=ticket_payload['customer_id'],node_id=ticket_payload['node_id'],sector_id=ticket_payload['sector_id'],circuit_code='PERM-REJECT',description='Verify')
            assert api_client.post(f'/api/installation-orders/{legacy_id}/circuit',json=circuit).status_code==403
        assert api_client.post('/api/incoming-mail/poll').status_code==403
    api_client.headers['Authorization']=original


def test_spoof_filename_public_endpoint(api_client,ticket_payload,tmp_path,monkeypatch):
    monkeypatch.setenv('INSTALLATION_STORAGE_DIR',str(tmp_path/'files'))
    order=api_client.post('/api/installation-orders',json=order_payload(ticket_payload['customer_id'],ticket_payload['circuit_id'])).json()['id']
    for filename,content in [('../outside.pdf',b'%PDF-1.7\n'),('image.png',b'<html>unsafe</html>'),('executable.pdf',b'MZbinary'),('bad.html',b'%PDF-1.7\n')]:
        response=api_client.post(f'/api/installation-orders/{order}/documents',params={'filename':filename},content=content)
        assert response.status_code==422,(filename,response.text)
    assert api_client.get(f'/api/installation-orders/{order}').json()['documents']==[]

def test_create_link_rolls_back_after_circuit_insert(api_client,db_session,ticket_payload,monkeypatch):
    from fastapi import HTTPException
    from ticketyn.api import installation_orders
    from test_installation_orders import legacy_order
    legacy=legacy_order(db_session,ticket_payload)
    order=api_client.get(f'/api/installation-orders/{legacy.id}').json()
    circuit=dict(customer_id=ticket_payload['customer_id'],node_id=ticket_payload['node_id'],sector_id=ticket_payload['sector_id'],circuit_code='INSERT-THEN-FAIL',description='Verify')
    before=db_session.scalar(select(func.count()).select_from(Circuit))
    real_event=installation_orders.event
    def event(*args,**kwargs):
        if args[2]=='LINK': raise HTTPException(409,'Simulated failure after circuit insert')
        return real_event(*args,**kwargs)
    monkeypatch.setattr(installation_orders,'event',event)
    response=api_client.post(f"/api/installation-orders/{order['id']}/circuit",json=circuit)
    assert response.status_code==409
    assert db_session.scalar(select(func.count()).select_from(Circuit))==before
    assert api_client.get(f"/api/installation-orders/{order['id']}").json()==order


def test_existing_circuit_contract(api_client,ticket_payload):
    data=dict(customer_id=ticket_payload['customer_id'],node_id=ticket_payload['node_id'],sector_id=ticket_payload['sector_id'],circuit_code='DIFFERENTIAL',description='legacy')
    response=api_client.post('/api/circuits',json=data)
    assert response.status_code==201
    body=response.json()
    assert body['circuit_code']=='DIFFERENTIAL' and body['description']=='legacy' and body['active'] is True
    assert api_client.post('/api/circuits',json=data).status_code==409
    assert api_client.post('/api/circuits',json={**data,'circuit_code':'INVALID','node_id':2147000100}).status_code==404
    assert api_client.get(f"/api/circuits/{body['id']}").json()==body
