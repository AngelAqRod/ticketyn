import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { PageHeading } from '../components/PageHeading'
import { RequestState } from '../components/RequestState'
import { OrderFields, orderPatch, orderPayload, orderValues } from '../components/installation/OrderFields'
import { createInstallationOrder, getInstallationOrder, installationError, updateInstallationOrder, uploadInstallationDocument } from '../api/installationOrders'
import type { InstallationOrderInput } from '../types/installationOrders'
import '../styles/installationOrders.css'
export function InstallationOrderForm({edit=false}: {edit?:boolean}) {
 const navigate=useNavigate(),id=Number(useParams().id),[search]=useSearchParams(),[values,setValues]=useState(()=>orderValues({customer_id:Number(search.get('customer_id')) || undefined,circuit_id:Number(search.get('circuit_id')) || undefined})),[files,setFiles]=useState<File[]>([]),[savedId,setSavedId]=useState<number|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null),[loading,setLoading]=useState(edit),[retry,setRetry]=useState(0),sending=useRef(false)
 useEffect(()=>{if(!edit)return;const controller=new AbortController();setLoading(true);getInstallationOrder(id,controller.signal).then(row=>{if(!controller.signal.aborted){setValues(orderValues(row));setLoading(false)}}).catch(cause=>{if(!controller.signal.aborted){setError(installationError(cause));setLoading(false)}});return()=>controller.abort()},[id,edit,retry])
 async function submit(event:FormEvent){event.preventDefault();if(sending.current)return;sending.current=true;setBusy(true);setError(null)
 try{const orderId=savedId ?? (edit ? (await updateInstallationOrder(id,orderPatch(values))).id : (await createInstallationOrder(orderPayload(values) as InstallationOrderInput)).id);setSavedId(orderId)
 for(const file of files){await uploadInstallationDocument(orderId,file);setFiles(current=>current.filter(row=>row!==file))}
 navigate(`/installation-orders/${orderId}`)
 }catch(cause){setError(installationError(cause))}finally{sending.current=false;setBusy(false)}}
 return <><PageHeading title={edit?'Editar orden de instalación':'Registrar orden de instalación'} description="Orden normal asociada a un circuito, u orden extraordinaria sin circuito." theme="emerald" action={<Link className="button-secondary" to={edit?`/installation-orders/${id}`:'/installation-orders'}>Volver</Link>}/>
 <RequestState compact loading={loading} error={error} onRetry={edit?()=>setRetry(v=>v+1):undefined}/>
 {!loading && <form className="panel installation-section max-w-3xl" onSubmit={submit} noValidate aria-label="Registro de orden de instalación"><OrderFields value={values} onChange={setValues} disabled={busy || savedId!==null} locked={edit}/>
 {!edit && <div className="mt-4"><label className="form-label" htmlFor="order-files">Documentos adjuntos</label><input id="order-files" type="file" multiple disabled={busy} onChange={e=>setFiles(Array.from(e.target.files ?? []))}/><ul>{files.map((file,index)=><li key={`${file.name}-${index}`}>{file.name}</li>)}</ul></div>}
 {savedId!==null && error && <p className="mt-4 text-amber-300">La orden ya está registrada. Reintenta para cargar únicamente los documentos pendientes, sin duplicar la orden. <Link className="underline" to={`/installation-orders/${savedId}`}>Ver orden</Link></p>}
 <div className="mt-6 flex gap-3"><button className="button-primary button-primary--emerald" disabled={busy} type="submit">{busy?'Guardando…':savedId?'Reintentar documentos':edit?'Guardar cambios':'Registrar orden'}</button></div></form>}</>
}
