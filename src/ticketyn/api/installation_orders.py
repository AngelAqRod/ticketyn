"""Installation order API, independent from activations."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from typing import Literal
from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import func, or_, select, text
from ticketyn.api.crud import DBSession, get_or_404
from ticketyn.api.distribution_data import distribution_write
from ticketyn.api.fms_data import validate_active
from ticketyn.models import Circuit, Customer, Node, Responsible, Sector
from ticketyn.models.service_type import ServiceType
from ticketyn.models.installation_orders import InstallationOrder as Order, InstallationRequest as Intake, InstallationDocument as Document, InstallationEvent as Event
from ticketyn.schemas.installation_orders import EXTRAORDINARY_FIELDS, OrderInput, OrderPatch, CircuitLink
from ticketyn.schemas.circuit import CircuitCreate

router = APIRouter(prefix='/api/installation-orders', tags=['installation-orders'])

def event(session, actor, action, *, order_id=None, request_id=None, detail=None):
    session.add(Event(actor_id=actor.id, action=action, order_id=order_id, request_id=request_id, detail=detail or {}))

def locked(session, model, id):
    item = session.scalar(select(model).where(model.id == id).with_for_update(of=model).execution_options(populate_existing=True))
    if item is None:
        raise HTTPException(404, 'No se encontró el registro.')
    return item

def dates(statement, column, date_from, date_to):
    tz = ZoneInfo('America/Guatemala')
    if date_from:
        statement = statement.where(column >= datetime.combine(date_from, time.min, tz))
    if date_to:
        statement = statement.where(column < datetime.combine(date_to + timedelta(days=1), time.min, tz))
    return statement

def document_data(item):
    return {key: getattr(item, key) for key in ('id', 'original_name', 'media_type', 'size', 'checksum', 'created_at')}

def event_data(item):
    return {key: getattr(item, key) for key in ('id', 'action', 'detail', 'actor_id', 'created_at')}

def named(row):
    return {'id': row.id, 'name': row.name} if row else None

def technical(session, item, circuit):
    """NORMAL orders read the circuit (single source of truth); EXTRAORDINARY orders read their own catalog references."""
    if item.order_type == 'NORMAL' and circuit:
        return {'service_type': named(circuit.service_type), 'node': named(circuit.node), 'sector': named(circuit.sector),
                'device': named(circuit.distribution_device), 'port': named(circuit.distribution_port), 'cpe': named(circuit.cpe_model)}
    if item.order_type == 'EXTRAORDINARY':
        return {'service_type': named(session.get(ServiceType, item.service_type_id)), 'node': named(session.get(Node, item.node_id)),
                'sector': named(session.get(Sector, item.sector_id)), 'device': None, 'port': None, 'cpe': None}
    return None

def site(item, circuit):
    """Address, GPS point and notes always come from the circuit; the order stores no copy."""
    if item.order_type != 'NORMAL' or not circuit:
        return None
    # Coordinates travel as strings, exactly like CircuitResponse (JSON floats would lose the fixed six decimals).
    return {key: str(value) if isinstance(value := getattr(circuit, key), Decimal) else value for key in ('address', 'latitude', 'longitude', 'additional_notes')}

def order_data(session, item):
    source_request = session.scalar(select(Intake).where(Intake.order_id == item.id))
    source = source_request.id if source_request else None
    customer = session.get(Customer, item.customer_id)
    author = session.get(Responsible, item.created_by)
    circuit = session.get(Circuit, item.circuit_id) if item.circuit_id else None
    documents = session.scalars(select(Document).where(or_(Document.order_id == item.id, Document.request_id == source) if source else Document.order_id == item.id).order_by(Document.id)).all()
    events = session.scalars(select(Event).where(or_(Event.order_id == item.id, Event.request_id == source) if source else Event.order_id == item.id).order_by(Event.id)).all()
    result = {key: getattr(item,key) for key in ('id','reference','order_type','external_reference','customer_id','service','location','description','service_type_id','node_id','sector_id','contact','phone','requested_at','notes','created_by','created_at','updated_at','circuit_id')}
    return {**result, 'technical': technical(session,item,circuit), 'circuit_location': site(item,circuit), 'customer': {'id':customer.id,'name':customer.name}, 'author': {'id':author.id,'name':author.name}, 'circuit': {'id':circuit.id,'circuit_code':circuit.circuit_code} if circuit else None, 'source_request_id':source, 'source_request':{key:getattr(source_request,key) for key in ('sender','subject','received_at','body','message_id')} if source_request else None, 'documents':[document_data(d) for d in documents], 'events':[event_data(e) for e in events]}

def validate_modality(session, values):
    """Backend rules for both modalities; the lock on the circuit serializes concurrent claims of the same circuit."""
    customer = get_or_404(session, Customer, values['customer_id'])
    if values['order_type'] == 'NORMAL':
        circuit = locked(session, Circuit, values['circuit_id'])
        if circuit.customer_id != customer.id:
            raise HTTPException(409, 'El circuito no pertenece al cliente seleccionado.')
        existing = session.scalar(select(Order.reference).where(Order.circuit_id == circuit.id))
        if existing:
            raise HTTPException(409, f'El circuito ya tiene la orden de instalación {existing}.')
    else:
        for model, key in ((ServiceType, 'service_type_id'), (Node, 'node_id'), (Sector, 'sector_id')):
            validate_active(session, model, values[key])

def insert_order(session, values, actor):
    validate_modality(session, values)
    id = session.scalar(text("SELECT nextval(pg_get_serial_sequence('installation_orders', 'id'))"))
    item = Order(**values, id=id, reference=f'OI-{id:06d}', created_by=actor.id)
    session.add(item)
    session.flush()
    event(session, actor, 'CREATE', order_id=item.id, detail={'order_type': item.order_type})
    return item

@router.get('')
def list_orders(session: DBSession, response: Response, customer_id: int | None=None, circuit_id: int | None=None, date_from: date | None=None, date_to: date | None=None, linked: bool | None=None, order_type: Literal['NORMAL','EXTRAORDINARY','UNCLASSIFIED'] | None=None, q: str | None=None, limit: int=Query(50,ge=1,le=200), offset: int=Query(0,ge=0)):
    stmt = select(Order).join(Customer, Order.customer_id == Customer.id)
    if customer_id: stmt = stmt.where(Order.customer_id == customer_id)
    if circuit_id: stmt = stmt.where(Order.circuit_id == circuit_id)
    if linked is not None: stmt = stmt.where(Order.circuit_id.is_not(None) if linked else Order.circuit_id.is_(None))
    if order_type: stmt = stmt.where(Order.order_type.is_(None) if order_type == 'UNCLASSIFIED' else Order.order_type == order_type)
    if q: stmt = stmt.where(or_(*(field.icontains(q,autoescape=True) for field in (Order.reference,Customer.name,Order.service,Order.description))))
    stmt = dates(stmt,Order.requested_at,date_from,date_to)
    response.headers['X-Total-Count'] = str(session.scalar(select(func.count()).select_from(stmt.subquery())))
    return [order_data(session,item) for item in session.scalars(stmt.order_by(Order.id.desc()).limit(limit).offset(offset))]

@router.post('',status_code=201)
def create_order(payload: OrderInput, session: DBSession, request: Request):
    with distribution_write(session):
        item = insert_order(session,payload.model_dump(),request.state.principal)
        session.flush()
        result = order_data(session,item)
    return result

@router.get('/{id}')
def get_order(id: int, session: DBSession):
    return order_data(session,get_or_404(session,Order,id))

@router.patch('/{id}')
def patch_order(id: int,payload: OrderPatch,session: DBSession,request: Request):
    with distribution_write(session):
        item = locked(session,Order,id)
        values = payload.model_dump(exclude_unset=True)
        specific = [key for key in EXTRAORDINARY_FIELDS if key in values]
        if specific and item.order_type != 'EXTRAORDINARY':
            raise HTTPException(422,'Descripción, servicio, nodo y sector solo aplican a órdenes extraordinarias.')
        required = ('customer_id','requested_at') + (EXTRAORDINARY_FIELDS if item.order_type == 'EXTRAORDINARY' else ())
        if any(values.get(key,True) is None for key in required):
            raise HTTPException(422,'Cliente, fecha y los datos propios del tipo de orden son obligatorios.')
        if 'customer_id' in values:
            get_or_404(session,Customer,values['customer_id'])
            if item.circuit_id and session.get(Circuit,item.circuit_id).customer_id != values['customer_id']:
                raise HTTPException(409,'El cliente debe coincidir con el circuito asociado.')
        for model,key in ((ServiceType,'service_type_id'),(Node,'node_id'),(Sector,'sector_id')):
            if key in values: validate_active(session,model,values[key])
        for key,value in values.items(): setattr(item,key,value)
        item.updated_at = datetime.now(timezone.utc)
        event(session,request.state.principal,'EDIT',order_id=id,detail={'fields':list(values)})
        session.flush(); result = order_data(session,item)
    return result

def unclassified_only(item):
    if item.order_type:
        raise HTTPException(409,'El tipo de orden es permanente: las órdenes normales y extraordinarias no pueden cambiar su circuito.')

@router.post('/{id}/circuit',status_code=201)
def create_circuit(id:int,payload:CircuitCreate,session:DBSession,request:Request):
    from ticketyn.api.circuit_creation import build_circuit
    with distribution_write(session):
        item = locked(session,Order,id)
        unclassified_only(item)
        if item.circuit_id: raise HTTPException(409,'La orden ya tiene un circuito asociado.')
        if item.customer_id != payload.customer_id: raise HTTPException(409,'El cliente debe coincidir con la orden.')
        circuit = build_circuit(session,payload,request.state.principal)
        item.circuit_id = circuit.id; item.order_type = 'NORMAL'
        event(session,request.state.principal,'LINK',order_id=id,detail={'circuit_id':circuit.id,'created':True})
        session.flush(); result=order_data(session,item)
    return result

@router.put('/{id}/circuit')
def link_circuit(id:int,payload:CircuitLink,session:DBSession,request:Request):
    with distribution_write(session):
        item = locked(session,Order,id)
        unclassified_only(item)
        circuit = locked(session,Circuit,payload.circuit_id)
        if item.circuit_id or session.scalar(select(Order.id).where(Order.circuit_id == circuit.id)):
            raise HTTPException(409,'La orden o el circuito ya tienen una asociación.')
        if circuit.customer_id != item.customer_id: raise HTTPException(409,'El cliente del circuito debe coincidir con la orden.')
        item.circuit_id=circuit.id; item.order_type='NORMAL'
        event(session,request.state.principal,'LINK',order_id=id,detail={'circuit_id':circuit.id})
        session.flush(); result=order_data(session,item)
    return result

@router.delete('/{id}/circuit')
def unlink_circuit(id:int,session:DBSession,request:Request):
    with distribution_write(session):
        item=locked(session,Order,id)
        unclassified_only(item)
        if not item.circuit_id: raise HTTPException(409,'La orden no tiene un circuito asociado.')
        previous=item.circuit_id; item.circuit_id=None
        event(session,request.state.principal,'UNLINK',order_id=id,detail={'circuit_id':previous})
        session.flush(); result=order_data(session,item)
    return result
