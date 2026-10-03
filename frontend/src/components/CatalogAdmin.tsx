import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { QuickCatalogCreate } from './QuickCatalogCreate'
import { SearchableSelect } from './SearchableSelect'
import { useUrlFilters } from '../hooks/useUrlFilters'
import { circuitFilterKeys } from '../lib/ticketFilters'
import type { FormEvent } from 'react'
import * as api from '../api'
import type { CatalogKind, Circuit, Customer, NamedCatalog } from '../types/catalog'
import { formatDate, formatTableDate } from '../lib/format'
import { FormField } from './FormField'
import { PageHeading } from './PageHeading'
import { FilterChips } from './FilterChips'

const labels = {
  nodes: { title: "Nodos", singular: "nodo", empty: "nodos", description: "Nodos de distribución asociados a circuitos." },
  responsibles: { title: "Responsables", singular: "responsable", empty: "responsables", description: "Asignados operativos de los tickets." },
  customers: { title: 'Clientes', singular: 'cliente', empty: 'clientes', description: 'Clientes y sus códigos de negocio.' },
  circuits: { title: 'Circuitos', singular: 'circuito', empty: 'circuitos', description: 'Circuitos y servicios contratados por tus clientes.' },
  sectors: { title: 'Sectores', singular: 'sector', empty: 'sectores', description: 'Administra los sectores de esta instalación.' },
  departments: { title: 'Departamentos', singular: 'departamento', empty: 'departamentos', description: 'Administra los departamentos de esta instalación.' },
  'incident-types': { title: 'Tipos de incidencia', singular: 'tipo de incidencia', empty: 'tipos de incidencia', description: 'Administra los tipos de incidencia de esta instalación.' },
}

type CatalogItem = Customer | Circuit | NamedCatalog
interface Draft { id: number | null; code: string; name: string; customerId: string; nodeId: string; active: boolean }
const blank = (): Draft => ({ id: null, code: '', name: '', customerId: '', nodeId: '', active: true })
const message = (error: unknown) => error instanceof Error ? error.message : 'Ocurrió un error inesperado.'

function list(kind: CatalogKind, signal: AbortSignal, filters?: URLSearchParams): Promise<CatalogItem[]> {
  switch (kind) {
    case 'nodes': return api.listNodes(signal, true)
    case 'responsibles': return api.listResponsibles(signal, true)
    case 'customers': return api.listCustomers(signal, true)
    case 'circuits': return api.listCircuits(filters?.get('customer_id') ? Number(filters.get('customer_id')) : undefined, signal, true, { search: filters?.get('search') || undefined, node_id: filters?.get('node_id') ? Number(filters.get('node_id')) : undefined, active: filters?.get('active') === 'true' ? true : filters?.get('active') === 'false' ? false : undefined })
    case 'sectors': return api.listSectors(signal, true)
    case 'departments': return api.listDepartments(signal, true)
    case 'incident-types': return api.listIncidentTypes(signal, true)
  }
}

function save(kind: CatalogKind, draft: Draft): Promise<CatalogItem> {
  const id = draft.id
  const named = { name: draft.name.trim(), active: draft.active }
  switch (kind) {
    case 'nodes': return id === null ? api.createNode(named) : api.updateNode(id, named)
    case 'responsibles': return id === null ? api.createResponsible(named) : api.updateResponsible(id, named)
    case 'customers': {
      const payload = { ...named, customer_code: draft.code.trim() }
      return id === null ? api.createCustomer(payload) : api.updateCustomer(id, payload)
    }
    case 'circuits': {
      const payload = { description: draft.name.trim(), circuit_code: draft.code.trim(), node_id: draft.nodeId ? Number(draft.nodeId) : null, customer_id: Number(draft.customerId), active: draft.active }
      return id === null ? api.createCircuit(payload) : api.updateCircuit(id, payload)
    }
    case 'sectors': return id === null ? api.createSector(named) : api.updateSector(id, named)
    case 'departments': return id === null ? api.createDepartment(named) : api.updateDepartment(id, named)
    case 'incident-types': return id === null ? api.createIncidentType(named) : api.updateIncidentType(id, named)
  }
}

function changeActive(kind: CatalogKind, id: number, active: boolean): Promise<CatalogItem> {
  switch (kind) {
    case 'nodes': return api.updateNode(id, { active })
    case 'responsibles': return api.updateResponsible(id, { active })
    case 'customers': return api.updateCustomer(id, { active })
    case 'circuits': return api.updateCircuit(id, { active })
    case 'sectors': return api.updateSector(id, { active })
    case 'departments': return api.updateDepartment(id, { active })
    case 'incident-types': return api.updateIncidentType(id, { active })
  }
}

