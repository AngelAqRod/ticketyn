"""Human validation of retained incoming installation requests."""
from datetime import date, datetime, timezone
import json
from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import func, or_, select
from ticketyn.api.crud import DBSession, get_or_404
from ticketyn.api.distribution_data import distribution_write
from ticketyn.api.installation_orders import dates, document_data, event_data, event, locked, insert_order, order_data
from ticketyn.models import Responsible
from ticketyn.models.installation_orders import InstallationRequest as Intake, InstallationRequestDraft as Draft, InstallationDocument as Document, InstallationEvent as Event
from ticketyn.schemas.installation_orders import DraftInput, ProcessInput, DiscardInput

router=APIRouter(prefix='/api/installation-requests',tags=['installation-requests'])

def request_data(session,item):
    draft=session.get(Draft,item.id)
    reviewer=session.get(Responsible,item.reviewer_id) if item.reviewer_id else None
    documents=session.scalars(select(Document).where(Document.request_id==item.id).order_by(Document.id)).all()
    result={key:getattr(item,key) for key in ('id','sender','subject','body','received_at','state','order_id','message_id','checksum','discard_reason')}
    return {**result,'reviewer':{'id':reviewer.id,'name':reviewer.name} if reviewer else None,'draft':{'data':draft.data,'version':draft.version} if draft else None,'has_draft':draft is not None,'attachment_count':sum(d.media_type!='message/rfc822' for d in documents),'documents':[document_data(d) for d in documents],'events':[event_data(e) for e in session.scalars(select(Event).where(Event.request_id==item.id).order_by(Event.id))]}

def editable(item):
    if item.state not in ('PENDING','REVIEWING'): raise HTTPException(409,'La solicitud ya fue procesada o descartada.')

@router.get('/summary')
def summary(session:DBSession):
    counts=dict(session.execute(select(Intake.state,func.count()).group_by(Intake.state)).all())
    return {'pending':counts.get('PENDING',0),'reviewing':counts.get('REVIEWING',0),'processed':counts.get('PROCESSED',0),'discarded':counts.get('DISCARDED',0),'to_attend':counts.get('PENDING',0)+counts.get('REVIEWING',0)}

@router.get('')
def list_requests(session:DBSession,response:Response,state:str|None=None,pending:bool=False,date_from:date|None=None,date_to:date|None=None,sender:str|None=None,subject:str|None=None,q:str|None=None,has_draft:bool|None=None,limit:int=Query(50,ge=1,le=200),offset:int=Query(0,ge=0)):
    stmt=select(Intake)
    if state:
        if state not in ('PENDING','REVIEWING','PROCESSED','DISCARDED'): raise HTTPException(422,'Estado no válido.')
        stmt=stmt.where(Intake.state==state)
    if pending: stmt=stmt.where(Intake.state.in_(('PENDING','REVIEWING')))
    if sender: stmt=stmt.where(Intake.sender.icontains(sender,autoescape=True))
    if subject: stmt=stmt.where(Intake.subject.icontains(subject,autoescape=True))
    if q: stmt=stmt.where(or_(Intake.sender.icontains(q,autoescape=True),Intake.subject.icontains(q,autoescape=True)))
    if has_draft is not None:
        exists=select(Draft.request_id).where(Draft.request_id==Intake.id).exists()
        stmt=stmt.where(exists if has_draft else ~exists)
    stmt=dates(stmt,Intake.received_at,date_from,date_to)
    response.headers['X-Total-Count']=str(session.scalar(select(func.count()).select_from(stmt.subquery())))
    return [request_data(session,item) for item in session.scalars(stmt.order_by(Intake.received_at.desc(),Intake.id.desc()).limit(limit).offset(offset))]

@router.get('/{id}')
def get_request(id:int,session:DBSession): return request_data(session,get_or_404(session,Intake,id))

@router.post('/{id}/review')
def review(id:int,session:DBSession,request:Request):
    with distribution_write(session):
        item=locked(session,Intake,id); editable(item)
        item.state='REVIEWING'; item.reviewer_id=request.state.principal.id
        event(session,request.state.principal,'REVIEW',request_id=id)
        session.flush(); result=request_data(session,item)
    return result

@router.put('/{id}/draft')
def save_draft(id:int,payload:DraftInput,session:DBSession,request:Request):
    if len(json.dumps(payload.data))>100000: raise HTTPException(413,'El borrador supera el tamaño permitido.')
    with distribution_write(session):
        item=locked(session,Intake,id); editable(item)
        draft=session.get(Draft,id)
        if payload.version != (draft.version if draft else 0): raise HTTPException(409,'El borrador cambió. Actualiza antes de guardar.')
        if draft is None:
            draft=Draft(request_id=id,data={},version=0,updated_by=request.state.principal.id); session.add(draft)
        draft.data=payload.data; draft.version+=1; draft.updated_by=request.state.principal.id; draft.updated_at=datetime.now(timezone.utc)
        item.state='REVIEWING'; item.reviewer_id=request.state.principal.id
        event(session,request.state.principal,'DRAFT',request_id=id,detail={'version':draft.version})
        session.flush(); result=request_data(session,item)
    return result

@router.post('/{id}/process',status_code=201)
def process(id:int,payload:ProcessInput,session:DBSession,request:Request):
    with distribution_write(session):
        item=locked(session,Intake,id); editable(item)
        draft=session.get(Draft,id)
        if payload.version != (draft.version if draft else 0): raise HTTPException(409,'El borrador cambió. Actualiza antes de registrar la orden.')
        order=insert_order(session,payload.model_dump(exclude={'version'}),request.state.principal)
        item.order_id=order.id; item.state='PROCESSED'; item.reviewer_id=request.state.principal.id
        event(session,request.state.principal,'PROCESS',request_id=id,order_id=order.id)
        session.flush(); result=order_data(session,order)
    return result

@router.post('/{id}/discard')
def discard(id:int,payload:DiscardInput,session:DBSession,request:Request):
    with distribution_write(session):
        item=locked(session,Intake,id); editable(item)
        item.state='DISCARDED'; item.discard_reason=payload.reason; item.reviewer_id=request.state.principal.id
        event(session,request.state.principal,'DISCARD',request_id=id,detail={'reason':payload.reason})
        session.flush(); result=request_data(session,item)
    return result
