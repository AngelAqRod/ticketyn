import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ClipboardCheck } from 'lucide-react'
import { usePermissions } from '../../auth/permissions'
import { installationError, listInstallationOrders } from '../../api/installationOrders'
import type { InstallationOrder } from '../../types/installationOrders'
import { RequestState } from '../RequestState'
export function CircuitInstallationOrder({circuitId,customerId}: {circuitId:number;customerId?:number}) {
 const access=usePermissions(),[order,setOrder]=useState<InstallationOrder|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState<string|null>(null),[retry,setRetry]=useState(0),allowed=access.can('installation_orders.view')
 useEffect(()=>{if(!allowed)return;const controller=new AbortController();setLoading(true);setOrder(null);setError(null);listInstallationOrders(new URLSearchParams({circuit_id:String(circuitId),limit:'1'}),controller.signal).then(({data})=>{if(!controller.signal.aborted){setOrder(data[0]??null);setLoading(false)}}).catch(cause=>{if(!controller.signal.aborted){setError(installationError(cause));setLoading(false)}});return()=>controller.abort()},[circuitId,allowed,retry])
 if(!allowed)return null
 return <section className="panel rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl p-4" aria-label="Orden de instalación">
 <div className="flex items-center gap-2 border-b border-sky-500/15 pb-2 mb-3"><span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs" aria-hidden="true"><ClipboardCheck size={14}/></span><h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">Orden de instalación</h2></div>
 <RequestState compact loading={loading} error={error} onRetry={()=>setRetry(v=>v+1)}/>
 {!loading && !error && (order?<Link className="text-emerald-400 font-mono font-bold tracking-wide underline" to={`/installation-orders/${order.id}`}>{order.reference}</Link>:<div className="flex flex-wrap items-center gap-x-4 gap-y-2"><p className="text-sm text-slate-400 font-mono">Sin orden de instalación asociada.</p>{customerId!==undefined && access.can('installation_orders.create') && <Link className="button-secondary" to={`/installation-orders/new?customer_id=${customerId}&circuit_id=${circuitId}`}>Crear orden normal</Link>}</div>)}
 </section>
}
