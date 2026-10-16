"""Transactional changes and shared, duration-based measurements."""
from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException
from sqlalchemy import select, or_, exists, delete
from sqlalchemy.orm import selectinload
from ticketyn.models import MaintenanceChange as Change, ChangeSupport, ChangeTicket, ChangeAudit, ChangeType, ChangeCompletionType, ChangeNumberConfig, Responsible, Sector, Node, InternalTicket
from ticketyn.api.ticket_numbers import locked_number_config, format_reference
from ticketyn.api.crud import get_or_404

DURATION_TOLERANCE_SECONDS = 15 * 60
START_TOLERANCE_SECONDS = 60 * 60


def percentage(value, total):
    return float((Decimal(str(value))/Decimal(str(total))*100).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)) if total else None


FIELDS = ('change_type_id','title','description','sector_id','node_id','manager_id','status','proposed_start','proposed_end','actual_start','actual_end','completion_type_id','final_notes')
STATUS_LABELS = {'SCHEDULED':'Agendado','EXECUTING':'En ejecución','FINISHED':'Finalizado'}
EFFICIENCY_LABELS = {'BETTER':'Mayor eficiencia','ON_TIME':'Tiempo cumplido','EXCEEDED':'Tiempo excedido','NOT_EVALUABLE':'No evaluable'}


def measurements(item):
    planned = (item.proposed_end-item.proposed_start).total_seconds()
    actual = (item.actual_end-item.actual_start).total_seconds() if item.actual_start is not None and item.actual_end is not None else None
    late = item.actual_start is not None and (item.actual_start-item.proposed_start).total_seconds() > START_TOLERANCE_SECONDS
    eligible = item.status == 'FINISHED' and item.efficiency_eligible is True and planned > 0 and actual is not None and actual >= 0
    difference = planned-actual if eligible else None
    classification = ('BETTER' if difference > DURATION_TOLERANCE_SECONDS else 'EXCEEDED' if difference < -DURATION_TOLERANCE_SECONDS else 'ON_TIME') if eligible else 'NOT_EVALUABLE'
    percent = percentage(difference,planned) if eligible else None
    return dict(planned_seconds=planned, actual_seconds=actual, efficiency=classification, efficiency_label=EFFICIENCY_LABELS[classification], saved_seconds=max(difference,0) if eligible else None, exceeded_seconds=max(-difference,0) if eligible else None, variation_percent=percent, late_start=late)


def statement(filters):
    q=select(Change)
    for field in ('status','sector_id','node_id','department_id','manager_id','completion_type_id','change_type_id'):
        value=getattr(filters,field)
        if value is not None:q=q.where(getattr(Change,field)==value)
    if filters.search:q=q.where(or_(Change.reference.icontains(filters.search,autoescape=True),Change.title.icontains(filters.search,autoescape=True)))
    if filters.from_at:q=q.where(Change.proposed_start>=filters.from_at)
    if filters.to_at:q=q.where(Change.proposed_start<filters.to_at)
    if filters.support_id:q=q.where(exists().where(ChangeSupport.change_id==Change.id,ChangeSupport.person_id==filters.support_id))
    if filters.involved_id:q=q.where(or_(Change.manager_id==filters.involved_id,exists().where(ChangeSupport.change_id==Change.id,ChangeSupport.person_id==filters.involved_id)))
    if filters.internal_ticket_id:q=q.where(exists().where(ChangeTicket.change_id==Change.id,ChangeTicket.internal_ticket_id==filters.internal_ticket_id))
    order=getattr(Change,filters.sort)
    return q.order_by(order.asc() if filters.direction=='asc' else order.desc(),Change.id.asc() if filters.direction=='asc' else Change.id.desc())


def response(item):
    values={field:getattr(item,field) for field in (*FIELDS,'id','reference','ticket_number','manager_name','department_id','department_name','completion_name','efficiency_eligible','created_at','updated_at')}
    values.update(change_type={'id':item.change_type.id,'name':item.change_type.name,'active':item.change_type.active} if item.change_type else None,sector={'id':item.sector.id,'name':item.sector.name},node={'id':item.node.id,'name':item.node.name} if item.node else None,
                  support=[{'id':p.person_id,'name':p.person_name} for p in item.support],
                  internal_tickets=[{'id':link.ticket.id,'reference':link.ticket.reference,'title':link.ticket.title} for link in item.tickets],**measurements(item))
    return values


def audit_values(item):
    values={key:getattr(item,key) for key in (*FIELDS,'manager_name','department_id','department_name','completion_name','efficiency_eligible')}
    values.update(support=[{'id':p.person_id,'name':p.person_name} for p in item.support],internal_ticket_ids=[p.internal_ticket_id for p in item.tickets])
    return {key:value.isoformat() if hasattr(value,'isoformat') else value for key,value in values.items()}


def active_relation(session, model, id):
    row=session.scalar(select(model).where(model.id==id).with_for_update(read=True,of=model))
    if row is None:raise HTTPException(422,f'{model.__name__} no existe')
    if not row.active:raise HTTPException(422,f'{model.__name__} está inactivo')
    return row


