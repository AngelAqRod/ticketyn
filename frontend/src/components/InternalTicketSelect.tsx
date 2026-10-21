import { Can } from '../auth/permissions'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { getJson } from '../api/client'
import type { InternalTicket } from '../types/internalTicket'
import { SearchableSelect } from './SearchableSelect'
import { RequestState } from './RequestState'

/** Remote, bounded search using the existing combobox and its keyboard interaction. */
export function InternalTicketSelect({ value, onChange, disabled }: { value: string; onChange: (id: string) => void; disabled?: boolean }) {
  const [activated, setActivated] = useState(false)
  const [search, setSearch] = useState(''), [rows, setRows] = useState<InternalTicket[]>([]), [selected, setSelected] = useState<InternalTicket | null>(null)
  const [offset, setOffset] = useState(0), [error, setError] = useState<string | null>(null), [loading, setLoading] = useState(false), [more, setMore] = useState(false), [retry, setRetry] = useState(0)
  useEffect(() => {
    const request = new AbortController()
    if (!value) { setSelected(null); return }
    getJson<InternalTicket>(`/api/internal-tickets/${value}`, request.signal).then(row => { if (!request.signal.aborted) setSelected(row) }).catch(() => { if (!request.signal.aborted) setSelected(null) })
    return () => request.abort()
  }, [value])
  useEffect(() => {
    if (!activated) return
    const request = new AbortController(); setLoading(true); setError(null)
    const timer = setTimeout(() => {
      getJson<InternalTicket[]>(`/api/internal-tickets?${new URLSearchParams({ search, limit: '20', offset: String(offset) })}`, request.signal).then(items => {
        if (!Array.isArray(items)) throw new Error('La API no devolvió tickets internos válidos.')
        if (!request.signal.aborted) { setRows(items); setMore(items.length === 20); setLoading(false) }
      }).catch(failure => { if (!request.signal.aborted) { setError(failure instanceof Error ? failure.message : 'No se pudo buscar.'); setLoading(false) } })
    }, 300)
    return () => { clearTimeout(timer); request.abort() }
  }, [search, offset, retry, activated])
  const options = selected && String(selected.id) === value && !rows.some(row => row.id === selected.id) ? [selected, ...rows] : rows
  return <div className="min-w-0"><SearchableSelect id="related-internal-ticket" label="Ticket interno relacionado" value={value} disabled={disabled} onChange={onChange} remote onSearchChange={query => { setActivated(true); setSearch(query); setOffset(0) }} options={options.map(row => ({ value: String(row.id), label: `${row.reference} — ${row.title}` }))} placeholder="Sin ticket interno relacionado" emptyMessage={loading ? 'Buscando...' : 'No hay tickets internos.'} noMatchMessage="Sin coincidencias." dropdownFooter={<div className="flex flex-wrap gap-2 px-2">{offset > 0 && <button type="button" onMouseDown={event => event.preventDefault()} className="button-ghost" onClick={() => setOffset(Math.max(0, offset - 20))}>Resultados anteriores</button>}{more && <button type="button" onMouseDown={event => event.preventDefault()} className="button-ghost" disabled={loading} onClick={() => setOffset(offset + 20)}>Más resultados</button>}</div>} />
    <RequestState compact loading={loading} error={error} loadingText="Buscando tickets internos..." errorTitle="" onRetry={() => setRetry(retry + 1)} />
    {selected && String(selected.id) === value && <p className="mt-1.5 text-xs text-slate-300 whitespace-pre-wrap [overflow-wrap:anywhere]">{selected.description}</p>}
    {value && <Can permission="internal_tickets.view"><Link className="button-ghost rounded-full mt-1.5 inline-flex" to={`/internal-tickets/${value}`}>Ver ticket interno</Link></Can>}
  </div>
}
