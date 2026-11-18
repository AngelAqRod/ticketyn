import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { usePermissions } from '../auth/permissions'
import { getInstallationOrder, installationError, uploadInstallationDocument } from '../api/installationOrders'
import type { InstallationOrder } from '../types/installationOrders'
import { PageHeading } from '../components/PageHeading'
import { RequestState } from '../components/RequestState'
import { InstallationDocuments, InstallationHistory } from '../components/installation/Documents'
import { OrderCircuit } from '../components/installation/OrderCircuit'
import { OrderTechnicalData } from '../components/installation/OrderTechnical'
import { CircuitLocationData } from '../components/CircuitLocationData'
import { orderTypeLabels } from '../types/installationOrders'
import { formatDate } from '../lib/format'
import { ticketynTimezone } from '../lib/datetime'
import '../styles/installationOrders.css'
export function InstallationOrderDetail(){
 const access=usePermissions(),id=Number(useParams().id),[order,setOrder]=useState<InstallationOrder|null>(null),[error,setError]=useState<string|null>(null),[retry,setRetry]=useState(0),[busy,setBusy]=useState(false),[files,setFiles]=useState<File[]>([])
 useEffect(()=>{const controller=new AbortController();setOrder(null);setError(null);getInstallationOrder(id,controller.signal).then(data=>{if(!controller.signal.aborted)setOrder(data)}).catch(cause=>{if(!controller.signal.aborted)setError(installationError(cause))});return()=>controller.abort()},[id,retry])
 async function upload(){if(busy)return;setBusy(true);setError(null);try{for(const file of files){await uploadInstallationDocument(id,file);setFiles(current=>current.filter(row=>row!==file))}setRetry(v=>v+1)}catch(cause){setError(installationError(cause))}finally{setBusy(false)}}
 if(!order)return <RequestState loading={!error} error={error} onRetry={()=>setRetry(v=>v+1)}/>
 const data=[['Cliente',order.customer?.name],...(order.order_type==='EXTRAORDINARY'?[['Descripción',order.description]]:[]),...(order.order_type===null?[['Servicio solicitado (registro anterior)',order.service],['Ubicación (registro anterior)',order.location]]:[]),['Referencia externa',order.external_reference],['Contacto',order.contact],['Teléfono',order.phone],['Fecha de solicitud',formatDate(order.requested_at,ticketynTimezone)],['Registrada por',order.author?.name],['Observaciones',order.notes]]
 return <><PageHeading title={order.reference} description={order.source_request_id?'Orden registrada a partir de una solicitud por correo.':'Orden registrada manualmente.'} theme="emerald" action={<div className="flex gap-3 flex-wrap"><Link className="button-secondary" to="/installation-orders?tab=orders">Volver a órdenes</Link>{access.can('installation_orders.edit') && <Link className="button-primary button-primary--emerald" to={`/installation-orders/${id}/edit`}>Editar orden</Link>}</div>}/>
 <RequestState compact error={error}/><section className="panel installation-section"><h2>Solicitud de instalación <span className={`status-badge ${order.order_type==='EXTRAORDINARY'?'status-warning':'status-neutral'}`}>{order.order_type?`Orden ${orderTypeLabels[order.order_type].toLowerCase()}`:'Orden sin clasificar'}</span></h2><dl className="installation-data">{data.map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value || 'No indicado'}</dd></div>)}</dl></section>
 {order.technical && <section className="panel installation-section"><OrderTechnicalData technical={order.technical} title={order.order_type==='NORMAL'?'Datos técnicos del circuito':'Servicio, nodo y sector solicitados'}/>{order.circuit_location && <div className="mt-5"><CircuitLocationData site={order.circuit_location} title="Ubicación del circuito"/></div>}</section>}
 <OrderCircuit order={order} onChange={setOrder}/>
 <section className="panel installation-section"><h2>Documentos originales</h2><InstallationDocuments documents={order.documents ?? []}/>{access.can('installation_orders.edit') && <div className="mt-6"><label className="form-label" htmlFor="detail-documents">Agregar documentos</label><input id="detail-documents" type="file" multiple disabled={busy} onChange={e=>setFiles(Array.from(e.target.files ?? []))}/><ul>{files.map((file,index)=><li key={`${file.name}-${index}`}>{file.name}</li>)}</ul><button className="button-secondary mt-3" disabled={busy || !files.length} onClick={()=>void upload()}>{busy?'Subiendo…':'Subir documentos'}</button></div>}</section>
 {order.source_request_id && <section className="panel installation-section"><h2>Correo original</h2><p className="mb-3 text-slate-300">El correo y sus adjuntos se conservan en los documentos originales de esta orden.</p>{order.source_request && <><dl className="installation-data"><div><dt>Remitente</dt><dd>{order.source_request.sender}</dd></div><div><dt>Asunto</dt><dd>{order.source_request.subject}</dd></div><div><dt>Recibido</dt><dd>{formatDate(order.source_request.received_at,ticketynTimezone)}</dd></div><div><dt>Message-ID</dt><dd>{order.source_request.message_id || 'No disponible'}</dd></div></dl><pre className="installation-email my-4">{order.source_request.body || 'Sin contenido de texto. Consulta los documentos originales.'}</pre></>}{access.can('installation_requests.review') && <Link className="text-emerald-400 underline" to={`/installation-requests/${order.source_request_id}`}>Consultar solicitud de origen</Link>}</section>}
 <InstallationHistory events={order.events ?? []}/></>
}
