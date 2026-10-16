from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
import pytest
from ticketyn.api.change_data import measurements


def payload(client):
 kind=client.post('/api/change-types',json={'name':'Tipo prueba'}).json()
 sector=client.post('/api/sectors',json={'name':'Sector cambios'}).json()
 dept=client.post('/api/departments',json={'name':'Ingeniería cambios'}).json()
 manager=client.post('/api/responsibles',json={'name':'Encargado cambios','department_id':dept['id']}).json()
 return dict(change_type_id=kind['id'],title='Mejora de transporte',description='Ajuste de configuración',sector_id=sector['id'],manager_id=manager['id'],proposed_start='2026-10-15T11:00:00-06:00',proposed_end='2026-10-15T15:00:00-06:00')


def create(client,p):
 r=client.post('/api/changes',json=p);assert r.status_code==201,r.text;return r.json()


def finish_type(client,eligible=True):
 r=client.post('/api/change-completion-types',json={'name':'Éxito prueba' if eligible else 'No evaluable prueba','applies_efficiency':eligible});assert r.status_code==201,r.text;return r.json()


def test_lifecycle_snapshot_late_efficiency_and_corrections(api_client):
 p=payload(api_client);kind=finish_type(api_client)
 item=create(api_client,p);id=item['id']
 assert item['reference']=='CAM-0000001' and item['department_name']=='Ingeniería cambios'
 assert item['efficiency']=='NOT_EVALUABLE'
 assert api_client.patch(f'/api/changes/{id}',json={'status':'EXECUTING'}).status_code==422
 assert api_client.patch(f'/api/changes/{id}',json={'status':'EXECUTING','actual_start':'2026-10-15T13:00:00-06:00'}).status_code==200
 response=api_client.patch(f'/api/changes/{id}',json={'status':'FINISHED','actual_end':'2026-10-15T15:00:00-06:00','completion_type_id':kind['id'],'final_notes':'Completado'})
 assert response.status_code==200,response.text
 result=response.json()
 assert result['planned_seconds']==14400 and result['actual_seconds']==7200
 assert result['saved_seconds']==7200 and result['efficiency']=='BETTER' and result['variation_percent']==50 and result['late_start']
 api_client.patch('/api/change-completion-types/'+str(kind['id']),json={'applies_efficiency':False,'name':'Renombrado','active':False})
 result=api_client.patch(f'/api/changes/{id}',json={'final_notes':'Notas corregidas'}).json()
 assert result['efficiency']=='BETTER' and result['completion_name']=='Éxito prueba'
 assert result['status']=='FINISHED' and result['created_at']==item['created_at']
 assert api_client.get(f'/api/changes/{id}/audit').json()
 assert api_client.patch(f'/api/changes/{id}',json={'created_at':'2020-01-01T00:00:00Z'}).status_code==422


@pytest.mark.parametrize('difference,expected',[(900,'ON_TIME'),(-900,'ON_TIME'),(901,'BETTER'),(-901,'EXCEEDED')])
def test_efficiency_boundaries(difference,expected):
 start=datetime(2026,1,1,tzinfo=timezone.utc)
 row=SimpleNamespace(proposed_start=start,proposed_end=start+timedelta(hours=4),actual_start=start+timedelta(hours=2),actual_end=start+timedelta(hours=6,seconds=-difference),status='FINISHED',efficiency_eligible=True)
 assert measurements(row)['efficiency']==expected
 assert measurements(row)['late_start']
 row.actual_start=start+timedelta(minutes=60);row.actual_end=row.actual_start+timedelta(hours=4)
 assert not measurements(row)['late_start']
 row.actual_start+=timedelta(minutes=1)
 assert measurements(row)['late_start']
 row.proposed_end=row.proposed_start
 assert measurements(row)['efficiency']=='NOT_EVALUABLE' and measurements(row)['variation_percent'] is None


