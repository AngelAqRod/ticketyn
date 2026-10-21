"""Recent-only sector corrections; all databases are disposable test fixtures."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import event, select, update, func
from sqlalchemy.orm import Session

from ticketyn.api import circuit_ticket_sectors as sync
from ticketyn.api.circuits import patch_circuit
from ticketyn.api.ticket_data import create_ticket
from ticketyn.models import Circuit, Sector, Ticket, TicketUpdate
from ticketyn.schemas.circuit import CircuitUpdate
from test_ticket_concurrency import concurrent_database


@pytest.fixture
def correction_clock(monkeypatch):
    clock=[datetime(2026,10,16,18,0,0,tzinfo=timezone.utc)]
    monkeypatch.setattr(sync,'correction_time',lambda session:clock[0])
    return clock


def new_sector(client,name='Sector corregido'):
    response=client.post('/api/sectors',json={'name':name})
    assert response.status_code==201,response.text
    return response.json()


def ticket(client,session,payload,created_at,**values):
    response=client.post('/api/tickets',json={**payload,**values})
    assert response.status_code==201,response.text
    id=response.json()['id']
    session.execute(update(Ticket).where(Ticket.id==id).values(created_at=created_at,updated_at=datetime(2026,10,16,17,59,tzinfo=timezone.utc)))
    session.commit();session.expire_all()
    return id


def snapshot(session,id):
    return dict(session.execute(select(Ticket.__table__).where(Ticket.id==id)).mappings().one())


def history(session,id):
    return [dict(row) for row in session.execute(select(TicketUpdate.__table__).where(TicketUpdate.ticket_id==id).order_by(TicketUpdate.id)).mappings()]


@pytest.mark.parametrize('status',['OPEN','CLOSED'])
@pytest.mark.parametrize('age,eligible',[
    (timedelta(days=1),True),(timedelta(days=3),True),(timedelta(hours=168),True),
    (timedelta(hours=168,microseconds=1),False),(timedelta(days=8),False),
    (timedelta(days=30),False),(timedelta(days=180),False),
    (timedelta(0),True),(timedelta(seconds=-1),False),
])
def test_exact_creation_window_preserves_every_other_field(api_client,ticket_payload,db_session,correction_clock,status,age,eligible):
    now=correction_clock[0];sector=new_sector(api_client)
    # The incident occurred years ago, but eligibility depends only on creation.
    id=ticket(api_client,db_session,ticket_payload,now-age,status=status,end_at='2020-01-01T13:00:00Z' if status=='CLOSED' else None)
    before=snapshot(db_session,id)
    response=api_client.patch(f"/api/circuits/{ticket_payload['circuit_id']}",json={'sector_id':sector['id']})
    assert response.status_code==200,response.text
    after=snapshot(db_session,id)
    assert after=={**before,'sector_id':sector['id'] if eligible else before['sector_id']}
    logs=history(db_session,id)
    assert len(logs)==int(eligible)
    if eligible:
        assert logs[0]['content']=='Sector actualizado automáticamente de «Sector de prueba» a «Sector corregido» por modificación del circuito asociado.'
        assert logs[0]['occurred_at']==now and logs[0]['created_at']==now
        assert logs[0]['responsible_id'] is None and logs[0]['escalation_id'] is None
        assert logs[0]['visibility']=='INTERNAL'
        # Existing API can read the generated evidence, without a human identity.
        entry=api_client.get(f'/api/tickets/{id}/updates').json()[0]
        assert entry['content']==logs[0]['content'] and entry['responsible'] is None


def test_unchanged_and_unrelated_circuits_and_existing_history(api_client,ticket_payload,db_session,correction_clock):
    now=correction_clock[0];new=new_sector(api_client)
    id=ticket(api_client,db_session,ticket_payload,now-timedelta(days=1))
    assert api_client.post(f'/api/tickets/{id}/updates',json={'content':'Intervención original','occurred_at':ticket_payload['start_at']}).status_code==201
    original_history=history(db_session,id)
    already=ticket(api_client,db_session,ticket_payload,now-timedelta(days=1))
    db_session.execute(update(Ticket).where(Ticket.id==already).values(sector_id=new['id'],updated_at=Ticket.updated_at));db_session.commit()
    other=api_client.post('/api/circuits',json={'customer_id':ticket_payload['customer_id'],'node_id':ticket_payload['node_id'],'sector_id':ticket_payload['sector_id'],'circuit_code':'OTRO-CIRCUITO','description':'Otro enlace'}).json()
    unrelated=ticket(api_client,db_session,{**ticket_payload,'circuit_id':other['id']},now-timedelta(days=1))
    before_other=snapshot(db_session,unrelated);before_already=snapshot(db_session,already)
    cid=ticket_payload['circuit_id']
    assert api_client.patch(f'/api/circuits/{cid}',json={'description':'Solo descripción'}).status_code==200
    assert history(db_session,id)==original_history
    assert api_client.patch(f'/api/circuits/{cid}',json={'sector_id':ticket_payload['sector_id']}).status_code==200
    assert history(db_session,id)==original_history
    assert api_client.patch(f'/api/circuits/{cid}',json={'sector_id':new['id']}).status_code==200
    assert history(db_session,id)[:-1]==original_history
    assert snapshot(db_session,unrelated)==before_other and history(db_session,unrelated)==[]
    assert snapshot(db_session,already)==before_already and history(db_session,already)==[]
    assert api_client.patch(f'/api/circuits/{cid}',json={'sector_id':new['id']}).status_code==200
    assert len(history(db_session,id))==len(original_history)+1


def test_change_without_tickets_and_invalid_sector(api_client,ticket_payload,db_session,correction_clock):
    cid=ticket_payload['circuit_id'];new=new_sector(api_client)
    assert api_client.patch(f'/api/circuits/{cid}',json={'sector_id':999999}).status_code==404
    assert api_client.patch(f'/api/circuits/{cid}',json={'sector_id':new['id']}).status_code==200
    assert db_session.scalar(select(func.count()).select_from(TicketUpdate))==0


def test_second_change_uses_new_window_and_ticket_previous_sector(api_client,ticket_payload,db_session,correction_clock):
    now=correction_clock[0];first=new_sector(api_client,'Sector intermedio');second=new_sector(api_client,'Sector final')
    aging=ticket(api_client,db_session,ticket_payload,now-timedelta(hours=167))
    recent=ticket(api_client,db_session,ticket_payload,now-timedelta(hours=1))
    cid=ticket_payload['circuit_id']
    assert api_client.patch(f'/api/circuits/{cid}',json={'sector_id':first['id']}).status_code==200
    correction_clock[0]+=timedelta(hours=2)
    assert api_client.patch(f'/api/circuits/{cid}',json={'sector_id':second['id']}).status_code==200
    assert snapshot(db_session,aging)['sector_id']==first['id'] and len(history(db_session,aging))==1
    assert snapshot(db_session,recent)['sector_id']==second['id'] and len(history(db_session,recent))==2
    assert history(db_session,recent)[1]['content']=='Sector actualizado automáticamente de «Sector intermedio» a «Sector final» por modificación del circuito asociado.'
    assert history(db_session,recent)[1]['occurred_at']==correction_clock[0]


def test_circuit_save_failure_rolls_back_ticket_and_history(api_client,ticket_payload,db_session,correction_clock):
    new=new_sector(api_client);cid=ticket_payload['circuit_id']
    id=ticket(api_client,db_session,ticket_payload,correction_clock[0]-timedelta(days=1))
    duplicate=api_client.post('/api/circuits',json={'customer_id':ticket_payload['customer_id'],'node_id':ticket_payload['node_id'],'sector_id':ticket_payload['sector_id'],'circuit_code':'DUPLICADO','description':'Otro circuito'}).json()
    before=snapshot(db_session,id)
    response=api_client.patch(f'/api/circuits/{cid}',json={'sector_id':new['id'],'circuit_code':duplicate['circuit_code']})
    assert response.status_code==409,response.text
    assert snapshot(db_session,id)==before and history(db_session,id)==[]
    assert api_client.get(f'/api/circuits/{cid}').json()['sector_id']==ticket_payload['sector_id']


def test_history_failure_rolls_back_circuit_and_tickets(api_client,ticket_payload,db_session,correction_clock):
    new=new_sector(api_client);id=ticket(api_client,db_session,ticket_payload,correction_clock[0]-timedelta(days=1))
    before=snapshot(db_session,id);connection=db_session.connection()
    def reject_history(conn,cursor,statement,parameters,context,many):
        if 'INSERT INTO ticket_updates' in statement:raise RuntimeError('Fallo de bitácora simulado')
    event.listen(connection,'before_cursor_execute',reject_history)
    try:
        with pytest.raises(RuntimeError,match='Fallo de bitácora simulado'):
            api_client.patch(f"/api/circuits/{ticket_payload['circuit_id']}",json={'sector_id':new['id']})
    finally:event.remove(connection,'before_cursor_execute',reject_history)
    assert snapshot(db_session,id)==before and history(db_session,id)==[]
    assert api_client.get(f"/api/circuits/{ticket_payload['circuit_id']}").json()['sector_id']==ticket_payload['sector_id']


def test_ticket_lock_conflict_is_atomic_and_retryable(concurrent_database,correction_clock):
    from types import SimpleNamespace
    from ticketyn.security.permissions import DEFAULT_GRANTS
    request=SimpleNamespace(state=SimpleNamespace(principal=SimpleNamespace(permissions=DEFAULT_GRANTS['SUPERADMIN'])))
    engine,payload=concurrent_database
    with Session(engine) as session:
        new=Sector(name='Sector corregido');session.add(new);session.commit();sector_id=new.id
        item=create_ticket(session,payload.copy());id=item.id
        session.execute(update(Ticket).where(Ticket.id==id).values(created_at=correction_clock[0]-timedelta(days=1),updated_at=Ticket.updated_at));session.commit()
    with Session(engine) as holder:
        holder.execute(select(Ticket.id).where(Ticket.id==id).with_for_update())
        with Session(engine) as contender:
            with pytest.raises(HTTPException) as failure:
                patch_circuit(payload['circuit_id'],CircuitUpdate(sector_id=sector_id),contender,request)
            assert failure.value.status_code==409
            assert contender.scalar(select(Circuit.sector_id).where(Circuit.id==payload['circuit_id']))==payload['sector_id']
            assert contender.scalar(select(func.count()).select_from(TicketUpdate))==0
    with Session(engine) as session:
        patch_circuit(payload['circuit_id'],CircuitUpdate(sector_id=sector_id),session,request)
        assert snapshot(session,id)['sector_id']==sector_id and len(history(session,id))==1


def test_other_fields_never_invoke_sync(api_client,ticket_payload,monkeypatch):
    from ticketyn.api import circuits
    def unexpected(*args):pytest.fail('No debe sincronizar un sector que no cambió')
    monkeypatch.setattr(circuits,'synchronize_recent_ticket_sectors',unexpected)
    cid=ticket_payload['circuit_id']
    assert api_client.patch(f'/api/circuits/{cid}',json={'description':'Descripción corregida'}).status_code==200
    assert api_client.patch(f'/api/circuits/{cid}',json={'sector_id':ticket_payload['sector_id']}).status_code==200
    assert api_client.patch(f'/api/circuits/{cid}/cpe-configuration',json={'configuration':'/system identity'}).status_code==200


def test_bulk_sql_is_bounded_and_does_not_touch_internal_tickets(api_client,ticket_payload,db_session,correction_clock):
    from test_internal_tickets import payload as internal_payload
    from ticketyn.models import InternalTicket
    internal=api_client.post('/api/internal-tickets',json=internal_payload(api_client)).json()
    internal_before=dict(db_session.execute(select(InternalTicket.__table__).where(InternalTicket.id==internal['id'])).mappings().one())
    new=new_sector(api_client)
    id=ticket(api_client,db_session,ticket_payload,correction_clock[0]-timedelta(days=1))
    base=snapshot(db_session,id);base.pop('id')
    copies=[]
    for index in range(1,61):
        copies.append({**base,'ticket_number':base['ticket_number']+index,'reference':f'BULK-SYNC-{index}',
                       'created_at':correction_clock[0]-timedelta(days=1 if index<=40 else 30)})
    db_session.execute(Ticket.__table__.insert(),copies);db_session.commit()
    statements=[];connection=db_session.connection()
    def capture(conn,cursor,statement,parameters,context,many):
        if 'eligible_ticket_sectors' in statement:statements.append(statement)
    event.listen(connection,'before_cursor_execute',capture)
    try:
        response=api_client.patch(f"/api/circuits/{ticket_payload['circuit_id']}",json={'sector_id':new['id']})
        assert response.status_code==200,response.text
    finally:event.remove(connection,'before_cursor_execute',capture)
    assert len(statements)==1
    sql=statements[0]
    assert 'tickets.circuit_id =' in sql and 'tickets.created_at >=' in sql and 'tickets.created_at <=' in sql
    assert 'tickets.status' not in sql and 'INSERT INTO ticket_updates' in sql
    assert db_session.scalar(select(func.count()).select_from(TicketUpdate))==41
    assert dict(db_session.execute(select(InternalTicket.__table__).where(InternalTicket.id==internal['id'])).mappings().one())==internal_before


def test_correction_clock_uses_database_wall_time(db_session):
    before=db_session.scalar(select(func.clock_timestamp()))
    result=sync.correction_time(db_session)
    after=db_session.scalar(select(func.clock_timestamp()))
    assert before<=result<=after and result.utcoffset()==timedelta(0)
