import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import * as api from '../api'
import type { CatalogKind, Circuit, Customer, NamedCatalog } from '../types/catalog'
import { formatDate } from '../lib/format'
import { FormField } from './FormField'
import { PageHeading } from './PageHeading'

const labels = {
  customers: { title: 'Clientes', singular: 'cliente', empty: 'clientes', description: 'Clientes y sus códigos de negocio.' },
  circuits: { title: 'Circuitos', singular: 'circuito', empty: 'circuitos', description: 'Circuitos y servicios contratados por tus clientes.' },
  sectors: { title: 'Sectores', singular: 'sector', empty: 'sectores', description: 'Administra los sectores de esta instalación.' },
  departments: { title: 'Departamentos', singular: 'departamento', empty: 'departamentos', description: 'Administra los departamentos de esta instalación.' },
  'incident-types': { title: 'Tipos de incidencia', singular: 'tipo de incidencia', empty: 'tipos de incidencia', description: 'Administra los tipos de incidencia de esta instalación.' },
}

type CatalogItem = Customer | Circuit | NamedCatalog
interface Draft { id: number | null; code: string; name: string; customerId: string; active: boolean }
const blank = (): Draft => ({ id: null, code: '', name: '', customerId: '', active: true })
const message = (error: unknown) => error instanceof Error ? error.message : 'Ocurrió un error inesperado.'

function list(kind: CatalogKind, signal: AbortSignal): Promise<CatalogItem[]> {
  switch (kind) {
    case 'customers': return api.listCustomers(signal, true)
    case 'circuits': return api.listCircuits(undefined, signal, true)
    case 'sectors': return api.listSectors(signal, true)
    case 'departments': return api.listDepartments(signal, true)
    case 'incident-types': return api.listIncidentTypes(signal, true)
  }
}

function save(kind: CatalogKind, draft: Draft): Promise<CatalogItem> {
  const id = draft.id
  const named = { name: draft.name.trim(), active: draft.active }
  switch (kind) {
    case 'customers': {
      const payload = { ...named, customer_code: draft.code.trim() }
      return id === null ? api.createCustomer(payload) : api.updateCustomer(id, payload)
    }
    case 'circuits': {
      const payload = { description: draft.name.trim(), circuit_code: draft.code.trim(), customer_id: Number(draft.customerId), active: draft.active }
      return id === null ? api.createCircuit(payload) : api.updateCircuit(id, payload)
    }
    case 'sectors': return id === null ? api.createSector(named) : api.updateSector(id, named)
    case 'departments': return id === null ? api.createDepartment(named) : api.updateDepartment(id, named)
    case 'incident-types': return id === null ? api.createIncidentType(named) : api.updateIncidentType(id, named)
  }
}

