import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { listSectors,listNodes,listResponsibles,listDepartments,listChangeTypes,listChangeCompletionTypes } from '../api'
import { getJson } from '../api/client'
import { FormField } from './FormField'
import { FilterHeading } from './FilterHeading'
import { RequestState } from './RequestState'
import { InternalTicketSelect } from './InternalTicketSelect'
import type { Change, ChangeCatalogs } from '../types/change'
import { formatDate,formatDuration } from '../lib/format'
import { ticketynDateTimeToIso } from '../lib/datetime'

export const changeStatuses={SCHEDULED:'Agendado',EXECUTING:'En ejecución',FINISHED:'Finalizado'}
export const changeFilterKeys=['search','status','from','to','manager_id','support_id','involved_id','department_id','sector_id','node_id','completion_type_id','change_type_id','sort','direction']
export function changeQuery(params:URLSearchParams){
 if(Boolean(params.get('from'))!==Boolean(params.get('to')))throw new Error('Completa ambos límites del período.')
 if(params.get('from')&&params.get('to')&&params.get('from')!>params.get('to')!)throw new Error('El fin debe ser igual o posterior al inicio.')
 const query=new URLSearchParams()
 for(const key of changeFilterKeys){const value=params.get(key);if(!value)continue;query.set(key,key==='from'||key==='to'?ticketynDateTimeToIso(value+'T00:00'):value)}
 // The UI's last day is inclusive; backend receives an exclusive local midnight.
 if(params.get('to')){const day=new Date(params.get('to')+'T12:00:00Z');day.setUTCDate(day.getUTCDate()+1);query.set('to',ticketynDateTimeToIso(day.toISOString().slice(0,10)+'T00:00'))}
 return query
}
export function useChangeCatalogs(){
 const [catalogs,setCatalogs]=useState<ChangeCatalogs|null>(null),[error,setError]=useState<string|null>(null),[retry,setRetry]=useState(0)
 useEffect(()=>{const c=new AbortController();setError(null);Promise.all([listSectors(c.signal,true),listNodes(c.signal,true),listResponsibles(c.signal,true),listDepartments(c.signal,true),listChangeCompletionTypes(c.signal,true),listChangeTypes(c.signal,true)]).then(([sectors,nodes,people,departments,types,changeTypes])=>{if(!c.signal.aborted)setCatalogs({sectors,nodes,people,departments,types,changeTypes})}).catch(f=>{if(!c.signal.aborted)setError(f instanceof Error?f.message:'No se pudieron cargar los catálogos.')});return()=>c.abort()},[retry])
 return {catalogs,error,retry:()=>setRetry(retry+1)}
}
export function ChangeFilters({params,change,clear,catalogs}:{params:URLSearchParams;change:(values:Record<string,string>)=>void;clear:()=>void;catalogs:ChangeCatalogs|null}){
 const [search,setSearch]=useState(params.get('search')??'');useEffect(()=>setSearch(params.get('search')??''),[params])
 return <section className="filter-toolbar mb-4" aria-label="Filtros de cambios"><FilterHeading title="Filtros de cambios"/><form className="mt-3 flex flex-wrap items-end gap-3" onSubmit={e=>{e.preventDefault();change({search})}}><FormField id="change-search" label="Buscar"><input id="change-search" className="form-input" placeholder="Correlativo o título" value={search} onChange={e=>setSearch(e.target.value)}/></FormField><button className="button-secondary">Buscar</button></form><div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
 <FormField id="change-status" label="Estado"><select id="change-status" className="form-input" value={params.get('status')??''} onChange={e=>change({status:e.target.value})}><option value="">Todos</option>{Object.entries(changeStatuses).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></FormField>
 {(['from','to'] as const).map(key=><FormField key={key} id={'change-'+key} label={key==='from'?'Inicio propuesto desde':'Inicio propuesto hasta'}><input id={'change-'+key} type="date" className="form-input" value={params.get(key)??''} onChange={e=>change({[key]:e.target.value})}/></FormField>)}
 {([['manager_id','Encargado',catalogs?.people],['support_id','Personal de apoyo',catalogs?.people],['involved_id','Personal involucrado',catalogs?.people],['department_id','Departamento',catalogs?.departments],['sector_id','Sector',catalogs?.sectors],['node_id','Nodo',catalogs?.nodes],['completion_type_id','Tipo de finalización',catalogs?.types],['change_type_id','Tipo de cambio',catalogs?.changeTypes]] as const).map(([key,label,rows])=><FormField key={key} id={'change-'+key} label={label}><select id={'change-'+key} className="form-input" value={params.get(key)??''} onChange={e=>change({[key]:e.target.value})}><option value="">Todos</option>{rows?.map(row=><option key={row.id} value={row.id}>{row.name}{row.active?'':' (Inactivo)'}</option>)}</select></FormField>)}
 <FormField id="change-sort" label="Ordenar por"><select id="change-sort" className="form-input" value={params.get('sort')??'proposed_start'} onChange={e=>change({sort:e.target.value})}>{[['proposed_start','Inicio propuesto'],['reference','Correlativo'],['created_at','Creación'],['status','Estado'],['title','Título']].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></FormField><FormField id="change-direction" label="Dirección"><select id="change-direction" className="form-input" value={params.get('direction')??'desc'} onChange={e=>change({direction:e.target.value})}><option value="desc">Descendente</option><option value="asc">Ascendente</option></select></FormField>
 </div><button type="button" className="button-secondary mt-3" onClick={clear}>Limpiar filtros</button></section>
}
export function ChangeEfficiency({item}:{item:Change}){return <div><span>{item.efficiency_label}{item.variation_percent!==null?` · ${Math.abs(item.variation_percent)}%`:''}</span>{item.late_start&&<span className="chip chip-warning ml-2">Inicio tardío</span>}</div>}
export function ChangeTable({rows}:{rows:Change[]}){return <div className="table-surface overflow-x-auto"><table className="operation-table" aria-label="Control de cambios"><thead><tr>{['Correlativo','Título','Tipo de cambio','Sector / Nodo','Encargado','Personal de apoyo','Inicio agendado','Duración planificada','Estado','Tipo de finalización','Eficiencia'].map(label=><th key={label}>{label}</th>)}</tr></thead><tbody>{rows.map(row=><tr key={row.id}><td><Link to={`/changes/${row.id}`}>{row.reference}</Link></td><td>{row.title}</td><td>{row.change_type?.name??'Sin clasificar'}</td><td>{row.sector.name}{row.node&&` / ${row.node.name}`}</td><td>{row.manager_name}</td><td>{row.support.length?<details><summary>{row.support.length} participantes</summary>{row.support.map(p=><div key={p.id}>{p.name}</div>)}</details>:'Sin apoyo'}</td><td>{formatDate(row.proposed_start)}</td><td>{formatDuration(row.planned_seconds)}</td><td><span className={'change-status change-status-'+row.status}>{changeStatuses[row.status]}</span></td><td>{row.completion_name??'—'}</td><td><ChangeEfficiency item={row}/></td></tr>)}</tbody></table></div>}
export function ChangeTicketLinks({items,onChange,disabled}:{items:Change['internal_tickets'];onChange:(items:Change['internal_tickets'])=>void;disabled?:boolean}){
 const [open,setOpen]=useState(false),[selected,setSelected]=useState(''),[error,setError]=useState<string|null>(null),[loading,setLoading]=useState(false)
 async function add(){if(!selected||loading)return;setLoading(true);setError(null);try{const row=await getJson<{id:number;reference:string;title:string}>(`/api/internal-tickets/${selected}`);if(!items.some(item=>item.id===row.id))onChange([...items,row]);setSelected('');setOpen(false)}catch(f){setError(f instanceof Error?f.message:'No se pudo vincular.')}finally{setLoading(false)}}
 return <div>{items.length>0&&<ul className="mb-3 space-y-2">{items.map(row=><li key={row.id} className="flex flex-wrap items-center gap-3"><Link to={`/internal-tickets/${row.id}`}>{row.reference} — {row.title}</Link><button type="button" disabled={disabled} className="button-ghost" onClick={()=>onChange(items.filter(x=>x.id!==row.id))}>Desvincular {row.reference}</button></li>)}</ul>}<button type="button" disabled={disabled} className="button-secondary" onClick={()=>setOpen(!open)}>Vincular ticket interno</button>{open&&<div className="mt-3"><InternalTicketSelect value={selected} disabled={disabled||loading} onChange={setSelected}/><button type="button" className="button-secondary mt-2" disabled={!selected||disabled||loading} onClick={()=>void add()}>Agregar vínculo</button></div>}<RequestState compact error={error}/></div>
}
