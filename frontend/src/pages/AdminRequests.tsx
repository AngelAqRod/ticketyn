import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { listAdminRequestTypes, listCircuits, listCustomers, listResponsibles } from '../api'
import { listAdminRequests } from '../api/adminRequests'
import { usePermissions } from '../auth/permissions'
import { PageHeading } from '../components/PageHeading'
import { FilterBar } from '../components/FilterBar'
import { PaginationBar } from '../components/PaginationBar'
import { RequestState } from '../components/RequestState'
import { formatDate } from '../lib/format'
import { ticketynTimezone } from '../lib/datetime'
import { statusLabels } from '../types/adminRequests'
import type { AdminRequest, AdminRequestStatus } from '../types/adminRequests'
import type { Circuit, Customer, NamedCatalog, Responsible } from '../types/catalog'
import '../styles/installationOrders.css' // shortcut: reuses the installation-* table styles; extract when a third module needs them

export const formatDay = (value: string) => value.split('-').reverse().join('/')
const labels: Record<string, string> = { search: 'Búsqueda', date_from: 'Desde', date_to: 'Hasta', requester_id: 'Solicitante', type_id: 'Tipo', status: 'Estado', customer_id: 'Cliente', circuit_id: 'Circuito' }

export function AdminRequests() {
  const access = usePermissions(), [params, setParams] = useSearchParams()
  const [items, setItems] = useState<AdminRequest[]>([]), [total, setTotal] = useState<number | null>(null), [loading, setLoading] = useState(true), [error, setError] = useState<string | null>(null), [retry, setRetry] = useState(0)
  const [people, setPeople] = useState<Responsible[]>([]), [types, setTypes] = useState<NamedCatalog[]>([]), [customers, setCustomers] = useState<Customer[]>([]), [circuits, setCircuits] = useState<Circuit[]>([])
  const offset = Number(params.get('offset') ?? 0), limit = 20, customer = params.get('customer_id')
  const query = new URLSearchParams(params); query.set('limit', String(limit)); query.set('offset', String(offset))
  const key = query.toString()
  function set(name: string, value: string) {
    setParams(old => { const next = new URLSearchParams(old); if (value) next.set(name, value); else next.delete(name); if (name === 'customer_id') next.delete('circuit_id'); if (name !== 'offset') next.delete('offset'); return next })
  }
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(null)
    listAdminRequests(new URLSearchParams(key), controller.signal).then(result => { if (!controller.signal.aborted) { setItems(result.items); setTotal(result.total); setLoading(false) } })
      .catch(cause => { if (!controller.signal.aborted) { setError(cause instanceof Error ? cause.message : 'No se pudieron cargar las solicitudes.'); setLoading(false) } })
    return () => controller.abort()
  }, [key, retry])
  useEffect(() => {
    const controller = new AbortController(), ignore = () => {}
    listResponsibles(controller.signal, true).then(setPeople).catch(ignore)
    listAdminRequestTypes(controller.signal, true).then(setTypes).catch(ignore)
    listCustomers(controller.signal, true).then(setCustomers).catch(ignore)
    return () => controller.abort()
  }, [])
  useEffect(() => {
    if (!customer) { setCircuits([]); return }
    const controller = new AbortController()
    listCircuits(Number(customer), controller.signal, true).then(setCircuits).catch(() => {})
    return () => controller.abort()
  }, [customer])
  const statusRows = (Object.keys(statusLabels) as AdminRequestStatus[]).map(key => ({ id: key as unknown as number, name: statusLabels[key] }))
  const lookup: Record<string, { id: number; name?: string; circuit_code?: string }[]> = { status: statusRows, requester_id: people, type_id: types, customer_id: customers, circuit_id: circuits }
  const chips = Object.entries(labels).flatMap(([name, label]) => {
    const value = params.get(name)
    if (!value) return []
    const found = lookup[name]?.find(row => String(row.id) === value)
    return [{ key: name, label, value: found ? (found.name ?? found.circuit_code ?? value) : name.startsWith('date') ? formatDay(value) : value, onRemove: () => set(name, '') }]
  })
  const select = (name: string, label: string, rows: { id: number; name?: string; circuit_code?: string }[], disabled = false) =>
    <label>{label}<select className="form-input" disabled={disabled} value={params.get(name) ?? ''} onChange={e => set(name, e.target.value)}><option value="">Todos</option>{rows.map(r => <option key={r.id} value={r.id}>{r.name ?? r.circuit_code}</option>)}</select></label>
  return <>
    <PageHeading title="Solicitudes administrativas" description="Bitácora operativa de requerimientos recibidos y su relación con tickets y cambios." theme="purple"
      action={access.can('admin_requests.create') ? <Link className="button-primary button-primary--purple" to="/admin-requests/new">Registrar solicitud</Link> : undefined} />
    <FilterBar theme="purple" label="Filtros de solicitudes administrativas"
      search={<label className="w-full">Buscar<input className="form-input" type="search" value={params.get('search') ?? ''} onChange={e => set('search', e.target.value)} placeholder="Referencia o descripción" /></label>}
      primary={<>
        <label>Desde<input className="form-input" type="date" value={params.get('date_from') ?? ''} onChange={e => set('date_from', e.target.value)} /></label>
        <label>Hasta<input className="form-input" type="date" value={params.get('date_to') ?? ''} onChange={e => set('date_to', e.target.value)} /></label>
        {select('status', 'Estado', statusRows)}{select('requester_id', 'Solicitante', people)}{select('type_id', 'Tipo de solicitud', types)}{select('customer_id', 'Cliente', customers)}{select('circuit_id', 'Circuito', circuits, !customer)}
      </>}
      chips={chips} onClear={() => setParams({})} />
    <RequestState loading={loading} error={error} errorTitle="Error al cargar solicitudes" empty={!loading && !error && !items.length} emptyTitle="No hay solicitudes para estos filtros." emptyDescription="" onRetry={() => setRetry(v => v + 1)} />
    {!loading && !error && items.length > 0 && <div className="panel overflow-x-auto mt-4"><table className="installation-table">
      <caption className="sr-only">Solicitudes administrativas</caption>
      <thead><tr>{['Referencia', 'Fecha de solicitud', 'Estado', 'Tipo', 'Solicitante', 'Cliente / circuito', 'Descripción', 'Registrada'].map(label => <th key={label} scope="col">{label}</th>)}</tr></thead>
      <tbody>{items.map(row => <tr key={row.id}>
        <td><Link className="text-blue-400 font-mono underline" to={`/admin-requests/${row.id}`}>{row.reference}</Link></td>
        <td>{formatDay(row.request_date)}</td><td>{statusLabels[row.status] ?? row.status}</td><td>{row.type.name}</td><td>{row.requester.name}</td>
        <td>{row.customer?.name ?? '—'}{row.circuit && <span className="block text-xs text-slate-400">{row.circuit.circuit_code}</span>}</td>
        <td className="min-w-48 max-w-md truncate" title={row.description}>{row.description}</td>
        <td><span className="block text-xs">{formatDate(row.created_at, ticketynTimezone)}</span><span className="block text-xs text-slate-400">{row.registered_by.name}</span></td>
      </tr>)}</tbody></table></div>}
    <PaginationBar page={Math.floor(offset / limit) + 1} info={total === null ? 'Total no disponible' : `${total} solicitudes`} onPrevious={() => set('offset', String(Math.max(0, offset - limit)))} onNext={() => set('offset', String(offset + limit))}
      previousDisabled={loading || offset <= 0} nextDisabled={loading || Boolean(error) || total === null || offset + limit >= total} />
  </>
}
