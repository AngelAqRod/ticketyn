"""Changes analytics and exports share the operational predicate and measurements."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Annotated, Literal
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Query, Path
from sqlalchemy import select, func, case, and_, union_all, literal
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import KeepTogether, PageBreak
from ticketyn.api import change_data as data
from ticketyn.api.crud import DBSession, get_or_404
from ticketyn.api.reports import read_snapshot
from ticketyn.api.report_data import trend, granularity
from ticketyn.api.ticket_exports import stream_ticket_export, write_export_xlsx
from ticketyn.api.ticket_reports import TicketReportOptions, report_response, intervention_block, date_text
from ticketyn.api.documents import build_pdf, paragraph, section, modern_table, fonts, duration_text, TrendGraphic, BarsGraphic, analytical_block
from ticketyn.models import MaintenanceChange as Change, ChangeSupport, ChangeUpdate, ChangeType, ChangeCompletionType, Responsible, Sector, Node
from ticketyn.schemas.change import ChangeFilters
from ticketyn.schemas.report import ReportFilters

router=APIRouter(tags=['change-reports'])
HEADERS=['Correlativo','Tipo de cambio','Título','Sector / Nodo','Encargado','Personal de apoyo','Inicio propuesto','Duración planificada','Estado','Tipo de finalización','Eficiencia','Inicio tardío']
WIDTHS=[90,90,140,85,80,90,95,75,75,90,95,55]


def summary_data(session, filters):
    q=data.statement(filters).order_by(None).subquery()
    planned=func.extract('epoch',q.c.proposed_end-q.c.proposed_start)
    real=func.extract('epoch',q.c.actual_end-q.c.actual_start)
    finished=and_(q.c.status=='FINISHED',q.c.actual_start.is_not(None),q.c.actual_end.is_not(None))
    eligible=and_(finished,q.c.efficiency_eligible.is_(True),planned>0,real>=0)
    difference=planned-real
    row=session.execute(select(func.count().label('total'),
        func.count().filter(q.c.status=='FINISHED').label('finished'),
        func.count().filter(q.c.status=='SCHEDULED').label('scheduled'),
        func.count().filter(q.c.status=='EXECUTING').label('executing'),
        func.avg(real).filter(finished).label('average_seconds'),func.coalesce(func.sum(real).filter(finished),0).label('total_seconds'),
        func.count().filter(eligible).label('evaluable'),func.count().filter(and_(eligible,difference>data.DURATION_TOLERANCE_SECONDS)).label('better'),
        func.count().filter(and_(eligible,difference.between(-data.DURATION_TOLERANCE_SECONDS,data.DURATION_TOLERANCE_SECONDS))).label('on_time'),func.count().filter(and_(eligible,difference < -data.DURATION_TOLERANCE_SECONDS)).label('exceeded'),
        func.coalesce(func.sum(func.greatest(difference,0)).filter(eligible),0).label('saved_seconds'),func.coalesce(func.sum(func.greatest(-difference,0)).filter(eligible),0).label('exceeded_seconds'),
        func.coalesce(func.sum(planned).filter(eligible),0).label('planned_evaluable_seconds'),func.coalesce(func.sum(real).filter(eligible),0).label('real_evaluable_seconds'),
        func.count().filter(func.extract('epoch',q.c.actual_start-q.c.proposed_start)>data.START_TOLERANCE_SECONDS).label('late_starts')).select_from(q)).one()
    k=dict(row._mapping);k['not_evaluable']=k['total']-k['evaluable']
    k['percentages']={key:data.percentage(k[key],k['evaluable']) or 0 for key in ('better','on_time','exceeded')}
    distributions={}
    for key,field,model in [('sectors','sector_id',Sector),('nodes','node_id',Node),('completion_types','completion_type_id',ChangeCompletionType)]:
        label=func.coalesce(q.c.completion_name,model.name,'Sin tipo') if key=='completion_types' else func.coalesce(model.name,'Sin asignar')
        distributions[key]=[dict(row._mapping) for row in session.execute(select(func.coalesce(model.id,0).label('id'),label.label('label'),func.count().label('count')).select_from(q).outerjoin(model,getattr(q.c,field)==model.id).group_by(model.id,label).order_by(func.count().desc(),model.id))]
    distributions['departments']=[dict(row._mapping) for row in session.execute(select(q.c.department_id.label('id'),q.c.department_name.label('label'),func.count().label('count')).group_by(q.c.department_id,q.c.department_name).order_by(func.count().desc(),q.c.department_id))]
    distributions['change_types']=[dict(row._mapping) for row in session.execute(select(q.c.change_type_id.label('id'),func.coalesce(ChangeType.name,'Sin clasificar').label('label'),func.count().label('count')).select_from(q.outerjoin(ChangeType,q.c.change_type_id==ChangeType.id)).group_by(q.c.change_type_id,ChangeType.name).order_by(func.count().desc(),q.c.change_type_id))]
    distributions['statuses']=[{'id':i,'label':label,'count':k[key]} for i,(key,label) in enumerate([('scheduled','Agendado'),('executing','En ejecución'),('finished','Finalizado')])]
    people=union_all(select(q.c.id.label('change_id'),q.c.manager_id.label('person_id'),literal('manager').label('role')),select(q.c.id,ChangeSupport.person_id,literal('support')).join(ChangeSupport,ChangeSupport.change_id==q.c.id)).subquery()
    participants=[dict(row._mapping) for row in session.execute(select(Responsible.id,Responsible.name.label('label'),func.count().filter(people.c.role=='manager').label('manager'),func.count().filter(people.c.role=='support').label('support'),func.count(func.distinct(people.c.change_id)).label('count')).select_from(people).join(Responsible,people.c.person_id==Responsible.id).group_by(Responsible.id,Responsible.name).order_by(func.count(func.distinct(people.c.change_id)).desc(),Responsible.id))]
    period=filters
    if filters.from_at is None:
        bounds=session.execute(select(func.min(q.c.proposed_start),func.max(q.c.proposed_start))).one()
        zone=ZoneInfo(filters.timezone);start=(bounds[0] or datetime.now(timezone.utc)).astimezone(zone).replace(hour=0,minute=0,second=0,microsecond=0)
        end=(bounds[1] or start).astimezone(zone).replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1)
        period=ReportFilters.model_construct(from_at=start,to_at=end,timezone=filters.timezone,granularity='auto')
    grain=granularity(period)
    return dict(kpis=k,**distributions,participants=participants,trend=trend(session,q,period,grain,'proposed_start'),granularity=grain,generated_at=datetime.now(timezone.utc))


def filter_labels(session,filters):
    values=['Fechas por Inicio propuesto',f'Zona horaria: {filters.timezone}']
    for key in ('from_at','to_at','search','status'):
        value=getattr(filters,key)
        if value is not None:values.append(f'{key}: {value.astimezone(ZoneInfo(filters.timezone)).isoformat() if hasattr(value,"astimezone") else data.STATUS_LABELS.get(value,value)}')
    from ticketyn.models import Department, InternalTicket
    for key,model,label in [('change_type_id',ChangeType,'Tipo de cambio'),('sector_id',Sector,'Sector'),('node_id',Node,'Nodo'),('department_id',Department,'Departamento'),('manager_id',Responsible,'Encargado'),('support_id',Responsible,'Apoyo'),('involved_id',Responsible,'Involucrado'),('completion_type_id',ChangeCompletionType,'Tipo'),('internal_ticket_id',InternalTicket,'Ticket interno')]:
        if getattr(filters,key):
            item=session.get(model,getattr(filters,key));values.append(f'{label}: {getattr(item,"name",None) or getattr(item,"reference",None) or "No disponible"}')
    return values


def export_rows(session,filters):
    for item in session.scalars(data.statement(filters).execution_options(yield_per=100)):
        m=data.measurements(item)
        yield [item.reference,item.change_type.name if item.change_type else 'Sin clasificar',item.title,' / '.join([item.sector.name,*([item.node.name] if item.node else [])]),item.manager_name,', '.join(p.person_name for p in item.support),item.proposed_start.astimezone(ZoneInfo(filters.timezone)).isoformat(),duration_text(m['planned_seconds']),data.STATUS_LABELS[item.status],item.completion_name or '—',m['efficiency_label']+(f" · {abs(m['variation_percent'])}%" if m['variation_percent'] is not None else ''),'Inicio tardío' if m['late_start'] else '']


def report_sheets(summary):
    k=summary['kpis']
    labels = {'total':'Cambios registrados','finished':'Finalizados','scheduled':'Agendados','executing':'En ejecución','average_seconds':'Duración real promedio (segundos, finalizados)','total_seconds':'Duración real acumulada (segundos, finalizados)','evaluable':'Cambios evaluables','better':'Mayor eficiencia','on_time':'Tiempo cumplido','exceeded':'Tiempo excedido','not_evaluable':'No evaluables','saved_seconds':'Tiempo ahorrado (segundos)','exceeded_seconds':'Tiempo excedido (segundos)','planned_evaluable_seconds':'Duración planificada evaluable (segundos)','real_evaluable_seconds':'Duración real evaluable (segundos)','late_starts':'Cambios con Inicio tardío'}
    values = [(label,k[key]) for key,label in labels.items()]
    values.extend([('Porcentaje · '+label,k['percentages'][key]) for key,label in [('better','Mayor eficiencia'),('on_time','Tiempo cumplido'),('exceeded','Tiempo excedido')]])
    yield ('Resumen',['Indicador','Valor'],[58,32],values)
    yield ('Evolución',['Inicio del intervalo','Cambios'],[34,20],[(r['start_at'].isoformat(),r['count']) for r in summary['trend']])
    for key,title in [('change_types','Tipos de cambio'),('statuses','Estados'),('completion_types','Finalización'),('sectors','Sectores'),('nodes','Nodos'),('departments','Departamentos')]:
        yield (title,['Nombre','Cambios'],[50,20],[(r['label'],r['count']) for r in summary[key]])
    yield ('Participación',['Persona','Encargado','Apoyo','Cambios distintos'],[40,20,20,25],[(r['label'],r['manager'],r['support'],r['count']) for r in summary['participants']])


def list_xlsx(session,filters,output,statistical=False):
    write_export_xlsx(output,'Control de cambios',HEADERS,[24,30,50,32,30,45,34,24,24,32,38,20],export_rows(session,filters),metadata=filter_labels(session,filters),extra_sheets=report_sheets(summary_data(session,filters)) if statistical else ())


def list_pdf(session,filters,output,statistical=False):
    fonts();width=landscape(A4)[0]-60;title='Reportería de Control de cambios' if statistical else 'Control de cambios'
    story=[paragraph(title,size=20,bold=True),paragraph(' · '.join(filter_labels(session,filters)),size=8),paragraph(f'Generado: {datetime.now(timezone.utc).astimezone(ZoneInfo(filters.timezone)):%d/%m/%Y %H:%M:%S}',size=8)]
    if statistical:
        summary=summary_data(session,filters)
        for name,headers,widths,rows in report_sheets(summary):
            table=modern_table(headers,rows,[width/len(headers)]*len(headers))
            graphic=None
            if name=='Evolución':graphic=TrendGraphic([SimpleNamespace(**r) for r in summary['trend']],ZoneInfo(filters.timezone),width,summary['granularity'])
            else:
                key={'Tipos de cambio':'change_types','Estados':'statuses','Finalización':'completion_types','Sectores':'sectors','Nodos':'nodes','Departamentos':'departments','Participación':'participants'}.get(name)
                if key:graphic=BarsGraphic([SimpleNamespace(**r) for r in summary[key]],width)
            story.extend(analytical_block(section(name),graphic,table,width))
        efficiency=[SimpleNamespace(label=data.EFFICIENCY_LABELS[key],count=summary['kpis'][field]) for key,field in [('BETTER','better'),('ON_TIME','on_time'),('EXCEEDED','exceeded')]]
        story.extend(analytical_block(section('Eficiencia · solo evaluables'),BarsGraphic(efficiency,width),modern_table(['Clasificación','Porcentaje'],[[r.label,summary['kpis']['percentages'][field]] for r,field in zip(efficiency,['better','on_time','exceeded'])],[width*.7,width*.3]),width))
        story.extend([paragraph('Duraciones: reales de cambios finalizados. Eficiencia: solo elegibles históricos y planificación positiva. Participación no es una calificación de desempeño.',size=8),PageBreak()])
    story.extend([section('Cambios filtrados',keep=False),modern_table(HEADERS,export_rows(session,filters),[width*w/sum(WIDTHS) for w in WIDTHS],reference=True)])
    build_pdf(output,title,filters.timezone,story)


def individual_pdf(session,id,output,zone,issued):
    fonts();item=get_or_404(session,Change,id);m=data.measurements(item)
    rows=[['Tipo de cambio',item.change_type.name if item.change_type else 'Sin clasificar'],['Estado',data.STATUS_LABELS[item.status]],['Sector',item.sector.name],['Nodo',item.node.name if item.node else 'Sin asignar'],['Encargado',item.manager_name],['Departamento',item.department_name],['Personal de apoyo',', '.join(p.person_name for p in item.support) or 'Sin personal de apoyo'],['Creado',date_text(item.created_at,zone)],['Inicio propuesto',date_text(item.proposed_start,zone)],['Fin propuesto',date_text(item.proposed_end,zone)],['Duración planificada',duration_text(m['planned_seconds'])],['Inicio real',date_text(item.actual_start,zone) if item.actual_start else 'Sin registrar'],['Fin real',date_text(item.actual_end,zone) if item.actual_end else 'Sin registrar'],['Duración real',duration_text(m['actual_seconds']) if m['actual_seconds'] is not None else 'Sin registrar'],['Tipo de finalización',item.completion_name or 'Sin registrar'],['Eficiencia',m['efficiency_label']],['Tiempo ahorrado',duration_text(m['saved_seconds']) if m['saved_seconds'] is not None else 'No evaluable'],['Tiempo excedido',duration_text(m['exceeded_seconds']) if m['exceeded_seconds'] is not None else 'No evaluable'],['Variación',f"{m['variation_percent']}%" if m['variation_percent'] is not None else 'No evaluable']]
    if m['late_start']:rows.append(['Puntualidad','Inicio tardío'])
    story=[paragraph(item.reference,size=18,bold=True),paragraph(item.title,size=12),section('Información general y ejecución',keep=False),modern_table(['Dato','Valor'],rows,[230,550],compact=True),section('Descripción'),paragraph(item.description,size=10),section('Notas finales'),paragraph(item.final_notes or 'Sin notas finales.',size=10),section('Seguimiento',keep=False)]
    updates=list(session.scalars(select(ChangeUpdate).where(ChangeUpdate.change_id==id).order_by(ChangeUpdate.occurred_at,ChangeUpdate.id)))
    if not updates:story.append(paragraph('Sin intervenciones registradas.',size=10))
    for update in updates:story.extend(intervention_block(paragraph(f'{date_text(update.occurred_at,zone)} · {update.responsible_name}',size=9,bold=True),paragraph(update.content,size=10)))
    if item.tickets:story.extend([section('Tickets internos relacionados'),modern_table(['Correlativo','Incidencia'],[[link.ticket.reference,link.ticket.title] for link in item.tickets],[170,610])])
    build_pdf(output,'Control de cambios · Reporte interno',str(zone),story,issued_at=date_text(issued,zone))

@router.get('/api/change-reports/summary')
def summary(session:DBSession,filters:Annotated[ChangeFilters,Query()]):
    read_snapshot(session);return summary_data(session,filters)

@router.get('/api/change-reports/export/{format}')
def report_export(session:DBSession,format:Literal['pdf','xlsx'],filters:Annotated[ChangeFilters,Query()]):
    renderer=list_pdf if format=='pdf' else list_xlsx
    return stream_ticket_export(session,format,filters,'ticketyn-reporte-cambios',lambda s,f,o:renderer(s,f,o,True))

@router.get('/api/changes/export/{format}')
def list_export(session:DBSession,format:Literal['pdf','xlsx'],filters:Annotated[ChangeFilters,Query()]):
    return stream_ticket_export(session,format,filters,'ticketyn-cambios',list_pdf if format=='pdf' else list_xlsx)

@router.get('/api/changes/{id}/reports/pdf')
def individual(id:Annotated[int, Path(gt=0)],session:DBSession,options:Annotated[TicketReportOptions,Query()]):
    return report_response(session,id,options,'internal',renderer=individual_pdf,filename=f'ticketyn-cambio-{id}.pdf')
