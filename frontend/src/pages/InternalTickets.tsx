import { RelatedChanges } from '../components/RelatedChanges'
import { InternalTicketReportDownload } from '../components/InternalTicketReportDownload'
import { downloadInternalTickets } from '../api/ticketExports'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { Plus, RefreshCw, FileText, FileSpreadsheet } from 'lucide-react'
import { getJson, patchJson, postJson } from '../api/client'
import { listSectors, listNodes, listDepartments, listResponsibles, listInternalIncidentTypes, listProviders } from '../api'
import type { NamedCatalog } from '../types/catalog'
import type { InternalTicket } from '../types/internalTicket'
import type { Ticket } from '../types/ticket'
import { PageHeading } from '../components/PageHeading'
import { PaginationBar } from '../components/PaginationBar'
import { FilterHeading } from '../components/FilterHeading'
import { FormField } from '../components/FormField'
import { SearchableSelect } from '../components/SearchableSelect'
import { PeriodShortcuts } from '../components/PeriodShortcuts'
import { RequestState } from '../components/RequestState'
import { FeedbackMessage } from '../components/FeedbackMessage'
import { StatusBadge } from '../components/StatusBadge'
import { TicketFollowUp } from '../components/TicketFollowUp'
import { TicketEscalations } from '../components/TicketEscalations'
import { useUrlFilters } from '../hooks/useUrlFilters'
import { reportPeriod } from '../lib/reportPeriod'
import { localDateTimeValue, localDateTimeToIso } from '../lib/datetime'
import { formatDate, formatDuration } from '../lib/format'

