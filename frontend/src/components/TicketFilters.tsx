import { RequestState } from './RequestState'
import { useEffect, useState } from 'react'
import { listCircuits, listCustomers, listDepartments, listIncidentTypes, listSectors, listNodes, listResponsibles } from '../api'
import type { Circuit, Customer, NamedCatalog } from '../types/catalog'
import { SearchableSelect } from './SearchableSelect'
import { FormField } from './FormField'
import { FilterChips } from './FilterChips'
import { SlidersHorizontal } from 'lucide-react'
import { reportPeriod } from '../lib/reportPeriod'

interface Props { params: URLSearchParams; change: (values: Record<string, string>) => void; clear: () => void }
interface Catalogs { customers: Customer[]; sectors: NamedCatalog[]; departments: NamedCatalog[]; types: NamedCatalog[]; nodes: NamedCatalog[]; responsibles: NamedCatalog[] }
export function TicketFilters({ params, change, clear }: Props) {
  const [catalogs, setCatalogs] = useState<Catalogs | null>(null)
  const [circuits, setCircuits] = useState<Circuit[]>([])
  const [loading, setLoading] = useState(true)
  const [circuitLoading, setCircuitLoading] = useState(true)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [circuitError, setCircuitError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const [quickPeriod, setQuickPeriod] = useState({ value: 'all', from: '', to: '' })
  const from = params.get('from') ?? ''
  const to = params.get('to') ?? ''
  const selectedPeriod = quickPeriod.from === from && quickPeriod.to === to
    ? quickPeriod.value : from || to ? 'custom' : 'all'
  function choosePeriod(value: string) {
    const range = value === 'all' ? { from: '', to: '' }
      : value === 'custom' ? { from, to }
      : reportPeriod(new URLSearchParams({ period: value }))
    setQuickPeriod({ value, from: range.from, to: range.to })
    if (value !== 'custom') change({ from: range.from, to: range.to })
  }
  function changeDate(key: 'from' | 'to', value: string) {
    setQuickPeriod({ value: 'custom', from: key === 'from' ? value : from, to: key === 'to' ? value : to })
    change({ [key]: value })
  }
  const customerId = params.get('customer_id') ?? ''
  const circuitId = params.get('circuit_id') ?? ''
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setCatalogError(null)
    Promise.all([listCustomers(controller.signal, true), listSectors(controller.signal, true), listDepartments(controller.signal, true), listIncidentTypes(controller.signal, true), listNodes(controller.signal, true), listResponsibles(controller.signal, true)])
      .then(([customers, sectors, departments, types, nodes, responsibles]) => { if (!controller.signal.aborted) { setCatalogs({ customers, sectors, departments, types, nodes, responsibles }); setLoading(false) } })
      .catch((error: unknown) => { if (!controller.signal.aborted) { setCatalogError(error instanceof Error ? error.message : 'Error cargando catálogos.'); setLoading(false) } })
    return () => controller.abort()
  }, [retry])
  useEffect(() => {
    const controller = new AbortController()
    setCircuitLoading(true); setCircuitError(null); setCircuits([])
    listCircuits(customerId ? Number(customerId) : undefined, controller.signal, true)
      .then((items) => { if (!controller.signal.aborted) { setCircuits(items); setCircuitLoading(false) } })
      .catch((error: unknown) => { if (!controller.signal.aborted) { setCircuitError(error instanceof Error ? error.message : 'Error cargando circuitos.'); setCircuitLoading(false) } })
    return () => controller.abort()
  }, [customerId, retry])
  function chooseCustomer(value: string) {
    const selected = circuits.find((item) => String(item.id) === circuitId)
    change({ customer_id: value, ...(value && circuitId && (!selected || String(selected.customer_id) !== value) ? { circuit_id: '' } : {}) })
  }
  function chooseCircuit(value: string) {
    const selected = circuits.find((item) => String(item.id) === value)
    change({ circuit_id: value, ...(!customerId && selected ? { customer_id: String(selected.customer_id) } : {}) })
  }
  const named = [['sector_id', 'Sector', catalogs?.sectors], ['department_id', 'Departamento', catalogs?.departments], ['incident_type_id', 'Tipo de incidencia', catalogs?.types]] as const
  const assignments = [['node_id', 'Nodo', catalogs?.nodes], ['responsible_id', 'Responsable', catalogs?.responsibles]] as const
  return <section aria-label="Filtros de tickets" className="filter-toolbar">
    <p className="toolbar-heading gap-3"><span className="icon-surface" aria-hidden="true"><SlidersHorizontal size={15} /></span>Filtros de tickets</p>
    <div className="segmented-control mb-3 max-w-full" role="group" aria-label="Período de tickets">
      {['all', '1', '7', '15', '30', 'custom'].map((value) => <button key={value} type="button" className="segment-button" aria-pressed={selectedPeriod === value} onClick={() => choosePeriod(value)}>{value === 'all' ? 'Todos' : value === 'custom' ? 'Personalizado' : `${value}D`}</button>)}
    </div>
    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
      <FormField id="filter-search" label="Buscar tickets"><input id="filter-search" className="form-input" type="search" placeholder="Referencia, número, título o descripción" value={params.get('search') ?? ''} onChange={(event) => change({ search: event.target.value })} /></FormField>
      <FormField id="filter-status" label="Estado"><select id="filter-status" className="form-input" value={params.get('status') ?? ''} onChange={(event) => change({ status: event.target.value })}><option value="">Todos</option><option value="OPEN">Abierto</option><option value="CLOSED">Cerrado</option></select></FormField>
      <FormField id="filter-customer" label="Cliente"><SearchableSelect id="filter-customer" label="Cliente" value={customerId} options={(catalogs?.customers ?? []).map((item) => ({ value: String(item.id), label: `${item.customer_code} — ${item.name}` }))} onChange={chooseCustomer} disabled={loading || Boolean(catalogError)} placeholder="Todos los clientes" emptyMessage="No hay clientes." noMatchMessage="No se encontraron clientes." /></FormField>
      <FormField id="filter-circuit" label="Circuito"><SearchableSelect id="filter-circuit" label="Circuito" value={circuitId} options={circuits.map((item) => ({ value: String(item.id), label: `${item.circuit_code} — ${item.description}` }))} onChange={chooseCircuit} disabled={circuitLoading || Boolean(circuitError)} placeholder={circuitLoading ? 'Cargando circuitos...' : 'Todos los circuitos'} emptyMessage="No hay circuitos." noMatchMessage="No se encontraron circuitos." /></FormField>
      {named.map(([key, label, items]) => <FormField key={key} id={`filter-${key}`} label={label}><select id={`filter-${key}`} className="form-input" disabled={loading || Boolean(catalogError)} value={params.get(key) ?? ''} onChange={(event) => change({ [key]: event.target.value })}><option value="">Todos</option>{items?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></FormField>)}
      {assignments.map(([key, label, items]) => <FormField key={key} id={`filter-${key}`} label={label}><SearchableSelect id={`filter-${key}`} label={label} value={params.get(key) ?? ''} options={(items ?? []).map((item) => ({ value: String(item.id), label: item.name }))} onChange={(value) => change({ [key]: value })} disabled={loading || Boolean(catalogError)} placeholder="Todos" emptyMessage="No hay registros." noMatchMessage="No hay coincidencias." /></FormField>)}
      <FormField id="filter-from" label="Desde"><input id="filter-from" type="date" className="form-input" value={from} onChange={(event) => changeDate('from', event.target.value)} /></FormField>
      <FormField id="filter-to" label="Hasta"><input id="filter-to" type="date" className="form-input" value={to} onChange={(event) => changeDate('to', event.target.value)} /></FormField>
      <div className="flex items-end"><button type="button" className="button-secondary w-full" onClick={() => { setQuickPeriod({ value: 'all', from: '', to: '' }); clear() }}>Limpiar filtros</button></div>
    </div>
    <FilterChips items={[
      ...(params.get('search') ? [{ label: 'Búsqueda', value: params.get('search')! }] : []),
      ...(params.get('status') ? [{ label: 'Estado', value: params.get('status') === 'OPEN' ? 'Abierto' : params.get('status') === 'CLOSED' ? 'Cerrado' : params.get('status')! }] : []),
      ...(customerId ? [{ label: 'Cliente', value: catalogs?.customers.find((item) => String(item.id) === customerId)?.customer_code ?? `#${customerId}` }] : []),
      ...(circuitId ? [{ label: 'Circuito', value: circuits.find((item) => String(item.id) === circuitId)?.circuit_code ?? `#${circuitId}` }] : []),
      ...[...named, ...assignments].flatMap(([key, label, items]) => params.get(key) ? [{ label, value: items?.find((item) => String(item.id) === params.get(key))?.name ?? `#${params.get(key)}` }] : []),
      ...(['from', 'to'] as const).flatMap((key) => params.get(key) ? [{ label: key === 'from' ? 'Desde' : 'Hasta', value: params.get(key)! }] : []),
    ]} />
    {(catalogError || circuitError) && <RequestState compact error={catalogError || circuitError} errorTitle="" retryText="Reintentar filtros" onRetry={() => setRetry(retry + 1)} className="mt-2" />}
    <p className="mt-2 text-[11px] text-slate-500">Rango sobre Inicio, con días completos en tu zona horaria. Incluye catálogos históricos inactivos.</p>
  </section>
}
