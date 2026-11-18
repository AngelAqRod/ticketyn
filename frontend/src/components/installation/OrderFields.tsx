import { useEffect, useId, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router'
import { listCircuits, listCustomers, listNodes, listSectors, listServiceTypes } from '../../api'
import { Can } from '../../auth/permissions'
import { FormField } from '../FormField'
import { SearchableSelect } from '../SearchableSelect'
import { QuickCatalogCreate } from '../QuickCatalogCreate'
import { RequestState } from '../RequestState'
import { OrderTechnicalData, technicalFromCircuit } from './OrderTechnical'
import { CircuitLocationData } from '../CircuitLocationData'
import type { Circuit, Customer, NamedCatalog } from '../../types/catalog'
import type { InstallationOrder, InstallationOrderInput, InstallationOrderType } from '../../types/installationOrders'
import { orderTypeLabels } from '../../types/installationOrders'
import { circuitLabel } from '../../lib/circuitLabel'
import { ticketynDateTimeToIso, ticketynDateTimeValue } from '../../lib/datetime'
import { installationError, listInstallationOrders } from '../../api/installationOrders'
// order_type '' only appears when editing a legacy order that was never classified.
export type OrderValues = { order_type: InstallationOrderType | ''; customer_id: string; circuit_id: string; description: string; service_type_id: string; node_id: string; sector_id: string; requested_at: string; external_reference: string; contact: string; phone: string; notes: string }
type OrderData = Partial<InstallationOrderInput> | InstallationOrder
const id = (value: unknown) => typeof value === 'number' && Number.isInteger(value) && value > 0 ? String(value) : ''
export function orderValues(data: OrderData = {}): OrderValues {
 const text = (value: unknown) => typeof value === 'string' ? value : ''
 const date = typeof data.requested_at === 'string' ? new Date(data.requested_at) : null
 const type = data.order_type === 'EXTRAORDINARY' || data.order_type === 'NORMAL' ? data.order_type : 'order_type' in data ? '' : 'NORMAL'
 return { order_type: type, customer_id: id(data.customer_id), circuit_id: id(data.circuit_id), description: text(data.description), service_type_id: id(data.service_type_id), node_id: id(data.node_id), sector_id: id(data.sector_id), requested_at: date && !Number.isNaN(date.getTime()) ? ticketynDateTimeValue(date) : '', external_reference: text(data.external_reference), contact: text(data.contact), phone: text(data.phone), notes: text(data.notes) }
}
export function orderPayload(values: OrderValues, draft = false): Partial<InstallationOrderInput> {
 const normal = values.order_type === 'NORMAL', extraordinary = values.order_type === 'EXTRAORDINARY'
 if (!draft) {
  const missing = !values.customer_id || !values.requested_at || (normal && !values.circuit_id) || (extraordinary && (!values.description.trim() || !values.service_type_id || !values.node_id || !values.sector_id))
  if (missing) throw new Error(normal ? 'Completa cliente, circuito y fecha de solicitud.' : extraordinary ? 'Completa cliente, descripción, servicio, nodo, sector y fecha de solicitud.' : 'Completa cliente y fecha de solicitud.')
 }
 const optional = (key: 'circuit_id' | 'service_type_id' | 'node_id' | 'sector_id') => values[key] ? { [key]: Number(values[key]) } : {}
 return { ...(values.order_type ? { order_type: values.order_type } : {}), ...(values.customer_id ? { customer_id: Number(values.customer_id) } : {}), ...(normal ? optional('circuit_id') : {}), ...(extraordinary ? { ...(values.description.trim() ? { description: values.description.trim() } : {}), ...optional('service_type_id'), ...optional('node_id'), ...optional('sector_id') } : {}), ...(values.requested_at ? { requested_at: ticketynDateTimeToIso(values.requested_at) } : {}), external_reference: values.external_reference.trim() || null, contact: values.contact.trim() || null, phone: values.phone.trim() || null, notes: values.notes.trim() || null }
}
// The type and the circuit are permanent: an edit never sends them.
export function orderPatch(values: OrderValues): Partial<InstallationOrderInput> {
 const { order_type: _type, circuit_id: _circuit, ...rest } = orderPayload(values)
 return rest
}
export function OrderFields({ value, onChange, disabled = false, locked = false }: { value: OrderValues; onChange: (value: OrderValues) => void; disabled?: boolean; locked?: boolean }) {
 const uid = useId()
 const [customers, setCustomers] = useState<Customer[]>([]), [circuits, setCircuits] = useState<Circuit[]>([]), [catalogs, setCatalogs] = useState<{ services: NamedCatalog[]; nodes: NamedCatalog[]; sectors: NamedCatalog[] }>({ services: [], nodes: [], sectors: [] })
 const [error, setError] = useState<string | null>(null), [circuitError, setCircuitError] = useState<string | null>(null), [loading, setLoading] = useState(true), [circuitLoading, setCircuitLoading] = useState(false), [retry, setRetry] = useState(0)
 const [quick, setQuick] = useState<'customer' | 'circuit' | null>(null), [notice, setNotice] = useState<string | null>(null), [existing, setExisting] = useState<{ id: number; reference: string } | null>(null)
 const normal = value.order_type === 'NORMAL', extraordinary = value.order_type === 'EXTRAORDINARY', typed = normal || extraordinary
 const fixedCustomer = locked && normal
 const set = (key: keyof OrderValues, val: string) => onChange({ ...value, [key]: val })
 useEffect(() => {
  const controller = new AbortController(); setLoading(true); setError(null)
  const catalogRequests = extraordinary ? Promise.all([listServiceTypes(controller.signal), listNodes(controller.signal), listSectors(controller.signal)]) : Promise.resolve(null)
  Promise.all([listCustomers(controller.signal), catalogRequests]).then(([rows, extra]) => { if (!controller.signal.aborted) { setCustomers(rows); if (extra) setCatalogs({ services: extra[0], nodes: extra[1], sectors: extra[2] }); setLoading(false) } }).catch(cause => { if (!controller.signal.aborted) { setError(installationError(cause)); setLoading(false) } })
  return () => controller.abort()
 }, [retry, extraordinary])
 useEffect(() => {
  if (!normal || !value.customer_id) { setCircuits([]); setCircuitError(null); return }
  const controller = new AbortController(); setCircuitLoading(true); setCircuitError(null)
  listCircuits(Number(value.customer_id), controller.signal).then(rows => { if (!controller.signal.aborted) { setCircuits(rows); setCircuitLoading(false) } }).catch(cause => { if (!controller.signal.aborted) { setCircuitError(installationError(cause)); setCircuitLoading(false) } })
  return () => controller.abort()
 }, [normal, value.customer_id, retry])
 useEffect(() => {
  setExisting(null)
  if (!normal || !value.circuit_id || locked) return
  const controller = new AbortController()
  // Informational only: operators without installation_orders.view simply do not see the notice; the backend still rejects duplicates.
  listInstallationOrders(new URLSearchParams({ circuit_id: value.circuit_id, limit: '1' }), controller.signal).then(({ data }) => { if (!controller.signal.aborted && data[0]) setExisting({ id: data[0].id, reference: data[0].reference }) }).catch(() => {})
  return () => controller.abort()
 }, [normal, value.circuit_id, locked])
 const selectedCustomer = customers.find(row => String(row.id) === value.customer_id)
 const selectedCircuit = useMemo(() => circuits.find(row => String(row.id) === value.circuit_id), [circuits, value.circuit_id])
 // A different customer invalidates the previous circuit, so the order can never mix customers.
 const changeCustomer = (customer: string) => onChange({ ...value, customer_id: customer, ...(customer === value.customer_id ? {} : { circuit_id: '' }) })
 function customerCreated(customer: Customer) {
  setCustomers(rows => [...rows.filter(row => row.id !== customer.id), customer])
  onChange({ ...value, customer_id: String(customer.id), circuit_id: '' }); setQuick(null); setNotice(`Cliente ${customer.customer_code} creado y seleccionado.`)
 }
 function circuitCreated(circuit: Circuit) {
  setCircuits(rows => [...rows.filter(row => row.id !== circuit.id), circuit])
  onChange({ ...value, circuit_id: String(circuit.id) }); setQuick(null); setNotice(`Circuito ${circuit.circuit_code} creado y seleccionado.`)
 }
 const catalog = (key: 'service_type_id' | 'node_id' | 'sector_id', label: string, rows: NamedCatalog[]): ReactNode => <FormField key={key} id={`${uid}-${key}`} label={label} required><SearchableSelect id={`${uid}-${key}`} label={label} required value={value[key]} onChange={v => set(key, v)} options={rows.map(row => ({ value: String(row.id), label: row.name, disabled: !row.active }))} placeholder={`Selecciona ${label.toLowerCase()}`} emptyMessage="No hay opciones disponibles." noMatchMessage="No se encontraron resultados." /></FormField>
 return <fieldset disabled={disabled} className="installation-fields"><legend className="sr-only">Datos de la orden</legend>
 {!locked && <div role="radiogroup" aria-label="Tipo de orden" className="segmented-control segmented-control--soft segmented-control--emerald">{(['NORMAL', 'EXTRAORDINARY'] as const).map(type => <button key={type} type="button" role="radio" aria-checked={value.order_type === type} className="segment-button" aria-pressed={value.order_type === type} onClick={() => value.order_type !== type && onChange({ ...value, order_type: type })}>{orderTypeLabels[type]}</button>)}</div>}
 {locked && <p><span className={`status-badge ${extraordinary ? 'status-warning' : 'status-neutral'}`}>{typed ? `Orden ${orderTypeLabels[value.order_type as InstallationOrderType].toLowerCase()}` : 'Orden sin clasificar'}</span> <span className="text-sm text-slate-400">El tipo de orden es permanente.</span></p>}
 <FormField id={`${uid}-customer`} label="Cliente" required><div className="flex items-start gap-2"><div className="min-w-0 flex-1"><SearchableSelect id={`${uid}-customer`} label="Cliente" required value={value.customer_id} onChange={changeCustomer} options={customers.map(row => ({ value: String(row.id), label: `${row.customer_code} — ${row.name}`, disabled: !row.active }))} disabled={disabled || loading || Boolean(error) || fixedCustomer} placeholder="Selecciona un cliente existente" emptyMessage="No hay clientes disponibles." noMatchMessage="No se encontraron clientes." /></div>
 {normal && !locked && <Can anyOf={['customers.create', 'context.customers.create']}><button type="button" className="button-secondary rounded-full shrink-0" aria-label="Crear cliente" title="Crear cliente" disabled={disabled || loading || Boolean(error)} onClick={() => setQuick('customer')}>+</button></Can>}</div></FormField>
 <RequestState compact loading={loading} error={error} onRetry={() => setRetry(v => v + 1)} />
 {normal && <><FormField id={`${uid}-circuit`} label="Circuito" required><div className="flex items-start gap-2"><div className="min-w-0 flex-1"><SearchableSelect id={`${uid}-circuit`} label="Circuito" required value={value.circuit_id} onChange={v => set('circuit_id', v)} options={circuits.map(row => ({ value: String(row.id), label: circuitLabel(row), disabled: !row.active }))} disabled={disabled || locked || !value.customer_id || circuitLoading || Boolean(circuitError)} placeholder={!value.customer_id ? 'Selecciona primero un cliente' : circuitLoading ? 'Cargando circuitos...' : 'Selecciona un circuito existente'} emptyMessage="Este cliente no tiene circuitos disponibles." noMatchMessage="No se encontraron circuitos." /></div>
 {!locked && <Can anyOf={['circuits.create', 'context.circuits.create']}><button type="button" className="button-secondary rounded-full shrink-0" aria-label="Crear circuito" title="Crear circuito" disabled={disabled || !selectedCustomer || circuitLoading || Boolean(circuitError)} onClick={() => setQuick('circuit')}>+</button></Can>}</div></FormField>
 <RequestState compact error={circuitError ? `Error al cargar circuitos: ${circuitError}` : null} onRetry={() => setRetry(v => v + 1)} />
 {existing && <p role="alert" className="text-amber-300">Este circuito ya tiene la orden de instalación <Link className="underline" to={`/installation-orders/${existing.id}`}>{existing.reference}</Link>. Un circuito admite una sola orden normal.</p>}
 {selectedCircuit ? <><OrderTechnicalData technical={technicalFromCircuit(selectedCircuit)} title="Datos técnicos del circuito" /><CircuitLocationData site={selectedCircuit} title="Ubicación del circuito" /></> : <p className="text-sm text-slate-400">Selecciona un circuito para consultar sus datos técnicos.</p>}</>}
 {extraordinary && <><FormField id={`${uid}-description`} label="Descripción" required><textarea id={`${uid}-description`} className="form-input" rows={3} required maxLength={20000} value={value.description} onChange={e => set('description', e.target.value)} /></FormField>{catalog('service_type_id', 'Servicio solicitado', catalogs.services)}{catalog('node_id', 'Nodo', catalogs.nodes)}{catalog('sector_id', 'Sector', catalogs.sectors)}</>}
 {notice && <p role="status" className="text-emerald-300">{notice}</p>}
 {([['external_reference', 'Referencia externa'], ['contact', 'Contacto'], ['phone', 'Teléfono']] as const).map(([key, label]) => <FormField key={key} id={`${uid}-${key}`} label={label}><input id={`${uid}-${key}`} className="form-input" value={value[key]} maxLength={key === 'phone' ? 80 : 2000} type={key === 'phone' ? 'tel' : 'text'} onChange={e => set(key, e.target.value)} /></FormField>)}
 <FormField id={`${uid}-date`} label="Fecha de solicitud (America/Guatemala)" required><input className="form-input" id={`${uid}-date`} type="datetime-local" required value={value.requested_at} onChange={e => set('requested_at', e.target.value)} /></FormField>
 <FormField id={`${uid}-notes`} label="Observaciones"><textarea id={`${uid}-notes`} className="form-input" rows={4} value={value.notes} onChange={e => set('notes', e.target.value)} /></FormField>
 {/* Portal + stopPropagation: the quick-create dialog owns a <form>; its submit must never reach the order form. */}
 {quick && createPortal(<div onSubmit={event => event.stopPropagation()}>{quick === 'customer' ? <QuickCatalogCreate kind="customer" onCancel={() => setQuick(null)} onCreated={customerCreated} /> : selectedCustomer && <QuickCatalogCreate kind="circuit" customer={selectedCustomer} onCancel={() => setQuick(null)} onCreated={circuitCreated} />}</div>, document.body)}
 </fieldset>
}