function confirmDeactivation(): boolean {
  return window.confirm('¿Desactivar este registro? Dejará de aparecer en selectores operativos nuevos. Los tickets históricos seguirán conservando la referencia. El registro no se eliminará.')
}

export function CatalogAdmin({ kind }: { kind: CatalogKind }) {
  const info = labels[kind]
  const [items, setItems] = useState<CatalogItem[]>([])
  const [nodes, setNodes] = useState<NamedCatalog[]>([])
  const [quickNode, setQuickNode] = useState(false)
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const [localSearch, setLocalSearch] = useState('')
  const { params, change, clear } = useUrlFilters(circuitFilterKeys)
  const filterKey = kind === 'circuits' ? params.toString() : ''
  const search = kind === 'circuits' ? params.get('search') ?? '' : localSearch
  const setSearch = (value: string) => kind === 'circuits' ? change({ search: value }) : setLocalSearch(value)
  const customerCache = useRef<Customer[] | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [busy, setBusy] = useState(false)
  const sending = useRef(false)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setLoadError(null)
    Promise.all([list(kind, controller.signal, new URLSearchParams(filterKey)), kind === 'circuits' ? (customerCache.current ? Promise.resolve(customerCache.current) : api.listCustomers(controller.signal, true)) : Promise.resolve([]), kind === 'circuits' ? api.listNodes(controller.signal, true) : Promise.resolve([])]).then(([rows, clients, nodeRows]) => {
      if (!controller.signal.aborted) { setItems(rows); setCustomers(clients); setNodes(nodeRows); if (kind === 'circuits') customerCache.current = clients; setLoading(false) }
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) { setLoadError(message(failure)); setLoading(false) }
    })
    return () => controller.abort()
  }, [kind, retry, filterKey])

  const customerLabel = (id: number) => {
    const customer = customers.find((item) => item.id === id)
    return customer ? `${customer.customer_code} — ${customer.name}` : 'Cliente no disponible'
  }
  const name = (item: CatalogItem) => 'description' in item ? item.description : item.name
  const code = (item: CatalogItem) => 'customer_code' in item ? item.customer_code : 'circuit_code' in item ? item.circuit_code : ''
  const visible = items.filter((item) => {
    if (!`${code(item)} ${name(item)}`.toLocaleLowerCase().includes((kind === 'circuits' ? search : search.trim()).toLocaleLowerCase())) return false
    if (kind !== 'circuits') return true
    if (params.get('customer_id') && (!('customer_id' in item) || String(item.customer_id) !== params.get('customer_id'))) return false
    return !params.get('active') || String(item.active) === params.get('active')
  })
  const ordered = [...visible].sort((a, b) => (code(a) || name(a)).localeCompare(code(b) || name(b)) || a.id - b.id)

  function edit(item?: CatalogItem) {
    setError(null); setNotice(null)
    setDraft(item ? { id: item.id, code: code(item), name: name(item), nodeId: 'node_id' in item && item.node_id ? String(item.node_id) : '', customerId: 'customer_id' in item ? String(item.customer_id) : '', active: item.active } : blank())
  }
  async function persist(operation: () => Promise<CatalogItem>, success: string, closeForm = false) {
    if (sending.current) return
    sending.current = true; setBusy(true); setError(null); setNotice(null)
    try {
      const item = await operation()
      if (mounted.current) {
        setItems((current) => current.some((row) => row.id === item.id) ? current.map((row) => row.id === item.id ? item : row) : [...current, item])
        setNotice(success)
        if (closeForm) setDraft(null)
      }
    } catch (failure) { if (mounted.current) setError(message(failure)) }
    finally { sending.current = false; if (mounted.current) setBusy(false) }
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!draft || sending.current) return
    if (!draft.name.trim() || ((kind === 'customers' || kind === 'circuits') && !draft.code.trim()) || (kind === 'circuits' && !draft.customerId)) {
      setError('Completa los campos obligatorios antes de guardar.'); return
    }
    if (!draft.active && (draft.id === null || items.find((item) => item.id === draft.id)?.active) && !confirmDeactivation()) return
    void persist(() => save(kind, draft), draft.id === null ? 'Registro creado correctamente.' : 'Cambios guardados correctamente.', true)
  }
  function toggle(item: CatalogItem) {
    if (sending.current || (item.active && !confirmDeactivation())) return
    void persist(() => changeActive(kind, item.id, !item.active), item.active ? 'Registro desactivado. Los tickets históricos conservan su referencia.' : 'Registro activado correctamente.')
  }

  return <>
    <PageHeading title={info.title} description={info.description} action={<button type="button" className="button-primary" disabled={busy || loading || Boolean(loadError)} onClick={() => edit()}>Nuevo {info.singular}</button>} />
    {notice && <p role="status" className="mb-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900">{notice}</p>}
    {error && <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>}
    {draft && <form className="form-surface mb-4 border-b border-slate-200" aria-label={`${draft.id === null ? 'Crear' : 'Editar'} ${info.singular}`} onSubmit={submit} noValidate>
      <h2 className="mb-3 text-sm font-semibold">{draft.id === null ? 'Nuevo' : 'Editar'} {info.singular}</h2>
      <fieldset disabled={busy} className="grid gap-3 sm:grid-cols-2"><legend className="sr-only">Datos del registro</legend>
        {kind === 'circuits' && <FormField id="admin-customer" label="Cliente" required><select id="admin-customer" className="form-input" required value={draft.customerId} onChange={(e) => setDraft({ ...draft, customerId: e.target.value })}><option value="">Selecciona un cliente</option>{customers.map((item) => <option key={item.id} value={item.id}>{item.customer_code} — {item.name}{item.active ? '' : ' (Inactivo)'}</option>)}</select></FormField>}
        {kind === 'circuits' && <FormField id="admin-node" label="Nodo de distribución"><div className="flex gap-2"><div className="min-w-0 flex-1"><SearchableSelect id="admin-node" label="Nodo de distribución" value={draft.nodeId} onChange={(value) => setDraft({ ...draft, nodeId: value })} options={nodes.filter((item) => item.active || String(item.id) === draft.nodeId).map((item) => ({ value: String(item.id), label: item.name, disabled: !item.active }))} placeholder="Sin asignar" emptyMessage="No hay nodos activos." noMatchMessage="No se encontraron nodos." /></div><button type="button" className="button-secondary" aria-label="Nuevo nodo" title="Nuevo nodo" onClick={() => setQuickNode(true)}>+</button></div></FormField>}
        {(kind === 'customers' || kind === 'circuits') && <FormField id="admin-code" label={kind === 'customers' ? 'Código de cliente' : 'Código de circuito'} required><input id="admin-code" className="form-input" required value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value })} /></FormField>}
        <FormField id="admin-name" label={kind === 'circuits' ? 'Descripción' : 'Nombre'} required><input id="admin-name" className="form-input" required value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></FormField>
        <div className="flex items-center gap-2 self-end pb-3"><input id="admin-active" type="checkbox" checked={draft.active} onChange={(e) => setDraft({ ...draft, active: e.target.checked })} /><label htmlFor="admin-active" className="text-sm">Activo</label></div>
      </fieldset>
      <p className="mt-3 text-xs text-slate-500">Desactivar conserva el registro y sus referencias históricas.</p>
      <div className="mt-4 flex justify-end gap-3"><button type="button" className="button-secondary" disabled={busy} onClick={() => { setDraft(null); setError(null) }}>Cancelar</button><button type="submit" className="button-primary" disabled={busy}>{busy ? (draft.id === null ? 'Creando...' : 'Guardando...') : 'Guardar'}</button></div>
    </form>}
    {kind === 'circuits' && <section aria-label="Filtros de circuitos" className="filter-toolbar grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
      <FormField id="circuit-search" label="Buscar circuitos"><input id="circuit-search" className="form-input" type="search" placeholder="Código o descripción" value={search} onChange={(event) => setSearch(event.target.value)} /></FormField>
      <FormField id="circuit-customer-filter" label="Filtrar por cliente"><SearchableSelect id="circuit-customer-filter" label="Cliente" value={params.get('customer_id') ?? ''} options={customers.map((item) => ({ value: String(item.id), label: `${item.customer_code} — ${item.name}` }))} onChange={(value) => change({ customer_id: value })} disabled={loading && !customers.length} placeholder="Todos los clientes" emptyMessage="No hay clientes." noMatchMessage="No se encontraron clientes." /></FormField>
      <FormField id="circuit-node-filter" label="Filtrar por nodo"><SearchableSelect id="circuit-node-filter" label="Nodo" value={params.get('node_id') ?? ''} options={nodes.map((item) => ({ value: String(item.id), label: item.name }))} onChange={(value) => change({ node_id: value })} placeholder="Todos los nodos" emptyMessage="No hay nodos." noMatchMessage="No se encontraron nodos." /></FormField>
      <FormField id="circuit-active-filter" label="Estado de circuitos"><select id="circuit-active-filter" className="form-input" value={params.get('active') ?? ''} onChange={(event) => change({ active: event.target.value })}><option value="">Todos</option><option value="true">Activos</option><option value="false">Inactivos</option></select></FormField>
      <div className="flex items-end"><button type="button" className="button-secondary w-full" onClick={clear}>Limpiar filtros</button></div>
    </section>}
    {kind === 'circuits' && <FilterChips items={[
      ...(params.get('search') ? [{ label: 'Búsqueda', value: params.get('search')! }] : []),
      ...(params.get('customer_id') ? [{ label: 'Cliente', value: customerLabel(Number(params.get('customer_id'))) }] : []),
      ...(params.get('node_id') ? [{ label: 'Nodo', value: nodes.find((item) => String(item.id) === params.get('node_id'))?.name ?? `#${params.get('node_id')}` }] : []),
      ...(params.get('active') ? [{ label: 'Estado', value: params.get('active') === 'true' ? 'Activos' : params.get('active') === 'false' ? 'Inactivos' : params.get('active')! }] : []),
    ]} />}
    {(kind === 'customers' || kind === 'nodes' || kind === 'responsibles') && <div className="mb-3 max-w-md"><label htmlFor="admin-search" className="mb-1 block text-xs font-medium">Buscar {info.empty}</label><input id="admin-search" type="search" className="form-input" value={search} onChange={(e) => setSearch(e.target.value)} /></div>}
    {loading ? <p role="status">Cargando {info.empty}...</p> : loadError ? <div role="alert" className="panel p-5"><p>Error al cargar {info.empty}: {loadError}</p><button type="button" className="button-secondary mt-3" onClick={() => setRetry(retry + 1)}>Reintentar</button></div> : !ordered.length ? <p className="panel p-6">{items.length || (kind === 'circuits' && circuitFilterKeys.some((key) => params.has(key))) ? 'No hay coincidencias con la búsqueda.' : `No hay ${info.empty} registrados.`}</p> : <div className="panel overflow-x-auto"><table className="operation-table min-w-[650px]"><caption className="sr-only">{info.title}</caption>
      <thead><tr>{[...(kind === 'customers' || kind === 'circuits' ? ['Código'] : []), ...(kind === 'circuits' ? ['Cliente', 'Nodo'] : []), kind === 'circuits' ? 'Descripción' : 'Nombre', 'Estado', 'Fecha de creación', 'Acciones'].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
      <tbody>{ordered.map((item) => <tr key={item.id}>
        {(kind === 'customers' || kind === 'circuits') && <th scope="row" className="record-code text-slate-900">{code(item)}</th>}
        {kind === 'circuits' && 'customer_id' in item && <td>{customerLabel(item.customer_id)}</td>}
        {kind === 'circuits' && 'circuit_code' in item && <td>{item.node?.name ?? 'Sin asignar'}</td>}
        <td>{name(item)}</td><td><span className={`status-badge ${item.active ? 'status-active' : 'status-neutral'}`}>{item.active ? 'Activo' : 'Inactivo'}</span></td>
        <td className="whitespace-nowrap text-xs tabular-nums text-slate-600"><time dateTime={item.created_at} title={formatDate(item.created_at)}>{formatTableDate(item.created_at)}</time></td><td><div className="flex flex-wrap items-center gap-2">
          {kind === 'customers' && <><Link className="text-xs text-primary underline" to={`/circuits?customer_id=${item.id}`} aria-label={`Ver circuitos de ${code(item)}`}>Circuitos</Link><Link className="text-xs text-primary underline" to={`/tickets?customer_id=${item.id}`} aria-label={`Ver tickets de ${code(item)}`}>Tickets</Link></>}
          {kind === 'circuits' && <Link className="text-xs text-primary underline" to={`/tickets?circuit_id=${item.id}`} aria-label={`Ver tickets de ${code(item)}`}>Ver tickets</Link>}
          <button type="button" className="button-secondary" disabled={busy || Boolean(draft)} onClick={() => edit(item)} aria-label={`Editar ${code(item) || name(item)}`}>Editar</button><button type="button" className={item.active ? 'button-danger' : 'button-secondary'} disabled={busy || Boolean(draft)} onClick={() => toggle(item)} aria-label={`${item.active ? 'Desactivar' : 'Activar'} ${code(item) || name(item)}`}>{item.active ? 'Desactivar' : 'Activar'}</button></div></td>
      </tr>)}</tbody></table></div>}
    {quickNode && draft && <QuickCatalogCreate kind="node" onCancel={() => setQuickNode(false)} onCreated={(node) => { setNodes((current) => [...current, node]); setDraft({ ...draft, nodeId: String(node.id) }); setQuickNode(false) }} />}
  </>
}
