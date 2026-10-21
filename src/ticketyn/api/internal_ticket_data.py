from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select, func, or_, String, cast
from ticketyn.api.crud import save_item
from ticketyn.api.ticket_numbers import locked_number_config, format_reference
from ticketyn.models import InternalTicket, InternalTicketNumberConfig, InternalTicketUpdate, InternalIncidentType, Provider, Sector, Node, Department, Responsible, Ticket
from ticketyn.schemas.internal_ticket import InternalTicketResponse

RELATIONS = {'sector_id': Sector, 'node_id': Node, 'department_id': Department, 'incident_type_id': InternalIncidentType, 'provider_id': Provider, 'responsible_id': Responsible}

def response(session, item, related_count=None):
    data = {key: getattr(item, key) for key in InternalTicketResponse.model_fields if key not in {'sector','node','department','incident_type','provider','responsible','related_count'}}
    for key, model in RELATIONS.items():
        data[key.removesuffix('_id')] = getattr(item, key.removesuffix('_id'))
    data['related_count'] = related_count if related_count is not None else session.scalar(select(func.count(Ticket.id)).where(Ticket.internal_ticket_id == item.id))
    return InternalTicketResponse.model_validate(data)

def evidence(session, ticket, field, old, new):
    session.add(InternalTicketUpdate(ticket_id=ticket.id, content=f'Cambio de {field}.\nAnterior: {old if old is not None else "Sin registrar"}\nNuevo: {new if new is not None else "Sin registrar"}', visibility='INTERNAL', occurred_at=datetime.now(timezone.utc)))

def persist(session, values, id=None):
    try:
        if id is not None:
            ticket = session.scalar(select(InternalTicket).where(InternalTicket.id == id).with_for_update(of=InternalTicket))
            if ticket is None: raise HTTPException(404, 'Ticket interno no encontrado')
            current = {key: getattr(ticket, key) for key in ('title','description','resolution','start_at','end_at','status',*RELATIONS)}
        else:
            ticket = None
            current = {}
        merged = {**current, **values}
        if merged.get('end_at') is not None and merged['end_at'] < merged['start_at']:
            raise HTTPException(422, 'end_at debe ser igual o posterior a start_at')
        for field, model in RELATIONS.items():
            if field not in values or (ticket and values[field] == current[field]) or values[field] is None: continue
            related = session.scalar(select(model).where(model.id == values[field]).with_for_update(read=True, of=model))
            if related is None: raise HTTPException(404, f'{model.__name__} no encontrado')
            if model is Responsible:
                from ticketyn.api.responsible_selection import selectable
                selectable(related)
            if not related.active: raise HTTPException(422, f'{model.__name__} está inactivo')
        if ticket is None:
            config = locked_number_config(session, InternalTicketNumberConfig)
            if config.next_number >= 2147483647: raise HTTPException(409, 'Se agotó el rango de numeración')
            ticket = InternalTicket(**values, ticket_number=config.next_number, reference=format_reference(config.prefix, config.separator, config.next_number, config.padding))
            config.next_number += 1
            session.add(ticket); session.flush()
            if ticket.resolution: evidence(session, ticket, 'resolución documentada', None, ticket.resolution)
        else:
            for field, value in values.items():
                if field in ('provider_id','resolution') and value != getattr(ticket, field):
                    # No authenticated actor exists; preserve evidence without inventing identity.
                    old = getattr(ticket, field)
                    if field == 'provider_id':
                        old = session.get(Provider, old).name if old else None
                        new = session.get(Provider, value).name if value else None
                    else: new = value
                    evidence(session, ticket, 'proveedor atribuible' if field == 'provider_id' else 'resolución documentada', old, new)
                setattr(ticket, field, value)
        return save_item(session, ticket)
    except Exception:
        session.rollback(); raise

def statement(filters, *, time_field="start_at"):
    query = select(InternalTicket)
    for field in ('status', *RELATIONS):
        if filters.get(field) is not None: query = query.where(getattr(InternalTicket, field) == filters[field])
    if filters.get('without_provider'): query = query.where(InternalTicket.provider_id.is_(None))
    if filters.get('search'):
        query = query.where(or_(*(getattr(InternalTicket, key).icontains(filters['search'], autoescape=True) for key in ('reference','title','description')), cast(InternalTicket.ticket_number, String).icontains(filters['search'], autoescape=True)))
    if filters.get('from_at'): query = query.where(getattr(InternalTicket, time_field) >= filters['from_at'])
    if filters.get('to_at'): query = query.where(getattr(InternalTicket, time_field) < filters['to_at'])
    if filters.get('from_at') and filters.get('to_at') and filters['to_at'] <= filters['from_at']: raise HTTPException(422, 'to debe ser posterior a from')
    return query.order_by(InternalTicket.created_at.desc(), InternalTicket.id.desc())
