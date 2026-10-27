import { PeriodShortcuts } from './PeriodShortcuts'
import { RequestState } from './RequestState'
import { useEffect, useState } from 'react'
import { listCircuits, listCustomers, listDepartments, listIncidentTypes, listSectors, listNodes, listResponsibles } from '../api'
import type { Circuit, Customer, NamedCatalog } from '../types/catalog'
import { SearchableSelect } from './SearchableSelect'
import { FormField } from './FormField'
import { FilterBar, FilterPanelGroup } from './FilterBar'
import { TicketQuickFilters } from './TicketQuickFilters'
import { reportPeriod } from '../lib/reportPeriod'
import { ageBucketLabel } from '../lib/ticketAge'

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
  const catalogName = (key: string, items?: NamedCatalog[]) => items?.find((item) => String(item.id) === params.get(key))?.name ?? `#${params.get(key)}`
  // Cada chip quita solo su condición; Estado también apaga las que solo existen en abiertos.
  const activeChips = [
    ...(params.get('search') ? [{ label: 'Búsqueda', value: params.get('search')!, onRemove: () => change({ search: '' }) }] : []),
    ...(params.get('status') ? [{ label: 'Estado', value: params.get('status') === 'OPEN' ? 'Abierto' : params.get('status') === 'CLOSED' ? 'Cerrado' : params.get('status')!, onRemove: () => change({ status: '', unassigned: '', age_bucket: '' }) }] : []),
    ...(params.get('age_bucket') ? [{ label: 'Antigüedad', value: ageBucketLabel(params.get('age_bucket')!) ?? params.get('age_bucket')!, onRemove: () => change({ age_bucket: '' }) }] : []),
    ...(params.get('unassigned') === 'true' ? [{ label: 'Responsable', value: 'Sin responsable', onRemove: () => change({ unassigned: '' }) }] : []),
    ...(customerId ? [{ label: 'Cliente', value: catalogs?.customers.find((item) => String(item.id) === customerId)?.customer_code ?? `#${customerId}`, onRemove: () => change({ customer_id: '' }) }] : []),
    ...(circuitId ? [{ label: 'Circuito', value: circuits.find((item) => String(item.id) === circuitId)?.circuit_code ?? `#${circuitId}`, onRemove: () => change({ circuit_id: '' }) }] : []),
    ...[...named, ...assignments].flatMap(([key, label, items]) => params.get(key) ? [{ label: key === 'responsible_id' && params.get('unassigned') === 'true' ? 'Responsable asignado' : label, value: catalogName(key, items), onRemove: () => change({ [key]: '' }) }] : []),
    ...(['from', 'to'] as const).flatMap((key) => params.get(key) ? [{ label: key === 'from' ? 'Desde' : 'Hasta', value: params.get(key)!, onRemove: () => { setQuickPeriod({ value: 'custom', from: key === 'from' ? '' : from, to: key === 'to' ? '' : to }); change({ [key]: '' }) } }] : []),
  ]
  // «Filtros (n)» cuenta solo los avanzados activos, calculados del estado de la URL.
  const advancedKeys = ['sector_id', 'department_id', 'incident_type_id', 'node_id', 'responsible_id', 'from', 'to']
  const advancedCount = advancedKeys.filter((key) => params.get(key)).length
  const disabled = loading || Boolean(catalogError)

  return <>
    <FilterBar
      label="Filtros de tickets"
      theme="blue"
      chips={activeChips}
      panelCount={advancedCount}
      onClear={() => { setQuickPeriod({ value: 'all', from: '', to: '' }); clear() }}
      search={<FormField id="filter-search" label="Buscar tickets"><input id="filter-search" className="form-input" type="search" placeholder="Referencia, número, título o descripción" value={params.get('search') ?? ''} onChange={(event) => change({ search: event.target.value })} /></FormField>}
      quick={<>
        <div className="filter-bar-quick"><FormField id="filter-customer" label="Cliente"><SearchableSelect id="filter-customer" label="Cliente" value={customerId} options={(catalogs?.customers ?? []).map((item) => ({ value: String(item.id), label: `${item.customer_code} — ${item.name}` }))} onChange={chooseCustomer} disabled={disabled} placeholder="Todos los clientes" emptyMessage="No hay clientes." noMatchMessage="No se encontraron clientes." /></FormField></div>
        <div className="filter-bar-quick"><FormField id="filter-circuit" label="Circuito"><SearchableSelect id="filter-circuit" label="Circuito" value={circuitId} options={circuits.map((item) => ({ value: String(item.id), label: `${item.circuit_code} — ${item.description}` }))} onChange={chooseCircuit} disabled={circuitLoading || Boolean(circuitError)} placeholder={circuitLoading ? 'Cargando circuitos...' : 'Todos los circuitos'} emptyMessage="No hay circuitos." noMatchMessage="No se encontraron circuitos." /></FormField></div>
      </>}
      primary={<>
        <TicketQuickFilters params={params} change={change} />
        <PeriodShortcuts label="Período de tickets" value={selectedPeriod} onChange={choosePeriod} includeAll />
      </>}
      panel={<>
        <FilterPanelGroup title="Clasificación">
          {named.map(([key, label, items]) => <FormField key={key} id={`filter-${key}`} label={label}><select id={`filter-${key}`} className="form-input" disabled={disabled} value={params.get(key) ?? ''} onChange={(event) => change({ [key]: event.target.value })}><option value="">Todos</option>{items?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></FormField>)}
        </FilterPanelGroup>
        <FilterPanelGroup title="Asignación">
          {assignments.map(([key, label, items]) => <FormField key={key} id={`filter-${key}`} label={label}><SearchableSelect id={`filter-${key}`} label={label} value={params.get(key) ?? ''} options={(items ?? []).map((item) => ({ value: String(item.id), label: item.name }))} onChange={(value) => change({ [key]: value, ...(key === 'responsible_id' && value ? { unassigned: '' } : {}) })} disabled={disabled} placeholder="Todos" emptyMessage="No hay registros." noMatchMessage="No hay coincidencias." /></FormField>)}
        </FilterPanelGroup>
        <FilterPanelGroup title="Fechas">
          <FormField id="filter-from" label="Desde"><input id="filter-from" type="date" className="form-input" value={from} onChange={(event) => changeDate('from', event.target.value)} /></FormField>
          <FormField id="filter-to" label="Hasta"><input id="filter-to" type="date" className="form-input" value={to} onChange={(event) => changeDate('to', event.target.value)} /></FormField>
          <p className="text-sm text-slate-400">Rango sobre Inicio, con días completos en tu zona horaria. Incluye catálogos históricos inactivos.</p>
        </FilterPanelGroup>
      </>}
    />
    {(catalogError || circuitError) && <RequestState compact error={catalogError || circuitError} errorTitle="" retryText="Reintentar filtros" onRetry={() => setRetry(retry + 1)} className="-mt-2 mb-4" />}
  </>
}
