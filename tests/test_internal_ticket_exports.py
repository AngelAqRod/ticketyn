from datetime import datetime, timezone
from io import BytesIO
import re
import pytest
from openpyxl import load_workbook
from sqlalchemy import event
from ticketyn.models import InternalTicket
from ticketyn.api.internal_ticket_exports import HEADERS
from test_internal_tickets import payload
from test_ticket_exports import pdf_strings


def export(client, format='xlsx', **filters):
    response=client.get(f'/api/internal-tickets/export/{format}',params=filters)
    assert response.status_code==200,response.text
    assert f'ticketyn-tickets-internos.{format}' in response.headers['content-disposition']
    assert response.headers['content-type'].startswith('application/pdf' if format=='pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    return response


def values(response):
    book=load_workbook(BytesIO(response.content))
    return book,list(book['Tickets internos'].values)


@pytest.mark.parametrize('format',['pdf','xlsx'])
def test_empty_export(api_client,format,pdf_strings):
    result=export(api_client,format)
    if format=='pdf':
        assert result.content.startswith(b'%PDF-') and 'Sin resultados.' in ' '.join(pdf_strings)
    else:
        book,rows=values(result)
        assert rows==[tuple(HEADERS)]
        assert book['Tickets internos'].freeze_panes=='A2'
        assert 'Todos los tickets internos' in [row[0] for row in book['Filtros'].values]


@pytest.mark.parametrize('format',['pdf','xlsx'])
def test_complete_exports_related_counts_and_dates(api_client,ticket_payload,db_session,format,pdf_strings):
    p=payload(api_client)
    rows=[]
    for index in range(55):
        rows.append(InternalTicket(**{**p,'start_at':datetime(2026,10,15,14,tzinfo=timezone.utc)},ticket_number=index+1,reference=f'INT-{index+1:07}',end_at=datetime(2026,10,15,15,30,tzinfo=timezone.utc),status='CLOSED'))
    db_session.add_all(rows);db_session.commit()
    id=rows[0].id
    for _ in range(3):
        response=api_client.post('/api/tickets',json={**ticket_payload,'internal_ticket_id':id})
        assert response.status_code==201,response.text
    statements=[]
    def capture(_conn,_cursor,statement,*_):statements.append(statement)
    engine=db_session.get_bind();event.listen(engine,'before_cursor_execute',capture)
    try:
        result=export(api_client,format,limit=1,offset=50,timezone='America/Guatemala')
    finally:event.remove(engine,'before_cursor_execute',capture)
    assert len(statements)<(9 if format=='pdf' else 8)  # PDF adds one volume preflight, never per-record queries.
    if format=='pdf':
        text=' '.join(pdf_strings)
        assert 'INT-0000001' in text and 'INT-0000055' in text
        assert '1 h 30 min' in text and '08:00' in text
        assert len(re.findall(rb'/Type\s*/Page\b',result.content))>1
        assert 'Total encontrado: 55' in text
    else:
        book,exported=values(result)
        assert len(exported)==56 and list(exported[0])==HEADERS
        record=next(row for row in exported[1:] if row[0]=='INT-0000001')
        assert record[8]=='Ninguno' and record[9]=='2026-10-15T08:00:00-06:00'
        assert record[10]=='1 h 30 min' and record[11]==3
        assert all(row[11]==0 for row in exported[1:] if row[0]!='INT-0000001')
        assert book['Tickets internos'].auto_filter.ref=='A1:L56'
        expected=[item['reference'] for item in api_client.get('/api/internal-tickets?limit=200').json()]
        assert [row[0] for row in exported[1:]]==expected
        assert not {'Cliente','Circuito'} & set(exported[0])


@pytest.mark.parametrize('format',['pdf','xlsx'])
@pytest.mark.parametrize('provider_filter',['all','none','specific'])
def test_combined_filters_and_provider_semantics(api_client,format,provider_filter,pdf_strings):
    p=payload(api_client)
    provider=api_client.post('/api/providers',json={'name':'Proveedor histórico'}).json()
    node=api_client.post('/api/nodes',json={'name':'Nodo histórico'}).json()
    person=api_client.post('/api/responsibles',json={'name':'Técnico histórico'}).json()
    items=[]
    for title,provider_id,start_at in [('INCIDENCIA-COMÚN-CON-PROVEEDOR',provider['id'],p['start_at']),('INCIDENCIA-COMÚN-SIN-PROVEEDOR',None,p['start_at']),('FUERA-DEL-PERÍODO',None,'2025-01-01T00:00:00Z')]:
        response=api_client.post('/api/internal-tickets',json={**p,'title':title,'provider_id':provider_id,'node_id':node['id'],'responsible_id':person['id'],'start_at':start_at})
        assert response.status_code==201,response.text
        items.append(response.json())
    api_client.patch('/api/providers/'+str(provider['id']),json={'active':False})
    filters=dict(search='INCIDENCIA-COMÚN',status='OPEN',sector_id=p['sector_id'],node_id=node['id'],department_id=p['department_id'],responsible_id=person['id'],incident_type_id=p['incident_type_id'],**{'from':'2026-10-15T14:00:00Z','to':'2026-10-16T00:00:00Z'})
    if provider_filter=='none':filters['without_provider']=True
    if provider_filter=='specific':filters['provider_id']=provider['id']
    expected=api_client.get('/api/internal-tickets',params=filters).json()
    assert len(expected)==(2 if provider_filter=='all' else 1)
    result=export(api_client,format,**filters)
    if format=='xlsx':
        book,rows=values(result)
        assert [row[0] for row in rows[1:]]==[row['reference'] for row in expected]
        assert rows[1][10]=='En curso'
        metadata=' '.join(row[0] for row in book['Filtros'].values)
        if provider_filter=='none':assert 'Atribuible a proveedor: Ninguno' in metadata
        if provider_filter=='specific':assert 'Proveedor histórico' in metadata
    else:
        text=' '.join(pdf_strings)
        for item in items:
            assert (item['reference'] in text)==any(row['id']==item['id'] for row in expected)


def test_internal_exports_duration_semantics_for_closed_and_open(api_client, pdf_strings):
    p = payload(api_client)
    closed_no_end = api_client.post('/api/internal-tickets', json={**p, 'title': 'Int Cerrado sin fin', 'status': 'CLOSED', 'end_at': None}).json()
    open_ticket = api_client.post('/api/internal-tickets', json={**p, 'title': 'Int Abierto sin fin', 'status': 'OPEN', 'end_at': None}).json()
    closed_with_end = api_client.post('/api/internal-tickets', json={**p, 'title': 'Int Cerrado con fin', 'status': 'CLOSED', 'end_at': '2026-10-15T15:30:00Z'}).json()

    book, rows = values(export(api_client, 'xlsx'))
    exported = {row[0]: row for row in rows[1:]}
    assert exported[closed_no_end['reference']][10] == 'Sin fecha de fin'
    assert exported[open_ticket['reference']][10] == 'En curso'
    assert exported[closed_with_end['reference']][10] == '1 h 30 min'

    export(api_client, 'pdf')
    text = ' '.join(pdf_strings)
    assert 'Sin fecha de fin' in text
    assert 'En curso' in text
    assert '1 h 30 min' in text


def test_export_parameters_and_literal_excel_text(api_client):
    p=payload(api_client)
    response=api_client.post('/api/internal-tickets',json={**p,'title':'=HYPERLINK("https://invalid")'})
    assert response.status_code==201
    book,rows=values(export(api_client))
    assert book['Tickets internos']['B2'].data_type=='s'
    assert rows[1][1].startswith('=HYPERLINK')
    for params in [{'timezone':'Invalid/Zone'},{'status':'WRONG'},{'from':'2026-10-16T00:00:00Z','to':'2026-10-15T00:00:00Z'}]:
        assert api_client.get('/api/internal-tickets/export/pdf',params=params).status_code==422
    assert api_client.get('/api/internal-tickets/export/csv').status_code==422
