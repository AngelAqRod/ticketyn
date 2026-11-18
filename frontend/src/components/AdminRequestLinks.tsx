import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { addAdminRequestLink, removeAdminRequestLink, searchLinkCandidates } from '../api/adminRequests'
import { usePermissions } from '../auth/permissions'
import { FeedbackMessage } from './FeedbackMessage'
import { formatDate } from '../lib/format'
import { ticketynTimezone } from '../lib/datetime'
import type { LinkKind, LinkedRecord } from '../types/adminRequests'

const WINDOW_DAYS = 15
const dayLabel = (iso: string, shift: number) => {
  const [y, m, d] = iso.split('-').map(Number), date = new Date(Date.UTC(y, m - 1, d + shift))
  return `${String(date.getUTCDate()).padStart(2, '0')}/${String(date.getUTCMonth() + 1).padStart(2, '0')}/${date.getUTCFullYear()}`
}
export const linkKinds: { kind: LinkKind; title: string; path: string; module: string }[] = [
  { kind: 'ticket', title: 'Tickets de cliente', path: '/tickets', module: 'tickets' },
  { kind: 'internal_ticket', title: 'Tickets internos', path: '/internal-tickets', module: 'internal_tickets' },
  { kind: 'change', title: 'Control de cambios', path: '/changes', module: 'changes' },
]

export function AdminRequestLinks({ requestId, requestDate, kind, title, path, module, linked, onChanged }: {
  requestId: number; requestDate: string; linked: LinkedRecord[]; onChanged: () => void
} & (typeof linkKinds)[number]) {
  const access = usePermissions(), canLink = access.can('admin_requests.link'), canSearch = canLink && access.can(module + '.view')
  const [open, setOpen] = useState(false), [search, setSearch] = useState(''), [rows, setRows] = useState<LinkedRecord[]>([]), [total, setTotal] = useState(0), [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null), limit = 10
  const taken = new Set(linked.map(row => row.id))
  useEffect(() => {
    if (!open) return
    const controller = new AbortController(), query = new URLSearchParams({ limit: String(limit), offset: String(offset), ...(search.trim() ? { search: search.trim() } : {}) })
    searchLinkCandidates(requestId, kind, query, controller.signal).then(result => { if (!controller.signal.aborted) { setRows(result.items); setTotal(result.total); setError(null) } })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'No se pudo buscar.') })
    return () => controller.abort()
  }, [open, search, offset, requestId, requestDate, kind, linked.length])
  async function act(task: () => Promise<unknown>) {
    if (busy) return
    setBusy(true); setError(null)
    try { await task(); onChanged() } catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo completar la operación.') } finally { setBusy(false) }
  }
  const canView = access.can(module + '.view')
  const record = (row: LinkedRecord) => <>{canView ? <Link className="text-blue-400 font-mono underline" to={`${path}/${row.id}`}>{row.reference}</Link> : <span className="font-mono">{row.reference}</span>} · {row.title} <span className="text-xs text-slate-400">({formatDate(row.date, ticketynTimezone)})</span></>
  return <section className="panel installation-section" aria-label={title}>
    <h2>{title}</h2>
    {linked.length === 0 ? <p className="text-sm text-slate-400">Sin registros asociados.</p> : <ul className="space-y-2">{linked.map(row => <li key={row.id} className="flex flex-wrap items-center gap-3">{record(row)}
      {canLink && <button type="button" className="button-secondary" disabled={busy} aria-label={`Desvincular ${row.reference}`} onClick={() => void act(() => removeAdminRequestLink(requestId, row.link_id as number))}>Desvincular</button>}</li>)}</ul>}
    {canSearch && <div className="mt-4">
      <button type="button" className="button-secondary" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? 'Cerrar búsqueda' : 'Buscar registros para asociar'}</button>
      {open && <div className="mt-3">
        <p className="mb-2 text-xs text-slate-400">Solo se buscan registros entre el {dayLabel(requestDate, -WINDOW_DAYS)} y el {dayLabel(requestDate, WINDOW_DAYS)} (±{WINDOW_DAYS} días de la fecha de solicitud, incluidos los extremos).{kind === 'ticket' ? ' Se respeta el circuito o cliente de la solicitud.' : ''} Las asociaciones ya guardadas se muestran siempre.</p>
        <label className="sr-only" htmlFor={`search-${kind}`}>Buscar {title}</label>
        <input id={`search-${kind}`} className="form-input" type="search" placeholder="Referencia o título" value={search} onChange={e => { setSearch(e.target.value); setOffset(0) }} />
        {rows.length === 0 ? <p className="mt-3 text-sm text-slate-400">No hay registros en el intervalo.</p> : <ul className="mt-3 space-y-2">{rows.map(row => <li key={row.id} className="flex flex-wrap items-center gap-3">{record(row)}
          <button type="button" className="button-primary button-primary--purple" disabled={busy || taken.has(row.id)} aria-label={`Asociar ${row.reference}`} onClick={() => void act(() => addAdminRequestLink(requestId, kind, row.id))}>{taken.has(row.id) ? 'Asociado' : 'Asociar'}</button></li>)}</ul>}
        <div className="mt-3 flex items-center gap-3 text-xs text-slate-400"><span>{total} en el intervalo</span>
          <button type="button" className="button-secondary" disabled={offset <= 0} onClick={() => setOffset(Math.max(0, offset - limit))}>Anterior</button>
          <button type="button" className="button-secondary" disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}>Siguiente</button></div>
      </div>}
    </div>}
    {error && <FeedbackMessage variant="error" className="mt-3">{error}</FeedbackMessage>}
  </section>
}