const root = '/api/internal-tickets'
const relationFields = [
  ['sector_id','Sector',true], ['node_id','Nodo',false], ['department_id','Departamento',true],
  ['responsible_id','Responsable',false], ['incident_type_id','Tipo de incidencia interna',true], ['provider_id','Atribuible a proveedor',false],
] as const
type Catalogs = Record<typeof relationFields[number][0], NamedCatalog[]>
function useCatalogs() {
  const [data,setData] = useState<Catalogs | null>(null), [error,setError] = useState<string | null>(null), [retry,setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController(); setError(null)
    Promise.all([listSectors(controller.signal,true),listNodes(controller.signal,true),listDepartments(controller.signal,true),listResponsibles(controller.signal,true),listInternalIncidentTypes(controller.signal,true),listProviders(controller.signal,true)]).then(rows => {
      if (!controller.signal.aborted) setData(Object.fromEntries(relationFields.map(([key],i)=>[key,rows[i]])) as Catalogs)
    }).catch(f => { if (!controller.signal.aborted) setError(f instanceof Error ? f.message : 'No se pudieron cargar los catálogos.') })
    return ()=>controller.abort()
  },[retry])
  return { data,error,retry:()=>setRetry(retry+1) }
}
function useInternal(id: string | undefined) {
  const [item,setItem]=useState<InternalTicket | null>(null),[error,setError]=useState<string | null>(null),[retry,setRetry]=useState(0)
  useEffect(()=>{const c=new AbortController();setItem(null);setError(null);getJson<InternalTicket>(`${root}/${id}`,c.signal).then(x=>{if(!c.signal.aborted)setItem(x)}).catch(f=>{if(!c.signal.aborted)setError(f instanceof Error?f.message:'No se pudo cargar.')});return()=>c.abort()},[id,retry])
  return { item,error,retry:()=>setRetry(retry+1) }
}
export function InternalTickets() {
  const keys=['search','status','sector_id','node_id','department_id','responsible_id','incident_type_id','provider_id','period','from','to']
  const {params,change,clear}=useUrlFilters(keys), catalogs=useCatalogs()
  const [rows,setRows]=useState<InternalTicket[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState<string | null>(null),[refresh,setRefresh]=useState(0)
  const [search,setSearch]=useState(params.get('search')??'')
  useEffect(()=>setSearch(params.get('search')??''),[params])
  const offset=Math.max(0,Number(params.get('offset'))||0)
  let query=new URLSearchParams({limit:'50',offset:String(offset)}),filterError:string|null=null
  try {
    const period=reportPeriod(new URLSearchParams({period:params.get('period')??'all',from:params.get('from')??'',to:params.get('to')??''})).query
    if(period.from)query.set('from',period.from);if(period.to)query.set('to',period.to)
    for(const key of keys.slice(0,8))if(params.get(key))query.set(key,params.get(key)!)
    if(params.get('provider_id')==='none'){query.delete('provider_id');query.set('without_provider','true')}
  }catch(f){filterError=f instanceof Error?f.message:'Rango inválido'}
  const queryKey=query.toString()
  const exportingRef=useRef(false)
  const [exporting,setExporting]=useState(false),[exportError,setExportError]=useState<string|null>(null)
  async function exportTickets(format:'pdf'|'xlsx') {
    if(exportingRef.current||filterError)return
    exportingRef.current=true;setExporting(true);setExportError(null)
    try {await downloadInternalTickets(format,new URLSearchParams(queryKey))}
    catch(f){setExportError(f instanceof Error?f.message:'No se pudo exportar el listado.')}
    finally{exportingRef.current=false;setExporting(false)}
  }

  useEffect(()=>{const c=new AbortController();setLoading(true);setError(null);if(filterError){setLoading(false);setError(filterError);return}
    getJson<InternalTicket[]>(`${root}?${queryKey}`,c.signal).then(x=>{if(!c.signal.aborted){setRows(x);setLoading(false)}}).catch(f=>{if(!c.signal.aborted){setError(f instanceof Error?f.message:'No se pudo cargar.');setLoading(false)}});return()=>c.abort()
  },[queryKey,refresh,filterError])
  return <><PageHeading title="Tickets internos" description="Incidencias de infraestructura y operación del NOC." action={<><button className="button-secondary" onClick={()=>setRefresh(refresh+1)} disabled={loading}><RefreshCw size={15}/>Actualizar</button><button type="button" className="button-secondary" disabled={exporting||Boolean(filterError)} onClick={()=>void exportTickets('pdf')}><FileText size={15}/>Exportar PDF</button><button type="button" className="button-secondary" disabled={exporting||Boolean(filterError)} onClick={()=>void exportTickets('xlsx')}><FileSpreadsheet size={15}/>Exportar Excel</button><Link className="button-primary" to="/internal-tickets/new"><Plus size={15}/>Nuevo ticket interno</Link></>}/>
    {exporting&&<RequestState loading compact loadingText="Generando archivo..." className="mb-3 workspace-caption"/>}
    {exportError&&<FeedbackMessage variant="error" className="mb-3">{exportError}</FeedbackMessage>}
    <section className="filter-toolbar space-y-3" aria-label="Filtros de tickets internos"><FilterHeading title="Filtros de tickets internos"/>
      <form className="flex gap-2" onSubmit={e=>{e.preventDefault();change({search})}}><FormField id="internal-search" label="Buscar"><input id="internal-search" className="form-input" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Correlativo, título o descripción"/></FormField><button className="button-secondary self-end">Buscar</button></form>
      <PeriodShortcuts includeAll label="Período" value={params.get('period')??'all'} onChange={period=>change({period,from:'',to:''})}/>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><FormField id="internal-status" label="Estado"><select id="internal-status" className="form-input" value={params.get('status')??''} onChange={e=>change({status:e.target.value})}><option value="">Todos</option><option value="OPEN">Abierto</option><option value="CLOSED">Cerrado</option></select></FormField>
      {relationFields.map(([key,label])=><FormField key={key} id={`filter-${key}`} label={label}><select id={`filter-${key}`} className="form-input" value={params.get(key)??''} onChange={e=>change({[key]:e.target.value})}><option value="">Todos</option>{key==='provider_id'&&<option value="none">Ninguno</option>}{catalogs.data?.[key].map(row=><option key={row.id} value={row.id}>{row.name}{row.active?'':' (Inactivo)'}</option>)}</select></FormField>)}
      {params.get('period')==='custom'&&(['from','to'] as const).map(key=><FormField key={key} id={`internal-${key}`} label={key==='from'?'Desde':'Hasta'}><input id={`internal-${key}`} type="date" className="form-input" value={params.get(key)??''} onChange={e=>change({[key]:e.target.value})}/></FormField>)}</div><RequestState compact error={catalogs.error} onRetry={catalogs.retry}/><button className="button-secondary" onClick={clear}>Limpiar filtros</button>
    </section>
    {loading||error||!rows.length?<RequestState loading={loading} error={error} empty={!rows.length} emptyTitle="Sin tickets internos" onRetry={()=>setRefresh(refresh+1)}/>:<InternalTable rows={rows}/>}
    <PaginationBar page={Math.floor(offset/50)+1} info={<span className="text-xs">Página {Math.floor(offset/50)+1}</span>} previousDisabled={loading||!offset} nextDisabled={loading||Boolean(error)||rows.length<50} onPrevious={()=>change({offset:String(Math.max(0,offset-50))},false)} onNext={()=>change({offset:String(offset+50)},false)}/>
  </>
}
function InternalTable({rows}:{rows:InternalTicket[]}) { return <div className="table-surface overflow-x-auto"><table className="operation-table"><caption className="table-title">Tickets internos</caption><thead><tr>{['Correlativo','Incidencia','Estado','Sector','Nodo','Departamento','Responsable','Tipo de incidencia interna','Atribuible a proveedor','Inicio','Duración','Tickets relacionados','Acciones'].map(x=><th key={x}>{x}</th>)}</tr></thead><tbody>{rows.map(t=><tr key={t.id}><th scope="row"><Link to={`/internal-tickets/${t.id}`}>{t.reference}</Link></th><td>{t.title}</td><td><StatusBadge status={t.status}/></td><td>{t.sector.name}</td><td>{t.node?.name??'Sin asignar'}</td><td>{t.department.name}</td><td>{t.responsible?.name??'Sin asignar'}</td><td>{t.incident_type.name}</td><td>{t.provider?.name??'Ninguno'}</td><td>{formatDate(t.start_at)}</td><td>{formatDuration(t.duration_seconds)}</td><td>{t.related_count}</td><td><Link className="button-secondary table-action" to={`/internal-tickets/${t.id}/edit`}>Editar</Link></td></tr>)}</tbody></table></div> }

export function InternalTicketEditor({edit=false}:{edit?:boolean}) {
  const {id}=useParams()
  return edit?<ExistingEditor key={id} id={id}/>:<InternalForm/>
}
function ExistingEditor({id}:{id:string|undefined}){const result=useInternal(id);return result.item?<InternalForm key={result.item.id} ticket={result.item}/>:<RequestState loading={!result.error} error={result.error} onRetry={result.retry}/>}
function InternalForm({ticket}:{ticket?:InternalTicket}) {
  const navigate=useNavigate(),catalogs=useCatalogs(),sending=useRef(false)
  const [values,setValues]=useState(()=>({title:ticket?.title??'',description:ticket?.description??'',resolution:ticket?.resolution??'',sector_id:ticket?String(ticket.sector_id):'',node_id:ticket?.node_id?String(ticket.node_id):'',department_id:ticket?String(ticket.department_id):'',responsible_id:ticket?.responsible_id?String(ticket.responsible_id):'',incident_type_id:ticket?String(ticket.incident_type_id):'',provider_id:ticket?.provider_id?String(ticket.provider_id):'',status:ticket?.status??'OPEN',start_at:localDateTimeValue(ticket?new Date(ticket.start_at):undefined),end_at:ticket?.end_at?localDateTimeValue(new Date(ticket.end_at)):''}))
  const [saving,setSaving]=useState(false),[error,setError]=useState<string|null>(null)
  function change(key:keyof typeof values,value:string){setValues(v=>({...v,[key]:value}))}
  async function submit(e:FormEvent){e.preventDefault();if(sending.current)return;setError(null)
    try{
      if(!values.title.trim()||!values.description.trim()||!values.sector_id||!values.department_id||!values.incident_type_id||!values.start_at)throw Error('Completa los campos obligatorios antes de guardar.')
      const start=values.start_at===(ticket&&localDateTimeValue(new Date(ticket.start_at)))?ticket!.start_at:localDateTimeToIso(values.start_at)
      const end=values.end_at?(values.end_at===(ticket?.end_at&&localDateTimeValue(new Date(ticket.end_at)))?ticket!.end_at:localDateTimeToIso(values.end_at)):null
      if(end&&new Date(end)<new Date(start))throw Error('Fin debe ser igual o posterior a Inicio.')
      const payload={...values,title:values.title.trim(),description:values.description.trim(),resolution:values.resolution.trim()?values.resolution:null,start_at:start,end_at:end,...Object.fromEntries(relationFields.map(([key])=>[key,values[key]?Number(values[key]):null]))}
      sending.current=true;setSaving(true)
      const saved=ticket?await patchJson<InternalTicket>(`${root}/${ticket.id}`,payload):await postJson<InternalTicket>(root,payload)
      navigate(`/internal-tickets/${saved.id}`)
    }catch(f){setError(f instanceof Error?f.message:'No se pudo guardar.')}finally{sending.current=false;setSaving(false)}
  }
  return <><PageHeading title={ticket?`Editar ${ticket.reference}`:'Nuevo ticket interno'} description="Gestión operativa de infraestructura, sin cliente ni circuito."/>
    <RequestState compact loading={!catalogs.data&&!catalogs.error} error={catalogs.error} onRetry={catalogs.retry}/>
    <form className="ticket-noc-form" aria-label={ticket?'Editar ticket interno':'Crear ticket interno'} onSubmit={submit} noValidate><fieldset className="space-y-5 min-w-0" disabled={saving||!catalogs.data||Boolean(catalogs.error)}><legend className="sr-only">Datos del ticket interno</legend>
      <section><h2 className="mb-3 font-semibold">Incidencia</h2>{(['title','description'] as const).map(key=><FormField key={key} id={`internal-${key}`} label={key==='title'?'Título':'Descripción'} required>{key==='title'?<input id={`internal-${key}`} className="form-input" value={values[key]} onChange={e=>change(key,e.target.value)}/>:<textarea id={`internal-${key}`} rows={3} className="form-input" value={values[key]} onChange={e=>change(key,e.target.value)}/>}</FormField>)}</section>
      <section><h2 className="mb-3 text-sm font-semibold">Clasificación</h2><div className="grid gap-3 sm:grid-cols-2">{relationFields.map(([key,label,required])=><FormField key={key} id={`internal-${key}`} label={label} required={required}><SearchableSelect id={`internal-${key}`} label={label} required={required} value={values[key]} onChange={v=>change(key,v)} options={(catalogs.data?.[key]??[]).filter(x=>x.active||String(x.id)===values[key]).map(x=>({value:String(x.id),label:x.name,disabled:!x.active}))} placeholder={key==='provider_id'?'Ninguno':required?'Selecciona una opción':'Sin asignar'} emptyMessage="No hay registros activos." noMatchMessage="Sin coincidencias."/></FormField>)}<FormField id="internal-state" label="Estado" required><select id="internal-state" className="form-input" value={values.status} onChange={e=>change('status',e.target.value)}><option value="OPEN">Abierto</option><option value="CLOSED">Cerrado</option></select></FormField></div></section>
      <section><h2 className="mb-3 text-sm font-semibold">Tiempos operativos</h2>{ticket&&<button type="button" className="button-secondary mb-3" onClick={()=>setValues(v=>({...v,status:'CLOSED',end_at:localDateTimeValue()}))}>Finalizar ahora</button>}<div className="grid gap-3 sm:grid-cols-2">{(['start_at','end_at'] as const).map(key=><FormField key={key} id={`internal-${key}`} label={key==='start_at'?'Inicio':'Fin'} required={key==='start_at'}><div className="flex gap-2"><input id={`internal-${key}`} type="datetime-local" step="60" className="form-input min-w-0" value={values[key]} onChange={e=>change(key,e.target.value)}/><button type="button" className="button-secondary" onClick={()=>change(key,localDateTimeValue())}>Ahora</button></div></FormField>)}</div></section>
      <section><h2 className="mb-3 text-sm font-semibold">Resolución documentada</h2><FormField id="internal-resolution" label="Resolución interna"><textarea id="internal-resolution" className="form-input" rows={3} maxLength={10000} value={values.resolution} onChange={e=>change('resolution',e.target.value)}/></FormField></section>
    </fieldset>{error&&<FeedbackMessage variant="error" className="mt-3">{error}</FeedbackMessage>}<div className="mt-5 flex justify-end gap-3"><button type="button" className="button-secondary" disabled={saving} onClick={()=>navigate(ticket?`/internal-tickets/${ticket.id}`:'/internal-tickets')}>Cancelar</button><button className="button-primary" disabled={saving||!catalogs.data||Boolean(catalogs.error)}>{saving?'Guardando...':ticket?'Guardar cambios':'Guardar'}</button></div></form></>
}
export function InternalTicketDetail(){const{id}=useParams(),result=useInternal(id);if(!result.item)return <RequestState loading={!result.error} error={result.error} onRetry={result.retry}/>;return <InternalDetail key={result.item.id} ticket={result.item}/>}
function InternalDetail({ticket:t}:{ticket:InternalTicket}){
  const [related,setRelated]=useState<{total:number;items:Ticket[]}|null>(null),[offset,setOffset]=useState(0),[error,setError]=useState<string|null>(null),[retry,setRetry]=useState(0)
  useEffect(()=>{const c=new AbortController();setRelated(null);setError(null);getJson<{total:number;items:Ticket[]}>(`${root}/${t.id}/related?limit=50&offset=${offset}`,c.signal).then(x=>{if(!c.signal.aborted)setRelated(x)}).catch(f=>{if(!c.signal.aborted)setError(f instanceof Error?f.message:'No se pudieron cargar las relaciones.')});return()=>c.abort()},[t.id,offset,retry])
  return <><PageHeading title={t.reference} description={t.title} action={<><StatusBadge status={t.status}/><InternalTicketReportDownload id={t.id} reference={t.reference}/><Link className="button-secondary" to="/internal-tickets">Volver a tickets internos</Link><Link className="button-primary" to={`/internal-tickets/${t.id}/edit`}>Editar ticket interno</Link></>}/>
    <div className="space-y-4">{[['Descripción',t.description],['Resolución documentada',t.resolution??'Sin resolución documentada.']].map(([label,value])=><section key={label} className="noc-panel p-4"><h2 className="noc-section-title mb-3 text-sm font-semibold">{label}</h2><p className="whitespace-pre-wrap [overflow-wrap:anywhere] text-sm">{value}</p></section>)}
    <section className="noc-panel p-4"><h2 className="noc-section-title mb-3 text-sm font-semibold">Clasificación y tiempos operativos</h2><dl className="grid gap-3 sm:grid-cols-2">{[...relationFields.map(([key,label])=>[label,t[key.replace('_id','') as 'sector'|'node'|'department'|'responsible'|'incident_type'|'provider']?.name??(key==='provider_id'?'Ninguno':'Sin asignar')]),['Inicio',formatDate(t.start_at)],['Fin',formatDate(t.end_at)],['Duración',formatDuration(t.duration_seconds)],['Fecha de creación',formatDate(t.created_at)],['Última actualización',formatDate(t.updated_at)]].map(([label,value])=><div key={label}><dt className="text-xs text-muted">{label}</dt><dd className="text-sm">{value}</dd></div>)}</dl></section></div>
    <RelatedChanges internalTicketId={t.id}/><TicketEscalations ticketId={t.id} internal/><TicketFollowUp ticketId={t.id} internal/>
    <section className="noc-panel mt-5 p-4"><h2 className="noc-section-title mb-3 text-sm font-semibold">Tickets de clientes relacionados{related?` (${related.total})`:''}</h2><RequestState compact loading={!related&&!error} error={error} empty={related?.items.length===0} emptyTitle="Sin tickets relacionados" onRetry={()=>setRetry(retry+1)}/>{related&&related.items.length>0&&<div className="table-surface overflow-x-auto"><table className="operation-table"><thead><tr>{['Correlativo','Cliente','Incidencia','Estado'].map(x=><th key={x}>{x}</th>)}</tr></thead><tbody>{related.items.map(row=><tr key={row.id}><td><Link to={`/tickets/${row.id}`}>{row.reference}</Link></td><td>{row.customer?.customer_code} — {row.customer?.name}</td><td>{row.title}</td><td><StatusBadge status={row.status}/></td></tr>)}</tbody></table></div>}<PaginationBar page={Math.floor(offset/50)+1} info={<span className="text-xs">Página {Math.floor(offset/50)+1}</span>} previousDisabled={!related||offset===0} nextDisabled={!related||offset+50>=related.total} onPrevious={()=>setOffset(Math.max(0,offset-50))} onNext={()=>setOffset(offset+50)}/></section>
  </>
}