def persist(session, supplied, id=None):
    try:
        item=session.scalar(select(Change).where(Change.id==id).with_for_update(of=Change)) if id else None
        if id and item is None:raise HTTPException(404,'Cambio no encontrado')
        before=audit_values(item) if item else {}
        values={**({field:getattr(item,field) for field in FIELDS} if item else {}),**{key:value for key,value in supplied.items() if key in FIELDS}}
        if not values.get('change_type_id') and (not item or any(key in supplied for key in FIELDS)):
            raise HTTPException(422,'Selecciona un tipo de cambio')
        if values.get('change_type_id') and (not item or values['change_type_id']!=item.change_type_id):
            active_relation(session,ChangeType,values['change_type_id'])
        supports=supplied.get('support_ids',[p.person_id for p in item.support] if item else [])
        links=supplied.get('internal_ticket_ids',[p.internal_ticket_id for p in item.tickets] if item else [])
        if len(set(supports))!=len(supports) or values['manager_id'] in supports:raise HTTPException(422,'El personal de apoyo no puede duplicarse ni incluir al encargado')
        if len(set(links))!=len(links):raise HTTPException(422,'Tickets internos duplicados')
        if values['proposed_end']<values['proposed_start']:raise HTTPException(422,'Fin propuesto anterior al inicio')
        if values.get('actual_end') is not None and (values.get('actual_start') is None or values['actual_end']<values['actual_start']):raise HTTPException(422,'Fechas reales inválidas')
        if values['status']!='SCHEDULED' and values.get('actual_start') is None:raise HTTPException(422,'El estado requiere inicio real')
        if values['status']=='FINISHED' and (values.get('actual_end') is None or values.get('completion_type_id') is None or not (values.get('final_notes') or '').strip()):raise HTTPException(422,'Finalizar requiere fechas reales, tipo y notas finales')
        for field,model in [('sector_id',Sector),('node_id',Node)]:
            if values.get(field) and (not item or values[field]!=getattr(item,field)):active_relation(session,model,values[field])
        manager=None
        if not item or values['manager_id']!=item.manager_id:
            manager=active_relation(session,Responsible,values['manager_id'])
            if manager.department_id is None:raise HTTPException(422,'El encargado debe tener departamento en su catálogo')
        old_support={p.person_id:p.person_name for p in item.support} if item else {}
        support_names={pid:old_support[pid] if pid in old_support else active_relation(session,Responsible,pid).name for pid in supports}
        for tid in links:
            if not item or tid not in [p.internal_ticket_id for p in item.tickets]:
                if session.scalar(select(InternalTicket.id).where(InternalTicket.id==tid).with_for_update(read=True,of=InternalTicket)) is None:raise HTTPException(422,'Ticket interno no encontrado')
        snapshot = values['status']=='FINISHED' and (not item or item.status!='FINISHED' or item.completion_type_id!=values['completion_type_id'])
        completion = None
        if values.get('completion_type_id') and (snapshot or not item or item.completion_type_id!=values['completion_type_id']):completion=active_relation(session,ChangeCompletionType,values['completion_type_id'])
        if item is None:
            config=locked_number_config(session,ChangeNumberConfig)
            if config.next_number>=2147483647:raise HTTPException(409,'Numeración agotada')
            item=Change(**values,ticket_number=config.next_number,reference=format_reference(config.prefix,config.separator,config.next_number,config.padding),manager_name=manager.name,department_id=manager.department_id,department_name=manager.department.name)
            config.next_number+=1
            session.add(item)
        else:
            for key,value in values.items():setattr(item,key,value)
        if manager:
            item.manager_name=manager.name;item.department_id=manager.department_id;item.department_name=manager.department.name
        if completion:
            item.completion_name=completion.name
            if snapshot:item.efficiency_eligible=completion.applies_efficiency
        if not values.get('completion_type_id'):
            item.completion_name=None;item.efficiency_eligible=None
        session.flush()
        old_s={p.person_id:p for p in item.support}
        old_t={p.internal_ticket_id:p for p in item.tickets}
        for pid,row in old_s.items():
            if pid not in supports:session.delete(row)
        for pid in supports:
            if pid not in old_s:session.add(ChangeSupport(change_id=item.id,person_id=pid,person_name=support_names[pid]))
        for tid,row in old_t.items():
            if tid not in links:session.delete(row)
        for tid in links:
            if tid not in old_t:session.add(ChangeTicket(change_id=item.id,internal_ticket_id=tid))
        session.flush();session.expire(item,['support','tickets'])
        after=audit_values(item)
        changes={key:{'before':before.get(key),'after':value} for key,value in after.items() if before.get(key)!=value}
        if changes:session.add(ChangeAudit(change_id=item.id,changes=changes))
        session.commit();session.refresh(item)
        return item
    except Exception:
        session.rollback();raise
