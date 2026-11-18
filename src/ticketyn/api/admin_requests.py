"""Administrative requests: operational log with optional links to existing records."""
from datetime import timedelta
from typing import Annotated
from fastapi import APIRouter, HTTPException, Path, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from ticketyn.api.change_data import active_relation
from ticketyn.api.crud import DBSession, get_or_404, list_items, save_item, update_item
from ticketyn.api.installation_orders import dates
from ticketyn.api.ticket_numbers import format_reference, locked_number_config
from ticketyn.models import (AdminRequest, AdminRequestEvent, AdminRequestLink, AdminRequestNumberConfig, AdminRequestType, Circuit,
                             Customer, InternalTicket, MaintenanceChange as Change, Responsible, Ticket)
from ticketyn.schemas.admin_request import (AdminRequestCreate, AdminRequestFilters, AdminRequestLinkCreate, AdminRequestPatch, AdminRequestStatusChange,
                                            AdminRequestTypeCreate, AdminRequestTypePatch, AdminRequestTypeResponse, PERIOD_ERROR)
from ticketyn.schemas.ticket_number_config import TicketNumberConfigResponse, TicketNumberConfigUpdate
from ticketyn.api.ticket_numbers import validate_number_config

router = APIRouter(tags=['admin-requests'])
RootId = Annotated[int, Path(gt=0)]
WINDOW_DAYS = 15
# Manual workflow; reopening a finished request is a normal transition. Dates never move the status.
TRANSITIONS = {'REGISTERED': {'IN_PROGRESS', 'CANCELLED'}, 'IN_PROGRESS': {'REGISTERED', 'COMPLETED', 'CANCELLED'},
               'COMPLETED': {'REGISTERED', 'IN_PROGRESS'}, 'CANCELLED': {'REGISTERED', 'IN_PROGRESS'}}
# kind -> (model, link column, module date column, label columns)
KINDS = {'ticket': (Ticket, 'ticket_id', Ticket.start_at), 'internal_ticket': (InternalTicket, 'internal_ticket_id', InternalTicket.start_at),
         'change': (Change, 'change_id', Change.proposed_start)}


@router.get('/api/admin-request-types', response_model=list[AdminRequestTypeResponse])
def types(session: DBSession, search: str | None = None, include_inactive: bool = False, limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Annotated[int, Query(ge=0)] = 0):
    return list_items(session, AdminRequestType, search=search, search_fields=('name',), order_field='name', include_inactive=include_inactive, limit=limit, offset=offset)


@router.post('/api/admin-request-types', response_model=AdminRequestTypeResponse, status_code=201)
def create_type(payload: AdminRequestTypeCreate, session: DBSession):
    return save_item(session, AdminRequestType(**payload.model_dump()))


@router.get('/api/admin-request-types/{id}', response_model=AdminRequestTypeResponse)
def get_type(id: RootId, session: DBSession):
    return get_or_404(session, AdminRequestType, id)


@router.patch('/api/admin-request-types/{id}', response_model=AdminRequestTypeResponse)
def patch_type(id: RootId, payload: AdminRequestTypePatch, session: DBSession):
    return update_item(session, get_or_404(session, AdminRequestType, id), payload.model_dump(exclude_unset=True))


@router.get('/api/settings/admin-request-number', response_model=TicketNumberConfigResponse)
def number_config(session: DBSession):
    return save_item(session, locked_number_config(session, AdminRequestNumberConfig))


@router.patch('/api/settings/admin-request-number', response_model=TicketNumberConfigResponse)
def patch_number(payload: TicketNumberConfigUpdate, session: DBSession):
    try:
        config = locked_number_config(session, AdminRequestNumberConfig)
        values = payload.model_dump(exclude_unset=True)
        validate_number_config(session, config, values, Ticket=AdminRequest)
        return update_item(session, config, values)
    except Exception:
        session.rollback()
        raise


def event(session, actor, request_id, action, detail=None):
    session.add(AdminRequestEvent(request_id=request_id, actor_id=actor.id, action=action, detail=detail or {}))


def label(kind, row):
    date = {'ticket': 'start_at', 'internal_ticket': 'start_at', 'change': 'proposed_start'}[kind]
    return {'id': row.id, 'reference': row.reference, 'title': row.title, 'date': getattr(row, date)}


