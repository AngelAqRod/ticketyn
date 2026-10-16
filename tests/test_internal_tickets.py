from sqlalchemy import select
from ticketyn.models import InternalTicketNumberConfig, InternalTicket, InternalTicketUpdate

def payload(client):
    def catalog(path, name):
        result = client.post('/api/' + path, json={'name': name})
        assert result.status_code == 201, result.text
        return result.json()['id']
    return dict(title='Caída de infraestructura', description='Incidencia interna del NOC', sector_id=catalog('sectors','Interno'), department_id=catalog('departments','NOC interno'), incident_type_id=catalog('internal-incident-types','Energía'), start_at='2026-10-15T08:00:00-06:00')

def test_internal_lifecycle_and_contracts(api_client):
    p = payload(api_client)
    response = api_client.post('/api/internal-tickets', json=p)
    assert response.status_code == 201, response.text
    ticket = response.json(); id = ticket['id']
    assert ticket['reference'] == 'INT-0000001'
    assert ticket['node_id'] is None and ticket['provider_id'] is None
    assert 'customer_id' not in ticket and 'circuit_id' not in ticket
    for forbidden in ('customer_id','circuit_id','customer_description','customer_resolution'):
        assert api_client.post('/api/internal-tickets', json={**p, forbidden: 1}).status_code == 422
    missing = dict(p); missing.pop('sector_id')
    assert api_client.post('/api/internal-tickets', json=missing).status_code == 422
    assert api_client.patch(f'/api/internal-tickets/{id}', json={'status':'CLOSED','end_at':'2026-10-15T10:00:00-06:00'}).status_code == 200
    provider = api_client.post('/api/providers', json={'name':'Proveedor NOC','description':'Transporte'}).json()
    patched = api_client.patch(f'/api/internal-tickets/{id}', json={'provider_id':provider['id']}).json()
    assert patched['status'] == 'CLOSED' and patched['duration_seconds'] == 7200
    assert api_client.get('/api/internal-tickets', params={'provider_id':provider['id']}).json()[0]['id'] == id
    assert api_client.get('/api/internal-tickets', params={'without_provider':True}).json() == []
    api_client.patch('/api/providers/'+str(provider['id']), json={'active':False})
    assert api_client.patch(f'/api/internal-tickets/{id}', json={'title':'Nuevo título'}).status_code == 200
    assert api_client.post('/api/internal-tickets', json={**p,'provider_id':provider['id']}).status_code == 422
    assert api_client.patch('/api/providers/'+str(provider['id']), json={'name':'Proveedor corregido','description':'Referencia actualizada','active':True}).status_code == 200
    assert api_client.get('/api/providers/'+str(provider['id'])).json()['active'] is True
    assert api_client.patch(f'/api/internal-tickets/{id}', json={'provider_id':None}).status_code == 200
    updates = api_client.get(f'/api/internal-tickets/{id}/updates', params={'limit':10}).json()
    assert len(updates['items']) == 2 and all(row['visibility']=='INTERNAL' for row in updates['items'])
    assert api_client.post(f'/api/internal-tickets/{id}/updates', json={'content':'Trabajo','visibility':'PUBLIC'}).status_code == 422
    assert api_client.post(f'/api/internal-tickets/{id}/updates', json={'content':'Trabajo interno'}).status_code == 201
    assert api_client.get('/api/internal-tickets', params={'search':'Incidencia interna'}).json()[0]['id'] == id
    assert api_client.get('/api/internal-tickets', params={'search':'INT-0000001'}).json()[0]['id'] == id
    assert api_client.patch(f'/api/internal-tickets/{id}', json={'end_at':'2026-10-15T07:00:00-06:00'}).status_code == 422

def test_internal_escalations_and_isolation(api_client):
    p=payload(api_client)
    t=api_client.post('/api/internal-tickets',json=p).json()
    reason=api_client.post('/api/escalation-reasons',json={'name':'Apoyo NOC'}).json()
    path=f"/api/internal-tickets/{t['id']}/escalations"
    result=api_client.post(path,json={'department_id':p['department_id'],'reason_id':reason['id'],'description':'Apoyo técnico','started_at':p['start_at']})
    assert result.status_code==201, result.text
    e=result.json()
    assert api_client.post(f"{path}/{e['id']}/finish",json={'finished_at':'2026-10-15T10:00:00-06:00'}).status_code==200
    assert len(api_client.get(f"{path}/{e['id']}/audit").json())==2
    assert api_client.get(f"/api/internal-tickets/{t['id']}").json()['status']=='OPEN'
    assert api_client.get('/api/tickets').json()==[]
    assert api_client.get('/api/tickets/stats').json()['total']==0
    assert api_client.post(f"/api/internal-tickets/{t['id']}/updates",json={'content':'Atendido','escalation_id':e['id']}).status_code==201
    assert api_client.post(f"/api/internal-tickets/{t['id']}/updates",json={'content':'Atendido','escalation_id':99999}).status_code==422