def test_participants_links_and_history(api_client):
 from test_internal_tickets import payload as internal_payload
 p=payload(api_client)
 support=api_client.post('/api/responsibles',json={'name':'Apoyo cambios'}).json()
 item=create(api_client,{**p,'support_ids':[support['id']]})
 assert api_client.post('/api/changes',json={**p,'support_ids':[support['id'],support['id']]}).status_code==422
 assert api_client.patch(f"/api/changes/{item['id']}",json={'support_ids':[p['manager_id']]}).status_code==422
 api_client.patch('/api/responsibles/'+str(support['id']),json={'active':False,'name':'Apoyo renombrado'})
 result=api_client.patch(f"/api/changes/{item['id']}",json={'title':'Corrección'}).json()
 assert result['support']==[{'id':support['id'],'name':'Apoyo cambios'}]
 internal=create_internal=api_client.post('/api/internal-tickets',json=internal_payload(api_client)).json()
 linked=api_client.patch(f"/api/changes/{item['id']}",json={'internal_ticket_ids':[internal['id']]})
 assert linked.status_code==200,linked.text
 assert linked.json()['internal_tickets'][0]['id']==internal['id']
 assert api_client.get('/api/changes',params={'internal_ticket_id':internal['id']}).json()['total']==1
 assert api_client.get('/api/internal-tickets/'+str(internal['id'])).json()['status']=='OPEN'
 assert api_client.patch(f"/api/changes/{item['id']}",json={'internal_ticket_ids':[]}).json()['internal_tickets']==[]


def test_validations_and_filters(api_client):
 p=payload(api_client)
 for values in ({'proposed_end':'2026-10-15T10:00:00-06:00'},{'status':'FINISHED'},{'actual_end':'2026-10-15T10:00:00-06:00'},{'manager_id':99999},{'internal_ticket_ids':[99999]}):
  assert api_client.post('/api/changes',json={**p,**values}).status_code==422
 item=create(api_client,p)
 for field in ('sector_id','manager_id'):
  assert api_client.get('/api/changes',params={field:p[field]}).json()['total']==1
  assert api_client.get('/api/changes',params={field:9999}).json()['total']==0
 assert api_client.get('/api/changes',params={'search':'transporte'}).json()['total']==1
 assert api_client.get('/api/changes',params={'involved_id':p['manager_id']}).json()['total']==1
 assert api_client.get('/api/changes',params={'from':'2027-01-01T00:00:00Z','to':'2027-02-01T00:00:00Z'}).json()['total']==0
 assert api_client.get('/api/changes/999999').status_code==404


def test_report_and_exports(api_client):
 p=payload(api_client);kind=finish_type(api_client)
 done=create(api_client,{**p,'status':'FINISHED','actual_start':'2026-10-15T13:00:00-06:00','actual_end':'2026-10-15T15:00:00-06:00','completion_type_id':kind['id'],'final_notes':'Notas finales'})
 create(api_client,p)
 summary=api_client.get('/api/change-reports/summary')
 assert summary.status_code==200,summary.text
 k=summary.json()['kpis'];assert k['total']==2 and k['evaluable']==1 and k['not_evaluable']==1 and k['better']==1 and k['percentages']['better']==100
 assert k['saved_seconds']==7200 and k['late_starts']==1
 assert summary.json()['participants'][0]['manager']==2 and summary.json()['participants'][0]['count']==2
 for base in ('/api/changes/export/','/api/change-reports/export/'):
  for format in ('pdf','xlsx'):
   r=api_client.get(base+format);assert r.status_code==200,r.text
   assert r.content.startswith(b'%PDF-' if format=='pdf' else b'PK')
 id=done['id']
 r=api_client.post(f'/api/changes/{id}/updates',json={'responsible_id':p['manager_id'],'occurred_at':'2026-10-15T15:00:00-06:00','content':'Actividad posterior'})
 assert r.status_code==201,r.text
 r=api_client.get(f'/api/changes/{id}/reports/pdf');assert r.status_code==200,r.text
 assert api_client.get(f'/api/changes/{id}/updates').json()['total']==1


