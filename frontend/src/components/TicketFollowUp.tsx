import { Can, usePermissions } from '../auth/permissions'
import { useEffect, useRef, useState } from 'react'
import { Globe, LockKeyhole, MessageSquare, Plus } from 'lucide-react'
import { pageTicketUpdates } from '../api/ticketUpdates'
import type { TicketUpdate } from '../types/ticketUpdate'
import { formatDate } from '../lib/format'
import { RequestState } from './RequestState'
import { FeedbackMessage } from './FeedbackMessage'
import { TicketInterventionModal } from './TicketInterventionModal'

const message = (error: unknown) => error instanceof Error ? error.message : 'No se pudo cargar el seguimiento.'

export function TicketFollowUp({ ticketId, internal = false }: { ticketId: number; internal?: boolean }) {
  const access = usePermissions()
  const scope = internal ? 'internal-tickets' : 'tickets'
  const [updates, setUpdates] = useState<TicketUpdate[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [moreLoading, setMoreLoading] = useState(false)
  const [moreError, setMoreError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const [modal, setModal] = useState(false)
  const [success, setSuccess] = useState(false)
  const moreRequest = useRef<AbortController | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    moreRequest.current?.abort()
    setLoading(true); setLoadError(null); setMoreError(null); setMoreLoading(false)
    pageTicketUpdates(ticketId, null, controller.signal, scope).then((page) => {
      if (!controller.signal.aborted) { setUpdates(page.items); setCursor(page.next_cursor); setLoading(false) }
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) { setLoadError(message(error)); setLoading(false) }
    })
    return () => { controller.abort(); moreRequest.current?.abort() }
  }, [ticketId, retry, scope])

  async function loadMore() {
    if (!cursor || moreRequest.current && !moreRequest.current.signal.aborted) return
    const controller = new AbortController()
    moreRequest.current = controller
    setMoreLoading(true); setMoreError(null)
    try {
      const page = await pageTicketUpdates(ticketId, cursor, controller.signal, scope)
      if (!controller.signal.aborted) {
        setUpdates((previous) => [...previous, ...page.items.filter((item) => !previous.some((existing) => existing.id === item.id))])
        setCursor(page.next_cursor)
      }
    } catch (error) { if (!controller.signal.aborted) setMoreError(message(error)) }
    finally { if (!controller.signal.aborted) { setMoreLoading(false); moreRequest.current = null } }
  }

  return <section className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-4" aria-labelledby="follow-up-heading">
    <div className="flex flex-wrap items-center justify-between border-b border-sky-500/15 pb-3 gap-3">
      <div className="flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs" aria-hidden="true"><MessageSquare size={14} /></span>
        <h2 id="follow-up-heading" className="text-xs font-bold font-mono text-white uppercase tracking-wider">Seguimiento</h2>
      </div>
      <Can permission={(internal?"internal_tickets":"tickets")+".followup"}><button type="button" className="button-primary rounded-full text-xs font-semibold" onClick={() => { setSuccess(false); setModal(true) }}><Plus size={14} aria-hidden="true" />Nueva intervención</button></Can>
    </div>
    {success && <FeedbackMessage variant="success" className="mb-3">Actualización registrada correctamente.</FeedbackMessage>}
    <RequestState compact loading={loading} error={loadError} loadingText="Cargando seguimiento..." errorTitle="" onRetry={() => setRetry((value) => value + 1)} retryText="Reintentar seguimiento" />
    {!loading && !loadError && <>
      <RequestState compact empty={!updates.length} emptyTitle="Sin actualizaciones" emptyDescription="Todavía no se han registrado intervenciones en este ticket." />
      {updates.length > 0 && <ol className="space-y-3" aria-label="Historial de seguimiento">
        {updates.map((update) => {
          const InternalIcon = update.visibility === 'INTERNAL' ? LockKeyhole : Globe
          return <li key={update.id} className="min-w-0 p-3.5 rounded-xl bg-[#070d1a] border border-slate-800 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-mono">
              <span className="text-slate-400">
                <time dateTime={update.occurred_at} className="tabular-nums text-slate-300 font-medium">{formatDate(update.occurred_at)}</time>
                {' · '}
                <strong className="text-white font-medium">{update.responsible?.name ?? 'Sin asignar'}</strong>
              </span>
              <div className="flex items-center gap-1.5">
                {update.escalation_id && <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-purple-950/80 text-purple-300 border border-purple-500/30">Escalamiento #{update.escalation_id}</span>}
                <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono flex items-center gap-1 ${update.visibility === 'PUBLIC' ? 'bg-sky-950/80 text-sky-300 border border-sky-700/60' : 'bg-slate-900 text-slate-400 border border-slate-700'}`}>
                  <InternalIcon size={11} aria-hidden="true" />
                  {update.visibility === 'INTERNAL' ? 'Interna' : 'Pública'}
                </span>
              </div>
            </div>
            <p className="text-xs text-slate-200 leading-relaxed whitespace-pre-wrap [overflow-wrap:anywhere] m-0">{update.content}</p>
          </li>
        })}
      </ol>}
    </>}
    {!loading && !loadError && <><RequestState compact loading={moreLoading} error={moreError} loadingText="Cargando más intervenciones..." errorTitle="" onRetry={() => void loadMore()} retryText="Reintentar más intervenciones" />
      {cursor && !moreError && <button type="button" className="button-secondary rounded-full mt-3 text-xs" disabled={moreLoading} onClick={() => void loadMore()}>Cargar más</button>}</>}
    {modal && access.can((internal?"internal_tickets":"tickets")+".followup") && <TicketInterventionModal internal={internal} ticketId={ticketId} onCancel={() => setModal(false)} onCreated={() => { setModal(false); setSuccess(true); setRetry((value) => value + 1) }} />}
  </section>
}
