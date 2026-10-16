import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { getJson } from '../api/client'
import type { InternalTicket } from '../types/internalTicket'
import { RequestState } from './RequestState'
export function RelatedInternalTicket({id}:{id?:number|null}) {
  const [ticket,setTicket]=useState<InternalTicket|null>(null),[error,setError]=useState<string|null>(null),[retry,setRetry]=useState(0)
  useEffect(()=>{const c=new AbortController();setTicket(null);setError(null);if(id)getJson<InternalTicket>(`/api/internal-tickets/${id}`,c.signal).then(x=>{if(!c.signal.aborted)setTicket(x)}).catch(f=>{if(!c.signal.aborted)setError(f instanceof Error?f.message:'No se pudo cargar el ticket interno.')});return()=>c.abort()},[id,retry])
  return <section className="noc-panel mt-4 p-4"><h3 className="section-label noc-section-title mb-2">Ticket interno relacionado</h3>{!id?<p className="text-sm">Sin ticket interno relacionado</p>:ticket?<Link className="text-primary [overflow-wrap:anywhere]" to={`/internal-tickets/${id}`}>{ticket.reference} — {ticket.title}</Link>:<RequestState compact loading={!error} error={error} onRetry={()=>setRetry(retry+1)}/>}</section>
}