function changeActive(kind: CatalogKind, id: number, active: boolean): Promise<CatalogItem> {
  switch (kind) {
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
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const [search, setSearch] = useState('')
  const [draft, setDraft] = useState<Draft | null>(null)
  const [busy, setBusy] = useState(false)
  const sending = useRef(false)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setLoadError(null)
    Promise.all([list(kind, controller.signal), kind === 'circuits' ? api.listCustomers(controller.signal, true) : Promise.resolve([])]).then(([rows, clients]) => {
      if (!controller.signal.aborted) { setItems(rows); setCustomers(clients); setLoading(false) }
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) { setLoadError(message(failure)); setLoading(false) }
    })
    return () => controller.abort()
  }, [kind, retry])

  const customerLabel = (id: number) => {
    const customer = customers.find((item) => item.id === id)
    return customer ? `${customer.customer_code} — ${customer.name}` : 'Cliente no disponible'
  }
  const name = (item: CatalogItem) => 'description' in item ? item.description : item.name
  const code = (item: CatalogItem) => 'customer_code' in item ? item.customer_code : 'circuit_code' in item ? item.circuit_code : ''
  const visible = items.filter((item) => `${code(item)} ${name(item)} ${'customer_id' in item ? customerLabel(item.customer_id) : ''}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()))
  const ordered = [...visible].sort((a, b) => (code(a) || name(a)).localeCompare(code(b) || name(b)) || a.id - b.id)

  function edit(item?: CatalogItem) {
    setError(null); setNotice(null)
    setDraft(item ? { id: item.id, code: code(item), name: name(item), customerId: 'customer_id' in item ? String(item.customer_id) : '', active: item.active } : blank())
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
    {draft && <form className="panel mb-6 p-5" aria-label={`${draft.id === null ? 'Crear' : 'Editar'} ${info.singular}`} onSubmit={submit} noValidate>
      <h2 className="mb-4 font-semibold">{draft.id === null ? 'Nuevo' : 'Editar'} {info.singular}</h2>
      <fieldset disabled={busy} className="grid gap-4 sm:grid-cols-2"><legend className="sr-only">Datos del registro</legend>
        {kind === 'circuits' && <FormField id="admin-customer" label="Cliente" required><select id="admin-customer" className="form-input" required value={draft.customerId} onChange={(e) => setDraft({ ...draft, customerId: e.target.value })}><option value="">Selecciona un cliente</option>{customers.map((item) => <option key={item.id} value={item.id}>{item.customer_code} — {item.name}{item.active ? '' : ' (Inactivo)'}</option>)}</select></FormField>}
        {(kind === 'customers' || kind === 'circuits') && <FormField id="admin-code" label={kind === 'customers' ? 'Código de cliente' : 'Código de circuito'} required><input id="admin-code" className="form-input" required value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value })} /></FormField>}
        <FormField id="admin-name" label={kind === 'circuits' ? 'Descripción' : 'Nombre'} required><input id="admin-name" className="form-input" required value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></FormField>
        <div className="flex items-center gap-2 self-end pb-3"><input id="admin-active" type="checkbox" checked={draft.active} onChange={(e) => setDraft({ ...draft, active: e.target.checked })} /><label htmlFor="admin-active" className="text-sm">Activo</label></div>
      </fieldset>
      <p className="mt-3 text-xs text-slate-500">Desactivar conserva el registro y sus referencias históricas.</p>
      <div className="mt-4 flex justify-end gap-3"><button type="button" className="button-secondary" disabled={busy} onClick={() => { setDraft(null); setError(null) }}>Cancelar</button><button type="submit" className="button-primary" disabled={busy}>{busy ? (draft.id === null ? 'Creando...' : 'Guardando...') : 'Guardar'}</button></div>
    </form>}
    {(kind === 'customers' || kind === 'circuits') && <div className="mb-4 max-w-md"><label htmlFor="admin-search" className="mb-1 block text-sm font-medium">Buscar {info.empty}</label><input id="admin-search" type="search" className="form-input" value={search} onChange={(e) => setSearch(e.target.value)} /></div>}
    {loading ? <p role="status">Cargando {info.empty}...</p> : loadError ? <div role="alert" className="panel p-5"><p>Error al cargar {info.empty}: {loadError}</p><button type="button" className="button-secondary mt-3" onClick={() => setRetry(retry + 1)}>Reintentar</button></div> : !ordered.length ? <p className="panel p-6">{items.length ? 'No hay coincidencias con la búsqueda.' : `No hay ${info.empty} registrados.`}</p> : <div className="panel overflow-x-auto"><table className="w-full min-w-[650px] text-left text-sm"><caption className="sr-only">{info.title}</caption>
      <thead className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500"><tr>{[...(kind === 'customers' || kind === 'circuits' ? ['Código'] : []), ...(kind === 'circuits' ? ['Cliente'] : []), kind === 'circuits' ? 'Descripción' : 'Nombre', 'Estado', 'Fecha de creación', 'Acciones'].map((label) => <th key={label} scope="col" className="px-4 py-3 font-medium">{label}</th>)}</tr></thead>
      <tbody className="divide-y divide-slate-100">{ordered.map((item) => <tr key={item.id}>
        {(kind === 'customers' || kind === 'circuits') && <th scope="row" className="px-4 py-3 font-medium">{code(item)}</th>}
        {kind === 'circuits' && 'customer_id' in item && <td className="px-4 py-3">{customerLabel(item.customer_id)}</td>}
        <td className="px-4 py-3">{name(item)}</td><td className="px-4 py-3"><span className={`rounded px-2 py-1 text-xs font-medium ${item.active ? 'bg-emerald-50 text-emerald-800' : 'bg-slate-100 text-slate-600'}`}>{item.active ? 'Activo' : 'Inactivo'}</span></td>
        <td className="whitespace-nowrap px-4 py-3">{formatDate(item.created_at)}</td><td className="px-4 py-3"><div className="flex gap-2"><button type="button" className="button-secondary" disabled={busy || Boolean(draft)} onClick={() => edit(item)} aria-label={`Editar ${code(item) || name(item)}`}>Editar</button><button type="button" className="button-secondary" disabled={busy || Boolean(draft)} onClick={() => toggle(item)} aria-label={`${item.active ? 'Desactivar' : 'Activar'} ${code(item) || name(item)}`}>{item.active ? 'Desactivar' : 'Activar'}</button></div></td>
      </tr>)}</tbody></table></div>}
  </>
}
