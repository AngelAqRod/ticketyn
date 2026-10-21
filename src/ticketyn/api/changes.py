from typing import Annotated, Literal
from fastapi import APIRouter, Path, Query, Request
from sqlalchemy import select, func
from ticketyn.api.crud import DBSession, get_or_404, list_items, save_item, update_item
from ticketyn.api import change_data as data
from ticketyn.models import MaintenanceChange as Change, ChangeType, ChangeCompletionType, ChangeNumberConfig, ChangeUpdate, ChangeAudit, Responsible
from ticketyn.schemas.change import ChangeCreate, ChangePatch, ChangeFilters, ChangeUpdateCreate, CompletionCreate, CompletionPatch, CompletionResponse, ChangeTypeCreate, ChangeTypePatch, ChangeTypeResponse
from ticketyn.schemas.ticket_number_config import TicketNumberConfigResponse, TicketNumberConfigUpdate
from ticketyn.api.ticket_numbers import locked_number_config, validate_number_config

router=APIRouter(tags=['changes'])
RootId=Annotated[int,Path(gt=0)]

@router.get('/api/change-types',response_model=list[ChangeTypeResponse])
def change_types(session:DBSession,search:str|None=None,include_inactive:bool=False,limit:Annotated[int,Query(ge=1,le=200)]=50,offset:Annotated[int,Query(ge=0)]=0):
    return list_items(session,ChangeType,search=search,search_fields=('name',),order_field='name',include_inactive=include_inactive,limit=limit,offset=offset)

@router.post('/api/change-types',response_model=ChangeTypeResponse,status_code=201)
def create_change_type(payload:ChangeTypeCreate,session:DBSession):
    return save_item(session,ChangeType(**payload.model_dump()))

@router.get('/api/change-types/{id}',response_model=ChangeTypeResponse)
def get_change_type(id:RootId,session:DBSession):return get_or_404(session,ChangeType,id)

@router.patch('/api/change-types/{id}',response_model=ChangeTypeResponse)
def patch_change_type(id:RootId,payload:ChangeTypePatch,session:DBSession):
    return update_item(session,get_or_404(session,ChangeType,id),payload.model_dump(exclude_unset=True))

@router.get('/api/change-completion-types',response_model=list[CompletionResponse])
def completion_types(session:DBSession,search:str|None=None,include_inactive:bool=False,limit:Annotated[int,Query(ge=1,le=200)]=50,offset:Annotated[int,Query(ge=0)]=0):
    return list_items(session,ChangeCompletionType,search=search,search_fields=('name',),order_field='name',include_inactive=include_inactive,limit=limit,offset=offset)

@router.post('/api/change-completion-types',response_model=CompletionResponse,status_code=201)
def create_type(payload:CompletionCreate,session:DBSession):
    return save_item(session,ChangeCompletionType(**payload.model_dump()))

@router.get('/api/change-completion-types/{id}',response_model=CompletionResponse)
def get_type(id:RootId,session:DBSession):return get_or_404(session,ChangeCompletionType,id)

@router.patch('/api/change-completion-types/{id}',response_model=CompletionResponse)
def patch_type(id:RootId,payload:CompletionPatch,session:DBSession):
    return update_item(session,get_or_404(session,ChangeCompletionType,id),payload.model_dump(exclude_unset=True))

@router.get('/api/settings/change-number',response_model=TicketNumberConfigResponse)
def number_config(session:DBSession):return save_item(session,locked_number_config(session,ChangeNumberConfig))

@router.patch('/api/settings/change-number',response_model=TicketNumberConfigResponse)
def patch_number(payload:TicketNumberConfigUpdate,session:DBSession):
    try:
        config=locked_number_config(session,ChangeNumberConfig);values=payload.model_dump(exclude_unset=True)
        validate_number_config(session,config,values,Ticket=Change)
        return update_item(session,config,values)
    except Exception:session.rollback();raise

@router.get('/api/changes')
def listing(session:DBSession,filters:Annotated[ChangeFilters,Query()]):
    q=data.statement(filters)
    return {'total':session.scalar(select(func.count()).select_from(q.order_by(None).subquery())), 'items':[data.response(item) for item in session.scalars(q.limit(filters.limit).offset(filters.offset))]}

@router.post('/api/changes',status_code=201)
def create(payload:ChangeCreate,session:DBSession,request:Request):return data.response(data.persist(session,payload.model_dump(),actor=request.state.principal))

@router.get('/api/changes/{id}')
def detail(id:RootId,session:DBSession):return data.response(get_or_404(session,Change,id))

@router.patch('/api/changes/{id}')
def patch(id:RootId,payload:ChangePatch,session:DBSession,request:Request):return data.response(data.persist(session,payload.model_dump(exclude_unset=True),id,actor=request.state.principal))

@router.get('/api/changes/{id}/updates')
def updates(id:RootId,session:DBSession,limit:Annotated[int,Query(ge=1,le=200)]=50,offset:Annotated[int,Query(ge=0)]=0):
    get_or_404(session,Change,id)
    q=select(ChangeUpdate).where(ChangeUpdate.change_id==id)
    return {'total':session.scalar(select(func.count()).select_from(q.subquery())),'items':list(session.scalars(q.order_by(ChangeUpdate.occurred_at,ChangeUpdate.id).limit(limit).offset(offset)))}

@router.post('/api/changes/{id}/updates',status_code=201)
def add_update(id:RootId,payload:ChangeUpdateCreate,session:DBSession):
    get_or_404(session,Change,id)
    person=data.active_relation(session,Responsible,payload.responsible_id)
    return save_item(session,ChangeUpdate(change_id=id,responsible_name=person.name,**payload.model_dump()))

@router.get('/api/changes/{id}/audit')
def audit(id:RootId,session:DBSession,limit:Annotated[int,Query(ge=1,le=200)]=50,offset:Annotated[int,Query(ge=0)]=0):
    get_or_404(session,Change,id)
    return list(session.scalars(select(ChangeAudit).where(ChangeAudit.change_id==id).order_by(ChangeAudit.id.desc()).limit(limit).offset(offset)))
