import { useEffect,useState } from 'react'
import { Link } from 'react-router'
import { getJson } from '../api/client'
import { RequestState } from './RequestState'
import { PaginationBar } from './PaginationBar'
import type { Change } from '../types/change'
import { changeStatuses } from './ChangeShared'
export function RelatedChanges({internalTicketId}:{internalTicketId:number}){
 const [data,setData]=useState<{total:number;items:Change[]}|null>(null),[offset,setOffset]=useState(0),[error,setError]=useState<string|null>(null)
 useEffect(()=>{const c=new AbortController();setError(null);getJson<{total:number;items:Change[]}>(`/api/changes?internal_ticket_id=${internalTicketId}&limit=50&offset=${offset}`,c.signal).then(row=>{if(!c.signal.aborted)setData(row)}).catch(f=>{if(!c.signal.aborted)setError(f instanceof Error?f.message:'No se pudieron cargar los cambios relacionados.')});return()=>c.abort()},[internalTicketId,offset])
 if(!error&&!data?.total)return null
 return <section className="noc-panel mt-4 p-4"><h2 className="noc-section-title mb-3">Cambios relacionados ({data?.total??0})</h2><RequestState error={error} compact/><ul className="space-y-2">{data?.items?.map(row=><li key={row.id}><Link to={`/changes/${row.id}`}>{row.reference} — {row.title}</Link> · {changeStatuses[row.status]}</li>)}</ul><PaginationBar page={Math.floor(offset/50)+1} info={<span className="text-xs">Página {Math.floor(offset/50)+1}</span>} previousDisabled={offset===0} nextDisabled={!data||offset+50>=data.total} onPrevious={()=>setOffset(Math.max(0,offset-50))} onNext={()=>setOffset(offset+50)}/></section>
}