def test_independent_concurrent_numbering(postgres_engine):
 from concurrent.futures import ThreadPoolExecutor
 from threading import Barrier
 from uuid import uuid4
 from sqlalchemy import text
 from sqlalchemy.orm import Session
 from ticketyn.db.base import Base
 from ticketyn.models import Sector,Department,Responsible,ChangeType,ChangeNumberConfig,TicketNumberConfig,InternalTicketNumberConfig
 from ticketyn.api.change_data import persist
 schema='change_concurrency_'+uuid4().hex
 engine=postgres_engine.execution_options(schema_translate_map={None:schema})
 with engine.begin() as db:
  db.execute(text(f'CREATE SCHEMA "{schema}"'));Base.metadata.create_all(db)
 try:
  with Session(engine) as session:
   sector=Sector(name='Sector');dept=Department(name='NOC');session.add_all([sector,dept]);session.flush()
   person=Responsible(name='Encargado',department_id=dept.id);kind=ChangeType(name='Prueba');session.add_all([person,kind]);session.commit()
   now=datetime.now(timezone.utc)
   p=dict(change_type_id=kind.id,title='Concurrente',description='Operación',sector_id=sector.id,node_id=None,manager_id=person.id,proposed_start=now,proposed_end=now+timedelta(hours=1),status='SCHEDULED',actual_start=None,actual_end=None,completion_type_id=None,final_notes=None)
  barrier=Barrier(5)
  def create_one(_):
   with Session(engine) as session:
    session.execute(text("SET LOCAL lock_timeout='15s'"));barrier.wait(timeout=10)
    result=persist(session,p.copy());return result.reference
  with ThreadPoolExecutor(max_workers=5) as pool:refs=list(pool.map(create_one,range(5)))
  assert len(set(refs))==5 and set(refs)=={f'CAM-{i:07}' for i in range(1,6)}
  with Session(engine) as session:
   assert session.get(ChangeNumberConfig,1).next_number==6
   assert session.get(TicketNumberConfig,1) is None and session.get(InternalTicketNumberConfig,1) is None
 finally:
  with postgres_engine.begin() as db:db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_empty_and_non_evaluable_reports_and_optional_node(api_client):
 r=api_client.get('/api/change-reports/summary');assert r.status_code==200,r.text
 assert r.json()['kpis']['total']==0 and r.json()['kpis']['percentages']['better']==0
 p=payload(api_client);kind=finish_type(api_client,False)
 # Sector and Node are independent by the user's confirmed scope decision.
 node=api_client.post('/api/nodes',json={'name':'Nodo sin circuitos'}).json()
 row=create(api_client,{**p,'node_id':node['id'],'status':'FINISHED','actual_start':p['proposed_start'],'actual_end':p['proposed_end'],'completion_type_id':kind['id'],'final_notes':'Documentación histórica'})
 assert row['efficiency']=='NOT_EVALUABLE'
 k=api_client.get('/api/change-reports/summary').json()['kpis']
 assert k['evaluable']==0 and k['not_evaluable']==1 and k['average_seconds']==14400
 assert api_client.patch('/api/settings/change-number',json={'next_number':1}).status_code==409
 assert api_client.patch('/api/settings/change-number',json={'prefix':'MNT','padding':3}).status_code==200
 assert create(api_client,p)['reference']=='MNT-002'


def test_participation_filters_and_closed_corrections(api_client):
 p=payload(api_client);kind=finish_type(api_client)
 a=api_client.post('/api/responsibles',json={'name':'Persona A','department_id':api_client.get('/api/responsibles/'+str(p['manager_id'])).json()['department_id']}).json()
 b=api_client.post('/api/responsibles',json={'name':'Persona B'}).json()
 one=create(api_client,{**p,'support_ids':[a['id'],b['id']],'status':'FINISHED','actual_start':p['proposed_start'],'actual_end':p['proposed_end'],'completion_type_id':kind['id'],'final_notes':'Fin'})
 create(api_client,{**p,'manager_id':a['id'],'support_ids':[p['manager_id']]})
 summary=api_client.get('/api/change-reports/summary').json()
 persons={r['id']:r for r in summary['participants']}
 assert persons[a['id']]['manager']==1 and persons[a['id']]['support']==1 and persons[a['id']]['count']==2
 for field in ('support_id','involved_id'):
  assert api_client.get('/api/changes',params={field:b['id']}).json()['total']==1
  assert api_client.get('/api/change-reports/summary',params={field:b['id']}).json()['kpis']['total']==1
 patched=api_client.patch('/api/changes/'+str(one['id']),json={'manager_id':a['id'],'support_ids':[b['id']]})
 assert patched.status_code==200,patched.text
 assert patched.json()['status']=='FINISHED' and patched.json()['manager_name']=='Persona A'
 assert len(api_client.get('/api/changes/'+str(one['id'])+'/audit').json())==2


