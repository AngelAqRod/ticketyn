import { RequestState } from './RequestState'
import { FeedbackMessage } from './FeedbackMessage'
import { ApiError } from '../api/client'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { Network, SlidersHorizontal, Users, Ticket, Pencil, Power, Trash2 } from 'lucide-react'
import { CatalogDeleteConfirmation } from './CatalogDeleteConfirmation'
import { QuickCatalogCreate } from './QuickCatalogCreate'
import { SearchableSelect } from './SearchableSelect'
import { useUrlFilters } from '../hooks/useUrlFilters'
import { circuitFilterKeys } from '../lib/ticketFilters'
import type { FormEvent } from 'react'
import * as api from '../api'
import type { CatalogKind, Circuit, Customer, NamedCatalog, Position } from '../types/catalog'
import { formatDate, formatTableDate } from '../lib/format'
import { FormField } from './FormField'
import { PageHeading } from './PageHeading'
import { FilterChips } from './FilterChips'

const labels = {
  positions: { title: 'Puestos', singular: 'puesto', empty: 'puestos', description: 'Puestos configurables por departamento, sin jerarquía obligatoria.' },
  'escalation-reasons': { title: 'Motivos de escalamiento', singular: 'motivo de escalamiento', empty: 'motivos', description: 'Solicitudes de apoyo; desactivar conserva el historial.' },
  nodes: { title: "Nodos", singular: "nodo", empty: "nodos", description: "Nodos de distribución asociados a circuitos." },
  responsibles: { title: "Responsables", singular: "responsable", empty: "responsables", description: "Asignados operativos de los tickets." },
  customers: { title: 'Clientes', singular: 'cliente', empty: 'clientes', description: 'Clientes y sus códigos de negocio.' },
  circuits: { title: 'Circuitos', singular: 'circuito', empty: 'circuitos', description: 'Circuitos y servicios contratados por tus clientes.' },
  sectors: { title: 'Sectores', singular: 'sector', empty: 'sectores', description: 'Administra los sectores de esta instalación.' },
  departments: { title: 'Departamentos', singular: 'departamento', empty: 'departamentos', description: 'Administra los departamentos de esta instalación.' },
  'incident-types': { title: 'Tipos de incidencia', singular: 'tipo de incidencia', empty: 'tipos de incidencia', description: 'Administra los tipos de incidencia de esta instalación.' },
}

type CatalogItem = Customer | Circuit | NamedCatalog
interface Draft { id: number | null; code: string; name: string; customerId: string; nodeId: string; active: boolean; detail: string; departmentId: string; positionId: string }
const blank = (): Draft => ({ id: null, code: '', name: '', customerId: '', nodeId: '', active: true, detail: '', departmentId: '', positionId: '' })
const message = (error: unknown) => error instanceof Error ? error.message : 'Ocurrió un error inesperado.'

