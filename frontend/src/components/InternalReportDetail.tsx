import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { getJson } from '../api/client'
import { reportParams } from '../api/reports'
import type { ReportQuery } from '../types/report'
import type { InternalTicket } from '../types/internalTicket'
import { RequestState } from './RequestState'
import { PaginationBar } from './PaginationBar'
import { StatusBadge } from './StatusBadge'

export function InternalReportDetail({query,offset,retry,onPage}:{query:ReportQuery;offset:number;retry:number;onPage:(offset:number)=>void}) {
  const [rows,setRows]=useState<InternalTicket[]>([]),[loading,setLoading]=useState(true),[error,setError]=useState<string|null>(null)
  const key=reportParams(query)
  useEffect(()=>{
    const controller=new AbortController();setLoading(true);setError(null)
    const params=new URLSearchParams(key);params.delete('timezone');params.delete('granularity');params.delete('recipient_id');params.set('limit','50');params.set('offset',String(offset))
    getJson<InternalTicket[]>(`/api/internal-tickets?${params}`,controller.signal).then(data=>{if(!controller.signal.aborted){setRows(data);setLoading(false)}}).catch(f=>{if(!controller.signal.aborted){setError(f instanceof Error?f.message:'No se pudo cargar.');setLoading(false)}})
    return()=>controller.abort()
  },[key,offset,retry])
  return <><RequestState loading={loading} error={error} empty={!loading&&!error&&rows.length===0}/>{!loading&&!error&&rows.length>0&&<div className="table-surface overflow-x-auto"><table className="operation-table" aria-label="Detalle de tickets internos"><thead><tr>{['Correlativo','Incidencia','Estado','Sector','Proveedor','Tickets vinculados'].map(label=><th key={label}>{label}</th>)}</tr></thead><tbody>{rows.map(row=><tr key={row.id}><td><Link to={`/internal-tickets/${row.id}`}>{row.reference}</Link></td><td>{row.title}</td><td><StatusBadge status={row.status}/></td><td>{row.sector.name}</td><td>{row.provider?.name ?? 'Ninguno'}</td><td>{row.related_count}</td></tr>)}</tbody></table></div>}<PaginationBar page={Math.floor(offset/50)+1} info={<span className="text-xs">Página {Math.floor(offset/50)+1} · Las exportaciones incluyen todos los resultados.</span>} previousDisabled={offset===0||loading} nextDisabled={loading||Boolean(error)||rows.length<50} onPrevious={()=>onPage(Math.max(0,offset-50))} onNext={()=>onPage(offset+50)}/></>
}