@pytest.mark.parametrize('finished',[False,True])
def test_support_is_optional_on_create_and_can_be_cleared_on_edit(api_client,finished):
 p=payload(api_client)
 if finished:
  kind=finish_type(api_client)
  p.update(status='FINISHED',actual_start=p['proposed_start'],actual_end=p['proposed_end'],completion_type_id=kind['id'],final_notes='Operación individual')
 item=create(api_client,{**p,'support_ids':[]})
 assert item['support']==[]
 id=item['id']
 person=api_client.post('/api/responsibles',json={'name':'Apoyo opcional'}).json()
 assigned=api_client.patch(f'/api/changes/{id}',json={'support_ids':[person['id']]})
 assert assigned.status_code==200,assigned.text
 assert assigned.json()['support']==[{'id':person['id'],'name':person['name']}]
 # Omitting the field keeps existing assignments; an explicit [] removes them.
 unchanged=api_client.patch(f'/api/changes/{id}',json={'title':'Cambio corregido'})
 assert unchanged.json()['support']==assigned.json()['support']
 cleared=api_client.patch(f'/api/changes/{id}',json={'support_ids':[]})
 assert cleared.status_code==200,cleared.text
 assert cleared.json()['support']==[] and cleared.json()['status']==item['status']
 assert api_client.get(f'/api/changes/{id}').json()['support']==[]
 audit=api_client.get(f'/api/changes/{id}/audit').json()
 assert audit[0]['changes']['support']=={'before':[{'id':person['id'],'name':person['name']}],'after':[]}
 assert api_client.patch(f'/api/changes/{id}',json={'support_ids':[]}).json()['support']==[]
 assert api_client.patch(f'/api/changes/{id}',json={'support_ids':[p['manager_id']]}).status_code==422
 assert api_client.patch(f'/api/changes/{id}',json={'support_ids':[person['id'],person['id']]}).status_code==422


def test_executing_seconds_midnight_create_and_edit(api_client):
 p={**payload(api_client),'status':'EXECUTING',
    'proposed_start':'2026-10-15T23:00:00-06:00',
    'proposed_end':'2026-10-16T03:00:00-06:00',
    'actual_start':'2026-10-15T23:00:50-06:00',
    'actual_end':None,'completion_type_id':None,'final_notes':None}
 item=create(api_client,p)
 path=f"/api/changes/{item['id']}"
 for response in [api_client.get(path),api_client.patch(path,json={'title':'Trabajo nocturno corregido'})]:
  assert response.status_code==200,response.text
  row=response.json()
  assert row['status']=='EXECUTING'
  assert row['planned_seconds']==14400 and row['actual_seconds'] is None
  assert datetime.fromisoformat(row['actual_start'])==datetime(2026,10,16,5,0,50,tzinfo=timezone.utc)
  assert row['actual_end'] is None and row['completion_type_id'] is None and row['final_notes'] is None
 assert api_client.patch(path,json={'status':'FINISHED'}).status_code==422
 kind=finish_type(api_client)
 response=api_client.patch(path,json={'status':'FINISHED','actual_end':p['proposed_end'],'completion_type_id':kind['id'],'final_notes':'Completado'})
 assert response.status_code==200,response.text
 assert response.json()['actual_seconds']==14350