def response(session, item):
    base = {key: getattr(item, key) for key in ('id', 'reference', 'request_date', 'requester_id', 'customer_id', 'circuit_id', 'type_id', 'description', 'notes', 'status', 'application_start', 'application_end', 'created_by', 'created_at', 'updated_at')}
    names = {model: dict(session.execute(select(model.id, model.name).where(model.id.in_(ids))).all()) for model, ids in
             ((Responsible, {item.requester_id, item.created_by}), (Customer, {item.customer_id} - {None}), (AdminRequestType, {item.type_id}))}
    circuit = session.get(Circuit, item.circuit_id) if item.circuit_id else None
    links = {kind: [] for kind in KINDS}
    for link in item.links:
        kind, (model, column, _) = next((k, v) for k, v in KINDS.items() if getattr(link, v[1]) is not None)
        links[kind].append({'link_id': link.id, **label(kind, session.get(model, getattr(link, column)))})
    events = session.scalars(select(AdminRequestEvent).where(AdminRequestEvent.request_id == item.id).order_by(AdminRequestEvent.id)).all()
    return {**base, 'requester': {'id': item.requester_id, 'name': names[Responsible][item.requester_id]}, 'registered_by': {'id': item.created_by, 'name': names[Responsible][item.created_by]},
            'customer': {'id': item.customer_id, 'name': names[Customer][item.customer_id]} if item.customer_id else None,
            'circuit': {'id': circuit.id, 'circuit_code': circuit.circuit_code} if circuit else None,
            'type': {'id': item.type_id, 'name': names[AdminRequestType][item.type_id]}, 'links': {'tickets': links['ticket'], 'internal_tickets': links['internal_ticket'], 'changes': links['change']},
            'events': [{'id': e.id, 'action': e.action, 'detail': e.detail, 'actor_id': e.actor_id, 'created_at': e.created_at} for e in events]}


def locked(session, id):
    item = session.scalar(select(AdminRequest).where(AdminRequest.id == id).with_for_update(of=AdminRequest).execution_options(populate_existing=True))
    if item is None:
        raise HTTPException(404, 'Solicitud administrativa no encontrada')
    return item


def validate_context(session, values, item=None):
    """Check only relations that change, so historical inactive ones stay editable; circuit must belong to the customer."""
    for field, model in (('requester_id', Responsible), ('type_id', AdminRequestType), ('customer_id', Customer), ('circuit_id', Circuit)):
        if values.get(field) and (item is None or values[field] != getattr(item, field)):
            active_relation(session, model, values[field])
    if values.get('circuit_id'):
        circuit = session.get(Circuit, values['circuit_id'])
        if values.get('customer_id') is None:
            values['customer_id'] = circuit.customer_id  # shortcut: a circuit alone implies its customer
        elif circuit.customer_id != values['customer_id']:
            raise HTTPException(422, 'El circuito no pertenece al cliente seleccionado')


@router.get('/api/admin-requests')
def listing(session: DBSession, filters: Annotated[AdminRequestFilters, Query()]):
    q = select(AdminRequest)
    for field in ('requester_id', 'type_id', 'customer_id', 'circuit_id'):
        if getattr(filters, field) is not None:
            q = q.where(getattr(AdminRequest, field) == getattr(filters, field))
    if filters.status:
        q = q.where(AdminRequest.status == filters.status)
    if filters.date_from:
        q = q.where(AdminRequest.request_date >= filters.date_from)
    if filters.date_to:
        q = q.where(AdminRequest.request_date <= filters.date_to)
    if filters.search:
        q = q.where(or_(AdminRequest.reference.icontains(filters.search, autoescape=True), AdminRequest.description.icontains(filters.search, autoescape=True)))
    total = session.scalar(select(func.count()).select_from(q.subquery()))
    rows = session.scalars(q.order_by(AdminRequest.request_date.desc(), AdminRequest.id.desc()).limit(filters.limit).offset(filters.offset)).all()
    return {'total': total, 'items': [response(session, row) for row in rows]}


@router.post('/api/admin-requests', status_code=201)
def create(payload: AdminRequestCreate, session: DBSession, request: Request):
    actor = request.state.principal
    try:
        values = payload.model_dump()
        validate_context(session, values)
        config = locked_number_config(session, AdminRequestNumberConfig)
        if config.next_number >= 2147483647:
            raise HTTPException(409, 'Numeración agotada')
        item = AdminRequest(**values, ticket_number=config.next_number, reference=format_reference(config.prefix, config.separator, config.next_number, config.padding), created_by=actor.id)
        config.next_number += 1
        session.add(item)
        session.flush()
        event(session, actor, item.id, 'CREATE')
        session.commit()
        return response(session, item)
    except Exception:
        session.rollback()
        raise


@router.get('/api/admin-requests/{id}')
def detail(id: RootId, session: DBSession):
    return response(session, get_or_404(session, AdminRequest, id))