def test_internal_links(api_client,ticket_payload):
    p=payload(api_client); i=api_client.post('/api/internal-tickets',json=p).json()
    t=api_client.post('/api/tickets',json={**ticket_payload,'internal_ticket_id':i['id']})
    assert t.status_code==201,t.text
    second=api_client.post('/api/tickets',json={**ticket_payload,'internal_ticket_id':i['id']}).json()
    linked=api_client.get(f"/api/internal-tickets/{i['id']}/related",params={'limit':1}).json()
    assert linked['total']==2 and len(linked['items'])==1
    other=api_client.post('/api/internal-tickets',json=p).json()
    assert api_client.patch('/api/tickets/'+str(second['id']),json={'internal_ticket_id':other['id']}).json()['internal_ticket_id']==other['id']
    assert api_client.get(f"/api/internal-tickets/{other['id']}/related").json()['total']==1
    assert api_client.patch('/api/tickets/'+str(second['id']),json={'internal_ticket_id':None}).status_code==200
    assert api_client.patch('/api/tickets/'+str(second['id']),json={'internal_ticket_id':999999}).status_code==404
    api_client.patch(f"/api/internal-tickets/{i['id']}",json={'status':'CLOSED'})
    assert api_client.get('/api/tickets/'+str(t.json()['id'])).json()['status']=='OPEN'
    assert api_client.patch('/api/tickets/'+str(second['id']),json={'internal_ticket_id':i['id']}).status_code==200

def test_internal_numbering_and_catalog_uniqueness(api_client):
    p=payload(api_client)
    first=api_client.post('/api/internal-tickets',json=p).json()
    config=api_client.get('/api/settings/internal-ticket-number').json()
    assert config['next_number']==2
    assert api_client.patch('/api/settings/internal-ticket-number',json={'next_number':1}).status_code==409
    assert api_client.patch('/api/settings/internal-ticket-number',json={'prefix':'NOC','padding':3}).status_code==200
    second=api_client.post('/api/internal-tickets',json=p).json()
    assert second['reference']=='NOC-002'
    assert api_client.get('/api/internal-tickets/'+str(first['id'])).json()['reference']=='INT-0000001'
    assert api_client.post('/api/internal-incident-types',json={'name':' energía '}).status_code==409

def test_internal_filters_and_validation(api_client):
    p=payload(api_client)
    node=api_client.post('/api/nodes',json={'name':'Nodo interno'}).json()
    provider=api_client.post('/api/providers',json={'name':'Proveedor filtro'}).json()
    t=api_client.post('/api/internal-tickets',json={**p,'node_id':node['id'],'provider_id':provider['id']}).json()
    for field in ('sector_id','node_id','department_id','incident_type_id','provider_id'):
        assert api_client.get('/api/internal-tickets',params={field:t[field]}).json()[0]['id']==t['id']
        assert api_client.get('/api/internal-tickets',params={field:999999}).json()==[]
    assert api_client.get('/api/internal-tickets',params={'from':'2026-10-15T14:00:00Z','to':'2026-10-15T14:00:01Z'}).json()[0]['id']==t['id']
    assert api_client.get('/api/internal-tickets',params={'from':'2026-10-16T00:00:00Z'}).json()==[]
    assert api_client.get('/api/internal-tickets',params={'from':'2026-10-16T00:00:00Z','to':'2026-10-15T00:00:00Z'}).status_code==422
    assert api_client.get('/api/internal-tickets',params={'offset':1}).json()==[]
    assert api_client.get('/api/internal-tickets',params={'status':'INVALID'}).status_code==422
    assert api_client.get('/api/internal-tickets',params={'customer_id':1}).status_code==422
    for field in ('sector_id','incident_type_id','node_id','provider_id','responsible_id'):
        assert api_client.post('/api/internal-tickets',json={**p,field:999999}).status_code==404
    api_client.patch('/api/internal-incident-types/'+str(p['incident_type_id']),json={'active':False})
    assert api_client.post('/api/internal-tickets',json=p).status_code==422
    assert api_client.patch('/api/internal-tickets/'+str(t['id']),json={'description':'Corrección histórica'}).status_code==200
    assert api_client.get('/api/internal-tickets/'+str(t['id'])+'/report/customer').status_code==404


def test_internal_concurrent_numbering(postgres_engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import uuid4
    from datetime import datetime, timezone
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from ticketyn.db.base import Base
    from ticketyn.models import Sector, Department, InternalIncidentType, TicketNumberConfig
    from ticketyn.api.internal_ticket_data import persist
    schema='internal_concurrency_'+uuid4().hex
    engine=postgres_engine.execution_options(schema_translate_map={None:schema})
    with engine.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'));Base.metadata.create_all(db)
    try:
        with Session(engine) as session:
            sector=Sector(name='Sector');department=Department(name='NOC');kind=InternalIncidentType(name='Energía')
            session.add_all([sector,department,kind]);session.commit()
            p=dict(title='Prueba',description='Concurrencia',sector_id=sector.id,department_id=department.id,incident_type_id=kind.id,node_id=None,provider_id=None,responsible_id=None,resolution=None,start_at=datetime.now(timezone.utc),end_at=None,status='OPEN')
        workers=6; barrier=Barrier(workers)
        def create(_):
            with Session(engine) as session:
                session.execute(text("SET LOCAL lock_timeout='15s'"));barrier.wait(timeout=10)
                ticket=persist(session,p.copy());return ticket.ticket_number,ticket.reference
        with ThreadPoolExecutor(max_workers=workers) as pool: rows=list(pool.map(create,range(workers)))
        assert sorted(number for number,_ in rows)==list(range(1,workers+1))
        assert len({reference for _,reference in rows})==workers
        with Session(engine) as session:
            assert session.get(InternalTicketNumberConfig,1).next_number==workers+1
            assert session.get(TicketNumberConfig,1) is None
    finally:
        with postgres_engine.begin() as db:db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
