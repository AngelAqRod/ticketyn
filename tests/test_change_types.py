"""Classification contracts use disposable PostgreSQL fixtures only."""
from io import BytesIO
import pytest
from openpyxl import load_workbook
from sqlalchemy import text
from test_changes import payload, create
from test_ticket_exports import pdf_strings


def test_catalog_validation_and_lifecycle(api_client):
    response=api_client.post('/api/change-types',json={'name':'  Mantenimiento NOC  ','description':'Trabajos de red'})
    assert response.status_code==201,response.text
    kind=response.json();id=kind['id']
    assert kind['name']=='Mantenimiento NOC'
    assert api_client.post('/api/change-types',json={'name':'mantenimiento noc'}).status_code==409
    assert api_client.post('/api/change-types',json={'name':'   '}).status_code==422
    another=api_client.post('/api/change-types',json={'name':'Otro tipo'}).json()
    assert api_client.patch(f"/api/change-types/{another['id']}",json={'name':' MANTENIMIENTO NOC '}).status_code==409
    assert api_client.patch(f'/api/change-types/{id}',json={'name':'Mantenimiento editado','description':'Nueva descripción','active':False}).status_code==200
    assert all(row['id']!=id for row in api_client.get('/api/change-types').json())
    assert any(row['id']==id for row in api_client.get('/api/change-types',params={'include_inactive':True}).json())
    assert api_client.get(f'/api/change-types/{id}').json()['description']=='Nueva descripción'
    assert api_client.patch(f'/api/change-types/{id}',json={'active':True}).json()['active']
    assert api_client.delete(f'/api/change-types/{id}').status_code==405


def test_required_active_type_and_historical_retention(api_client,db_session):
    p=payload(api_client);id=p['change_type_id']
    missing={key:value for key,value in p.items() if key!='change_type_id'}
    for value in (missing,{**p,'change_type_id':None},{**p,'change_type_id':99999}):
        assert api_client.post('/api/changes',json=value).status_code==422
    change=create(api_client,p);path=f"/api/changes/{change['id']}"
    api_client.patch(f'/api/change-types/{id}',json={'active':False})
    assert api_client.post('/api/changes',json=p).status_code==422
    preserved=api_client.patch(path,json={'title':'Corrección principal','change_type_id':id})
    assert preserved.status_code==200,preserved.text
    assert preserved.json()['change_type']['active'] is False
    other=api_client.post('/api/change-types',json={'name':'Clasificación activa'}).json()
    assert api_client.patch(path,json={'change_type_id':other['id']}).status_code==200
    assert api_client.patch(path,json={'change_type_id':id}).status_code==422
    assert api_client.patch(path,json={'change_type_id':None}).status_code==422
    # Simulate a pre-upgrade record without inferring a classification.
    db_session.execute(text('UPDATE maintenance_changes SET change_type_id=NULL WHERE id=:id'),{'id':change['id']});db_session.commit();db_session.expire_all()
    historical=api_client.get(path).json()
    assert historical['change_type_id'] is None and historical['change_type'] is None
    assert api_client.patch(path,json={'title':'Debe clasificarse'}).status_code==422
    assert api_client.patch(path,json={'internal_ticket_ids':[]}).status_code==200
    assert api_client.post(path+'/updates',json={'responsible_id':p['manager_id'],'occurred_at':p['proposed_start'],'content':'Seguimiento histórico'}).status_code==201
    assert api_client.patch(path,json={'title':'Clasificado','change_type_id':other['id']}).status_code==200


def test_classification_filters_summary_and_unclassified(api_client,db_session):
    p=payload(api_client);one=create(api_client,p)
    other=api_client.post('/api/change-types',json={'name':'Tipo alternativo'}).json()
    create(api_client,{**p,'change_type_id':other['id']})
    db_session.execute(text('UPDATE maintenance_changes SET change_type_id=NULL WHERE id=:id'),{'id':one['id']});db_session.commit();db_session.expire_all()
    summary=api_client.get('/api/change-reports/summary').json()
    assert {row['label']:row['count'] for row in summary['change_types']}=={'Sin clasificar':1,'Tipo alternativo':1}
    filters={'change_type_id':other['id'],'from':'2026-10-15T00:00:00-06:00','to':'2026-10-16T00:00:00-06:00'}
    listing=api_client.get('/api/changes',params={**filters,'limit':1}).json()
    assert listing['total']==1 and listing['items'][0]['change_type']['name']=='Tipo alternativo'
    filtered=api_client.get('/api/change-reports/summary',params=filters).json()
    assert filtered['kpis']['total']==1 and filtered['change_types']==[{'id':other['id'],'label':'Tipo alternativo','count':1}]
    assert api_client.get('/api/changes',params={'change_type_id':9999}).json()['total']==0


@pytest.mark.parametrize('historical',[False,True])
def test_classification_exports(api_client,db_session,pdf_strings,historical):
    p=payload(api_client);change=create(api_client,p)
    if historical:
        db_session.execute(text('UPDATE maintenance_changes SET change_type_id=NULL WHERE id=:id'),{'id':change['id']});db_session.commit();db_session.expire_all()
    label='Sin clasificar' if historical else 'Tipo prueba'
    for base in ('/api/changes/export/','/api/change-reports/export/'):
        params={} if historical else {'change_type_id':p['change_type_id']}
        response=api_client.get(base+'xlsx',params=params)
        assert response.status_code==200,response.text
        book=load_workbook(BytesIO(response.content))
        rows=list(book['Control de cambios'].values)
        column=rows[0].index('Tipo de cambio')
        assert rows[1][column]==label
        if 'change-reports' in base:
            assert list(book['Tipos de cambio'].values)[1]==(label,1)
        pdf_strings.clear()
        response=api_client.get(base+'pdf',params=params)
        assert response.status_code==200,response.text
        assert 'Tipo de cambio' in ' '.join(pdf_strings) and label in ' '.join(pdf_strings)
    pdf_strings.clear()
    response=api_client.get(f"/api/changes/{change['id']}/reports/pdf")
    assert response.status_code==200,response.text
    assert label in ' '.join(pdf_strings)
