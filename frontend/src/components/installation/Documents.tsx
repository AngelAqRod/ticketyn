import { useEffect, useState } from 'react'
import type { InstallationDocument, InstallationEvent } from '../../types/installationOrders'
import { downloadInstallationDocument, installationDocumentBlob, installationError } from '../../api/installationOrders'
import { formatDate } from '../../lib/format'
import { ticketynTimezone } from '../../lib/datetime'
import { RequestState } from '../RequestState'
export function InstallationDocuments({documents}: {documents: InstallationDocument[]}) {
 const [selected,setSelected]=useState<number|null>(null), [url,setUrl]=useState<string|null>(null), [error,setError]=useState<string|null>(null), [loading,setLoading]=useState(false), [zoom,setZoom]=useState(100)
 const doc=documents.find(row=>row.id===selected) ?? documents.find(row=>row.media_type!=='message/rfc822') ?? documents[0]
 const preview=Boolean(doc && ['image/png','image/jpeg','application/pdf'].includes(doc.media_type))
 useEffect(()=>{
  setUrl(null);setError(null);setZoom(100)
  if(!doc || !preview){setLoading(false);return}
  const controller=new AbortController(); let objectUrl:string|undefined;setLoading(true)
  installationDocumentBlob(doc.id,controller.signal).then(blob=>{if(!controller.signal.aborted){objectUrl=URL.createObjectURL(new Blob([blob],{type:doc.media_type}));setUrl(objectUrl);setLoading(false)}}).catch(cause=>{if(!controller.signal.aborted){setError(installationError(cause));setLoading(false)}})
  return ()=>{controller.abort();if(objectUrl)URL.revokeObjectURL(objectUrl)}
 },[doc?.id,doc?.media_type,preview])
 async function download(){if(!doc)return;try{setError(null);await downloadInstallationDocument(doc)}catch(cause){setError(installationError(cause))}}
 if(!doc)return <p className="text-slate-400">Sin documentos adjuntos.</p>
 return <section aria-label="Documentos originales"><div className="installation-document-actions"><label className="min-w-0 flex-1">Documento<select aria-label="Documento" className="form-input" value={doc.id} onChange={e=>setSelected(Number(e.target.value))}>{documents.map(row=><option key={row.id} value={row.id}>{row.original_name} ({Math.ceil(row.size/1024)} KB)</option>)}</select></label><button type="button" className="button-secondary" onClick={()=>void download()}>Descargar original</button></div>
 <RequestState compact loading={loading} error={error}/>
 {preview && <label className="mb-3 flex items-center gap-3">Zoom<input aria-label="Zoom del documento" type="range" min="50" max="200" step="10" value={zoom} onChange={e=>setZoom(Number(e.target.value))}/><output>{zoom}%</output></label>}
 {url && preview && <div className="installation-preview">{doc.media_type==='application/pdf'?<iframe key={`${url}-${zoom}`} title={`Vista previa: ${doc.original_name}`} sandbox="allow-same-origin" src={`${url}#zoom=${zoom}`} referrerPolicy="no-referrer"/>:<img alt={`Documento original: ${doc.original_name}`} src={url} style={{width:`${zoom}%`}}/>}</div>}
 {!preview && <p className="text-sm text-slate-300">Este formato solo está disponible mediante descarga autorizada.</p>}
 </section>
}
const eventLabels:Record<string,string>={create:'Orden registrada',edit:'Orden editada',link:'Circuito asociado',unlink:'Circuito desvinculado',draft:'Borrador guardado',process:'Solicitud procesada',discard:'Solicitud descartada',receive:'Recepción de correo',received:'Recepción de correo',review:'Revisión iniciada',reviewed:'Revisión iniciada',draft_saved:'Borrador guardado',processed:'Solicitud procesada',discarded:'Solicitud descartada',created:'Orden registrada',updated:'Orden editada',circuit_linked:'Circuito asociado',circuit_unlinked:'Circuito desvinculado',circuit_created:'Circuito creado y asociado'}
export function InstallationHistory({events}: {events: InstallationEvent[]}) {
 return <section className="panel installation-section"><h2>Historial de eventos</h2>{!events.length?<p className="text-slate-400">Sin eventos.</p>:<ol className="installation-history">{events.map(event=><li key={event.id}><strong>{eventLabels[event.action.toLowerCase()] ?? event.action}</strong><p className="text-xs text-slate-400">{formatDate(event.created_at,ticketynTimezone)} · {event.actor?.name ?? (event.actor_id?`Responsable #${event.actor_id}`:'Sistema')}</p>{event.detail && Object.keys(event.detail).length>0 && <p className="text-sm break-words">{Object.entries(event.detail).map(([key,value])=>`${key}: ${typeof value==='object'?JSON.stringify(value):String(value)}`).join(' · ')}</p>}</li>)}</ol>}</section>
}