function list(kind: CatalogKind, signal: AbortSignal, filters?: URLSearchParams): Promise<CatalogItem[]> {
  switch (kind) {
    case 'positions': return api.listPositions(signal, true, filters?.get('department_id') ? Number(filters.get('department_id')) : undefined)
    case 'escalation-reasons': return api.listEscalationReasons(signal, true)
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
    case 'escalation-reasons': { const payload = { ...named, description: draft.detail.trim() || null }; return id === null ? api.createEscalationReason(payload) : api.updateEscalationReason(id, payload) }
    case 'positions': { const payload = { ...named, department_id: Number(draft.departmentId), description: draft.detail.trim() || null }; return id === null ? api.createPosition(payload) : api.updatePosition(id, payload) }
    case 'nodes': return id === null ? api.createNode(named) : api.updateNode(id, named)
    case 'responsibles': { const payload = { ...named, department_id: draft.departmentId ? Number(draft.departmentId) : null, position_id: draft.positionId ? Number(draft.positionId) : null }; return id === null ? api.createResponsible(payload) : api.updateResponsible(id, payload) }
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
    case 'escalation-reasons': return api.updateEscalationReason(id, { active })
    case 'positions': return api.updatePosition(id, { active })
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
  const refreshedModule = kind === 'customers' || kind === 'circuits'
  const RecordIcon = kind === 'circuits' ? Network : Users
  const [items, setItems] = useState<CatalogItem[]>([])
  const [departments, setDepartments] = useState<NamedCatalog[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [departmentFilter, setDepartmentFilter] = useState('')
  const [nodes, setNodes] = useState<NamedCatalog[]>([])
  const [quickNode, setQuickNode] = useState(false)
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [apiInvalidFields, setApiInvalidFields] = useState<string[]>([])
  const [notice, setNotice] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const [localSearch, setLocalSearch] = useState('')
  const { params, change, clear } = useUrlFilters(circuitFilterKeys)
  const filterKey = kind === 'circuits' ? params.toString() : kind === 'positions' ? new URLSearchParams(departmentFilter ? { department_id: departmentFilter } : {}).toString() : ''
  const search = kind === 'circuits' ? params.get('search') ?? '' : localSearch
  const setSearch = (value: string) => kind === 'circuits' ? change({ search: value }) : setLocalSearch(value)
  const customerCache = useRef<Customer[] | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [deleting, setDeleting] = useState<Customer | Circuit | null>(null)
  const [busy, setBusy] = useState(false)
  const sending = useRef(false)
  const newRecordButton = useRef<HTMLButtonElement>(null)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setLoadError(null)
    Promise.all([list(kind, controller.signal, new URLSearchParams(filterKey)), kind === 'circuits' ? (customerCache.current ? Promise.resolve(customerCache.current) : api.listCustomers(controller.signal, true)) : Promise.resolve([]), kind === 'circuits' ? api.listNodes(controller.signal, true) : Promise.resolve([]), kind === 'positions' || kind === 'responsibles' ? api.listDepartments(controller.signal, true) : Promise.resolve([]), kind === 'responsibles' ? api.listPositions(controller.signal, true) : Promise.resolve([])]).then(([rows, clients, nodeRows, departmentRows, positionRows]) => {
      if (!controller.signal.aborted) { setItems(rows); setCustomers(clients); setNodes(nodeRows); setDepartments(departmentRows); setPositions(positionRows); if (kind === 'circuits') customerCache.current = clients; setLoading(false) }
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) { setLoadError(message(failure)); setLoading(false) }
    })
    return () => controller.abort()
  }, [kind, retry, filterKey])

  const customerLabel = (id: number) => {
    const customer = customers.find((item) => item.id === id)
    return customer ? `${customer.customer_code} — ${customer.name}` : 'Cliente no disponible'
  }
  const name = (item: CatalogItem) => 'circuit_code' in item ? item.description : item.name
  const code = (item: CatalogItem) => 'customer_code' in item ? item.customer_code : 'circuit_code' in item ? item.circuit_code : ''
  const visible = items.filter((item) => {
    if (!`${code(item)} ${name(item)}`.toLocaleLowerCase().includes((kind === 'circuits' ? search : search.trim()).toLocaleLowerCase())) return false
    if (kind !== 'circuits') return true
    if (params.get('customer_id') && (!('customer_id' in item) || String(item.customer_id) !== params.get('customer_id'))) return false
    return !params.get('active') || String(item.active) === params.get('active')
  })
  const ordered = [...visible].sort((a, b) => (code(a) || name(a)).localeCompare(code(b) || name(b)) || a.id - b.id)

  function edit(item?: CatalogItem) {
    setError(null); setApiInvalidFields([]); setNotice(null)
    setDraft(item ? { id: item.id, code: code(item), name: name(item), nodeId: 'node_id' in item && item.node_id ? String(item.node_id) : '', customerId: 'customer_id' in item ? String(item.customer_id) : '', active: item.active, departmentId: 'department_id' in item && item.department_id ? String(item.department_id) : '', positionId: 'position_id' in item && item.position_id ? String(item.position_id) : '', detail: (kind === 'positions' || kind === 'escalation-reasons') && 'description' in item ? String(item.description ?? '') : '' } : blank())
  }
  async function persist(operation: () => Promise<CatalogItem>, success: string, closeForm = false) {
    if (sending.current) return
    sending.current = true; setBusy(true); setError(null); setApiInvalidFields([]); setNotice(null)
    try {
      const item = await operation()
      if (mounted.current) {
        setItems((current) => current.some((row) => row.id === item.id) ? current.map((row) => row.id === item.id ? item : row) : [...current, item])
        setNotice(success)
        if (closeForm) setDraft(null)
      }
    } catch (failure) { if (mounted.current) { setError(message(failure)); setApiInvalidFields(failure instanceof ApiError ? failure.fields : []) } }
    finally { sending.current = false; if (mounted.current) setBusy(false) }
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!draft || sending.current) return
    setApiInvalidFields([])
    if (!draft.name.trim() || ((kind === 'customers' || kind === 'circuits') && !draft.code.trim()) || (kind === 'circuits' && !draft.customerId) || (kind === 'positions' && !draft.departmentId)) {
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
    <PageHeading title={info.title} description={info.description} action={<button ref={newRecordButton} type="button" className="button-primary" disabled={busy || loading || Boolean(loadError)} onClick={() => edit()}>Nuevo {info.singular}</button>} />
    {notice && <FeedbackMessage variant="success" className="mb-4">{notice}</FeedbackMessage>}
    {error && <FeedbackMessage id="catalog-form-error" variant="error" className="mb-4">{error}</FeedbackMessage>}
    {draft && <form className={`form-surface mb-4${refreshedModule ? '' : ' border-b border-slate-200'}`} aria-label={`${draft.id === null ? 'Crear' : 'Editar'} ${info.singular}`} onSubmit={submit} noValidate aria-describedby={error ? "catalog-form-error" : undefined}>
      <h2 className={refreshedModule ? 'toolbar-heading gap-3' : 'mb-3 text-sm font-semibold'}>{refreshedModule && <span className="icon-surface" aria-hidden="true"><RecordIcon size={15} /></span>}{draft.id === null ? 'Nuevo' : 'Editar'} {info.singular}</h2>
      <fieldset disabled={busy} className="grid gap-3 sm:grid-cols-2"><legend className="sr-only">Datos del registro</legend>
        {kind === 'circuits' && <FormField describedBy={error ? "catalog-form-error" : undefined} invalid={(error === "Completa los campos obligatorios antes de guardar." && !draft.customerId.trim()) || apiInvalidFields.includes("customer_id")} id="admin-customer" label="Cliente" required><select id="admin-customer" className="form-input" required value={draft.customerId} onChange={(e) => setDraft({ ...draft, customerId: e.target.value })}><option value="">Selecciona un cliente</option>{customers.map((item) => <option key={item.id} value={item.id}>{item.customer_code} — {item.name}{item.active ? '' : ' (Inactivo)'}</option>)}</select></FormField>}
        {kind === 'circuits' && <FormField describedBy={error ? "catalog-form-error" : undefined} invalid={apiInvalidFields.includes("node_id")} id="admin-node" label="Nodo de distribución"><div className="flex gap-2"><div className="min-w-0 flex-1"><SearchableSelect id="admin-node" label="Nodo de distribución" value={draft.nodeId} onChange={(value) => setDraft({ ...draft, nodeId: value })} options={nodes.filter((item) => item.active || String(item.id) === draft.nodeId).map((item) => ({ value: String(item.id), label: item.name, disabled: !item.active }))} placeholder="Sin asignar" emptyMessage="No hay nodos activos." noMatchMessage="No se encontraron nodos." /></div><button type="button" className="button-secondary" aria-label="Nuevo nodo" title="Nuevo nodo" onClick={() => setQuickNode(true)}>+</button></div></FormField>}
        {(kind === 'customers' || kind === 'circuits') && <FormField describedBy={error ? "catalog-form-error" : undefined} invalid={(error === "Completa los campos obligatorios antes de guardar." && !draft.code.trim()) || apiInvalidFields.includes(kind === "circuits" ? "circuit_code" : "customer_code")} id="admin-code" label={kind === 'customers' ? 'Código de cliente' : 'Código de circuito'} required><input id="admin-code" className="form-input" required value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value })} /></FormField>}
        <FormField describedBy={error ? "catalog-form-error" : undefined} invalid={(error === "Completa los campos obligatorios antes de guardar." && !draft.name.trim()) || apiInvalidFields.includes(kind === "circuits" ? "description" : "name")} id="admin-name" label={kind === 'circuits' ? 'Descripción' : 'Nombre'} required><input id="admin-name" className="form-input" required value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></FormField>
        {(kind === 'responsibles' || kind === 'positions') && <FormField id="admin-department" label="Departamento" describedBy={error ? "catalog-form-error" : undefined} invalid={apiInvalidFields.includes("department_id") || (kind === 'positions' && Boolean(error) && !draft.departmentId)} required={kind === 'positions'}><SearchableSelect id="admin-department" label="Departamento" required={kind === 'positions'} value={draft.departmentId} onChange={(value) => setDraft({ ...draft, departmentId: value, positionId: '' })} options={departments.filter((item) => item.active || String(item.id) === draft.departmentId).map((item) => ({ value: String(item.id), label: item.name, disabled: !item.active }))} placeholder={kind === 'positions' ? 'Selecciona un departamento' : 'Sin asignar'} emptyMessage="No hay departamentos activos." noMatchMessage="Sin coincidencias." /></FormField>}
        {kind === 'responsibles' && <FormField id="admin-position" label="Puesto" describedBy={error ? "catalog-form-error" : undefined} invalid={apiInvalidFields.includes("position_id")}><SearchableSelect id="admin-position" label="Puesto" value={draft.positionId} disabled={!draft.departmentId} onChange={(value) => setDraft({ ...draft, positionId: value })} options={positions.filter((item) => String(item.department_id) === draft.departmentId && (item.active || String(item.id) === draft.positionId)).map((item) => ({ value: String(item.id), label: item.name, disabled: !item.active }))} placeholder="Sin asignar" emptyMessage="No hay puestos activos en este departamento." noMatchMessage="Sin coincidencias." /></FormField>}
        {kind === 'responsibles' && draft.id !== null && (() => { const item = items.find((row) => row.id === draft.id); return item && 'attention_level' in item && item.attention_level ? <p className="text-xs text-muted sm:col-span-2">Dato anterior conservado (solo lectura): {String(item.attention_level)}</p> : null })()}
        {(kind === 'positions' || kind === 'escalation-reasons') && <FormField id="admin-detail" label="Descripción (opcional)"><input id="admin-detail" className="form-input" maxLength={10000} value={draft.detail} onChange={(event) => setDraft({ ...draft, detail: event.target.value })} /></FormField>}
        <div className="flex items-center gap-2 self-end pb-3"><input aria-describedby={error ? "catalog-form-error" : undefined} aria-invalid={apiInvalidFields.includes("active") || undefined} id="admin-active" type="checkbox" checked={draft.active} onChange={(e) => setDraft({ ...draft, active: e.target.checked })} /><label htmlFor="admin-active" className="text-sm">Activo</label></div>
      </fieldset>
      <p className="mt-3 text-xs text-slate-500">Desactivar conserva el registro y sus referencias históricas.</p>
      <div className="mt-4 flex justify-end gap-3"><button type="button" className="button-secondary" disabled={busy} onClick={() => { setDraft(null); setError(null); setApiInvalidFields([]) }}>Cancelar</button><button type="submit" className="button-primary" disabled={busy}>{busy ? (draft.id === null ? 'Creando...' : 'Guardando...') : 'Guardar'}</button></div>
    </form>}
    {kind === 'positions' && <div className="mb-3 max-w-md"><FormField id="position-department-filter" label="Filtrar por departamento"><SearchableSelect id="position-department-filter" label="Filtrar por departamento" value={departmentFilter} onChange={setDepartmentFilter} options={departments.map((item) => ({ value: String(item.id), label: item.name }))} placeholder="Todos los departamentos" emptyMessage="No hay departamentos." noMatchMessage="Sin coincidencias." /></FormField></div>}
    {kind === 'circuits' && <section aria-label="Filtros de circuitos" className="filter-toolbar grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
      <p className="toolbar-heading gap-3 sm:col-span-2 xl:col-span-4"><span className="icon-surface" aria-hidden="true"><SlidersHorizontal size={15} /></span>Filtros de circuitos</p>
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
    {(kind === 'customers' || kind === 'nodes' || kind === 'responsibles' || kind === 'positions') && <div className={kind === 'customers' ? 'filter-toolbar' : 'mb-3 max-w-md'}>
      {kind === 'customers' && <p className="toolbar-heading gap-3"><span className="icon-surface" aria-hidden="true"><SlidersHorizontal size={15} /></span>Filtros de clientes</p>}
      <div className="max-w-md"><label htmlFor="admin-search" className={kind === 'customers' ? 'form-label' : 'mb-1 block text-xs font-medium'}>Buscar {info.empty}</label><input id="admin-search" type="search" className="form-input" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
    </div>}
    {loading || loadError || !ordered.length ? <RequestState loading={loading} loadingText={`Cargando ${info.empty}...`} error={loadError ? `Error al cargar ${info.empty}: ${loadError}` : null} errorTitle="" onRetry={() => setRetry(retry + 1)} empty={!ordered.length} emptyTitle={items.length || (kind === 'circuits' && circuitFilterKeys.some((key) => params.has(key))) ? 'No hay coincidencias con la búsqueda.' : `No hay ${info.empty} registrados.`} emptyDescription="" compact={!refreshedModule && loading} /> : <div className="panel table-surface overflow-x-auto"><table className="operation-table min-w-[650px]"><caption className="sr-only">{info.title}</caption>
      <thead><tr>{[...(kind === 'customers' || kind === 'circuits' ? ['Código'] : []), ...(kind === 'circuits' ? ['Cliente', 'Nodo'] : []), kind === 'circuits' ? 'Descripción' : 'Nombre', ...(kind === 'positions' || kind === 'responsibles' ? ['Departamento'] : []), ...(kind === 'responsibles' ? ['Puesto'] : []), 'Estado', 'Fecha de creación', 'Acciones'].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
      <tbody>{ordered.map((item) => <tr key={item.id}>
        {(kind === 'customers' || kind === 'circuits') && <th scope="row" className="record-code text-slate-900">{code(item)}</th>}
        {kind === 'circuits' && 'customer_id' in item && <td>{customerLabel(item.customer_id)}</td>}
        {kind === 'circuits' && 'circuit_code' in item && <td>{item.node?.name ?? 'Sin asignar'}</td>}
        <td>{name(item)}</td>{(kind === 'positions' || kind === 'responsibles') && <td>{'department' in item && item.department ? (item.department as NamedCatalog).name : 'Sin asignar'}</td>}{kind === 'responsibles' && <td>{'position' in item && item.position ? (item.position as NamedCatalog).name : 'Sin asignar'}</td>}<td><span className={`status-badge ${item.active ? 'status-active' : 'status-neutral'}`}>{item.active ? 'Activo' : 'Inactivo'}</span></td>
        <td className="whitespace-nowrap text-xs tabular-nums text-slate-600"><time dateTime={item.created_at} title={formatDate(item.created_at)}>{formatTableDate(item.created_at)}</time></td><td><div className="table-actions">
          {kind === 'customers' && <><Link className="button-ghost table-action" to={`/circuits?customer_id=${item.id}`} aria-label={`Ver circuitos de ${code(item)}`}><Network size={14} aria-hidden="true" />Circuitos</Link><Link className="button-ghost table-action" to={`/tickets?customer_id=${item.id}`} aria-label={`Ver tickets de ${code(item)}`}><Ticket size={14} aria-hidden="true" />Tickets</Link></>}
          {kind === 'circuits' && <Link className="button-ghost table-action" to={`/tickets?circuit_id=${item.id}`} aria-label={`Ver tickets de ${code(item)}`}><Ticket size={14} aria-hidden="true" />Ver tickets</Link>}
          <button type="button" className="button-secondary table-action" disabled={busy || Boolean(draft)} onClick={() => edit(item)} aria-label={`Editar ${code(item) || name(item)}`}><Pencil size={14} aria-hidden="true" />Editar</button><button type="button" className={`${item.active ? 'button-danger' : 'button-secondary'} table-action`} disabled={busy || Boolean(draft)} onClick={() => toggle(item)} aria-label={`${item.active ? 'Desactivar' : 'Activar'} ${code(item) || name(item)}`}><Power size={14} aria-hidden="true" />{item.active ? 'Desactivar' : 'Activar'}</button>
          {('customer_code' in item || 'circuit_code' in item) && <button type="button" className="button-danger table-action" disabled={busy || Boolean(draft)} aria-label={`Eliminar ${code(item)}`} onClick={() => { setError(null); setNotice(null); setDeleting(item) }}><Trash2 size={14} aria-hidden="true" />Eliminar</button>}</div></td>
      </tr>)}</tbody></table></div>}
    {deleting && <CatalogDeleteConfirmation item={deleting} fallbackFocus={newRecordButton} onCancel={() => setDeleting(null)} onBusyChange={setBusy} onDeleted={() => {
      setItems((current) => current.filter((row) => row.id !== deleting.id))
      setBusy(false)
      setNotice('Registro eliminado correctamente.')
      setDeleting(null)
    }} />}
    {quickNode && draft && <QuickCatalogCreate kind="node" onCancel={() => setQuickNode(false)} onCreated={(node) => { setNodes((current) => [...current, node]); setDraft({ ...draft, nodeId: String(node.id) }); setQuickNode(false) }} />}
  </>
}