@router.patch('/api/admin-requests/{id}')
def patch(id: RootId, payload: AdminRequestPatch, session: DBSession, request: Request):
    try:
        item = locked(session, id)
        values = payload.model_dump(exclude_unset=True)
        if any(values.get(k, True) is None for k in ('request_date', 'requester_id', 'type_id', 'description')):
            raise HTTPException(422, 'Fecha, solicitante, tipo y descripción son obligatorios')
        final = {k: values.get(k, getattr(item, k)) for k in ('request_date', 'requester_id', 'customer_id', 'circuit_id', 'type_id', 'description', 'notes', 'application_start', 'application_end')}
        if final['application_start'] and final['application_end'] and final['application_end'] < final['application_start']:
            raise HTTPException(422, PERIOD_ERROR)
        validate_context(session, final, item)
        changed = {k: v for k, v in final.items() if getattr(item, k) != v}
        for key, value in changed.items():
            setattr(item, key, value)
        if changed:
            event(session, request.state.principal, id, 'EDIT', {'fields': sorted(changed)})
        session.commit()
        return response(session, item)
    except Exception:
        session.rollback()
        raise


@router.post('/api/admin-requests/{id}/status')
def change_status(id: RootId, payload: AdminRequestStatusChange, session: DBSession, request: Request):
    try:
        item = locked(session, id)
        if payload.status not in TRANSITIONS[item.status]:
            raise HTTPException(422, 'La transición de estado no está permitida')
        event(session, request.state.principal, id, 'STATUS', {'from': item.status, 'to': payload.status})
        item.status = payload.status
        session.commit()
        return response(session, item)
    except Exception:
        session.rollback()
        raise


def candidates(session, id, kind, search, limit, offset):
    item = get_or_404(session, AdminRequest, id)
    model, _, date_column = KINDS[kind]
    q = dates(select(model), date_column, item.request_date - timedelta(days=WINDOW_DAYS), item.request_date + timedelta(days=WINDOW_DAYS))
    if kind == 'ticket':
        if item.circuit_id:
            q = q.where(Ticket.circuit_id == item.circuit_id)
        elif item.customer_id:
            q = q.where(Ticket.customer_id == item.customer_id)
    if search:
        q = q.where(or_(model.reference.icontains(search, autoescape=True), model.title.icontains(search, autoescape=True)))
    total = session.scalar(select(func.count()).select_from(q.subquery()))
    rows = session.scalars(q.order_by(date_column.desc(), model.id.desc()).limit(limit).offset(offset))
    return {'total': total, 'items': [label(kind, row) for row in rows]}


def candidate_route(path, kind):
    @router.get(f'/api/admin-requests/{{id}}/candidates/{path}', name=f'candidates_{kind}')
    def view(id: RootId, session: DBSession, search: str | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 25, offset: Annotated[int, Query(ge=0)] = 0):
        return candidates(session, id, kind, search, limit, offset)


for path, kind in (('tickets', 'ticket'), ('internal-tickets', 'internal_ticket'), ('changes', 'change')):
    candidate_route(path, kind)


@router.post('/api/admin-requests/{id}/links', status_code=201)
def add_link(id: RootId, payload: AdminRequestLinkCreate, session: DBSession, request: Request):
    model, column, _ = KINDS[payload.kind]
    try:
        item = locked(session, id)
        if session.scalar(select(model.id).where(model.id == payload.target_id).with_for_update(read=True, of=model)) is None:
            raise HTTPException(422, 'El registro a asociar no existe')
        if session.scalar(select(AdminRequestLink.id).where(AdminRequestLink.request_id == id, getattr(AdminRequestLink, column) == payload.target_id)):
            raise HTTPException(409, 'El registro ya está asociado a la solicitud')
        session.add(AdminRequestLink(request_id=id, created_by=request.state.principal.id, **{column: payload.target_id}))
        event(session, request.state.principal, id, 'LINK', {'kind': payload.kind, 'target_id': payload.target_id})
        session.commit()
        session.refresh(item)
        return response(session, item)
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, 'El registro ya está asociado a la solicitud')
    except Exception:
        session.rollback()
        raise


@router.delete('/api/admin-requests/{id}/links/{link_id}')
def remove_link(id: RootId, link_id: RootId, session: DBSession, request: Request):
    try:
        item = locked(session, id)
        link = session.scalar(select(AdminRequestLink).where(AdminRequestLink.id == link_id, AdminRequestLink.request_id == id))
        if link is None:
            raise HTTPException(404, 'Asociación no encontrada')
        kind = next(k for k, v in KINDS.items() if getattr(link, v[1]) is not None)
        target = getattr(link, KINDS[kind][1])
        session.delete(link)
        event(session, request.state.principal, id, 'UNLINK', {'kind': kind, 'target_id': target})
        session.commit()
        session.refresh(item)
        return response(session, item)
    except Exception:
        session.rollback()
        raise
