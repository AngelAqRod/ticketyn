import { Can } from '../auth/permissions'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { Link2 } from 'lucide-react'
import { getJson } from '../api/client'
import type { InternalTicket } from '../types/internalTicket'
import { RequestState } from './RequestState'

export function RelatedInternalTicket({ id }: { id?: number | null }) {
  const [ticket, setTicket] = useState<InternalTicket | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    const c = new AbortController()
    setTicket(null); setError(null)
    if (id) {
      getJson<InternalTicket>(`/api/internal-tickets/${id}`, c.signal)
        .then((x) => { if (!c.signal.aborted) setTicket(x) })
        .catch((f) => { if (!c.signal.aborted) setError(f instanceof Error ? f.message : 'No se pudo cargar el ticket interno.') })
    }
    return () => c.abort()
  }, [id, retry])

  if (!id) {
    return (
      <section className="p-4 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400 text-sm" aria-hidden="true">
            <Link2 size={16} />
          </span>
          <div>
            <h3 className="text-xs font-bold font-mono text-white uppercase tracking-wider">Ticket Interno Relacionado</h3>
            <p className="text-xs text-slate-500 italic mt-0.5">Sin ticket interno relacionado</p>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section className="p-4 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3 min-w-0">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400 text-sm" aria-hidden="true">
          <Link2 size={16} />
        </span>
        <div className="min-w-0">
          <h3 className="text-xs font-bold font-mono text-white uppercase tracking-wider">Ticket Interno Relacionado</h3>
          {ticket ? (
            <p className="text-sm font-mono text-purple-300 font-semibold mt-0.5 truncate">
              {ticket.reference} — {ticket.title}
            </p>
          ) : (
            <RequestState compact loading={!error} error={error} onRetry={() => setRetry(retry + 1)} />
          )}
        </div>
      </div>
      {ticket && (
        <Can permission="internal_tickets.view" fallback={<span className="text-xs font-mono text-slate-500">Solo lectura</span>}>
          <Link
            to={`/internal-tickets/${id}`}
            className="px-3.5 py-1.5 rounded-full text-xs font-mono font-medium text-purple-300 hover:text-white bg-purple-950/40 hover:bg-purple-900/50 border border-purple-500/30 transition-all shadow-xs"
          >
            Ver ticket interno &gt;
          </Link>
        </Can>
      )}
    </section>
  )
}
