import { useEffect, useRef, useState } from 'react'
import { Globe, LockKeyhole, MessageSquare, Plus } from 'lucide-react'
import { pageTicketUpdates } from '../api/ticketUpdates'
import type { TicketUpdate } from '../types/ticketUpdate'
import { formatDate } from '../lib/format'
import { RequestState } from './RequestState'
import { FeedbackMessage } from './FeedbackMessage'
import { TicketInterventionModal } from './TicketInterventionModal'

const message = (error: unknown) => error instanceof Error ? error.message : 'No se pudo cargar el seguimiento.'

export function TicketFollowUp({ ticketId }: { ticketId: number }) {
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
    pageTicketUpdates(ticketId, null, controller.signal).then((page) => {
      if (!controller.signal.aborted) { setUpdates(page.items); setCursor(page.next_cursor); setLoading(false) }
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) { setLoadError(message(error)); setLoading(false) }
    })
    return () => { controller.abort(); moreRequest.current?.abort() }
  }, [ticketId, retry])

  async function loadMore() {
    if (!cursor || moreRequest.current && !moreRequest.current.signal.aborted) return
    const controller = new AbortController()
    moreRequest.current = controller
    setMoreLoading(true); setMoreError(null)
    try {
      const page = await pageTicketUpdates(ticketId, cursor, controller.signal)
      if (!controller.signal.aborted) {
        setUpdates((previous) => [...previous, ...page.items.filter((item) => !previous.some((existing) => existing.id === item.id))])
        setCursor(page.next_cursor)
      }
    } catch (error) { if (!controller.signal.aborted) setMoreError(message(error)) }
    finally { if (!controller.signal.aborted) { setMoreLoading(false); moreRequest.current = null } }
  }

  return <section className="panel mt-5 p-4 lg:p-5" aria-labelledby="follow-up-heading">
    <div className="section-heading flex-wrap gap-3"><div className="flex items-center gap-2.5"><span className="icon-surface" aria-hidden="true"><MessageSquare size={16} /></span><h2 id="follow-up-heading">Seguimiento</h2></div>
      <button type="button" className="button-primary" onClick={() => { setSuccess(false); setModal(true) }}><Plus size={16} aria-hidden="true" />Nueva intervención</button>
    </div>
    {success && <FeedbackMessage variant="success" className="mb-3">Actualización registrada correctamente.</FeedbackMessage>}
    <RequestState compact loading={loading} error={loadError} loadingText="Cargando seguimiento..." errorTitle="" onRetry={() => setRetry((value) => value + 1)} retryText="Reintentar seguimiento" />
    {!loading && !loadError && <>
      <RequestState compact empty={!updates.length} emptyTitle="Sin actualizaciones" emptyDescription="Todavía no se han registrado intervenciones en este ticket." />
      {updates.length > 0 && <ol className="space-y-3" aria-label="Historial de seguimiento">
        {updates.map((update) => {
          const InternalIcon = update.visibility === 'INTERNAL' ? LockKeyhole : Globe
          return <li key={update.id} className="min-w-0 border-b border-slate-100 pb-3 last:border-b-0">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-slate-500">
              <time dateTime={update.occurred_at} className="font-medium tabular-nums text-slate-700">{formatDate(update.occurred_at)}</time>
              <span className="min-w-0 max-w-full [overflow-wrap:anywhere]">{update.responsible?.name ?? 'Sin asignar'}</span>
              <span className={`chip ${update.visibility === 'PUBLIC' ? 'bg-blue-50 text-primary' : 'bg-slate-50 text-slate-600'}`}><InternalIcon size={12} aria-hidden="true" />{update.visibility === 'INTERNAL' ? 'Interna' : 'Pública'}</span>
            </div>
            <p className="mt-2 whitespace-pre-wrap [overflow-wrap:anywhere] text-sm leading-6 text-slate-700">{update.content}</p>
          </li>
        })}
      </ol>}
    </>}
    {!loading && !loadError && <><RequestState compact loading={moreLoading} error={moreError} loadingText="Cargando más intervenciones..." errorTitle="" onRetry={() => void loadMore()} retryText="Reintentar más intervenciones" />
      {cursor && !moreError && <button type="button" className="button-secondary mt-3" disabled={moreLoading} onClick={() => void loadMore()}>Cargar más</button>}</>}
    {modal && <TicketInterventionModal ticketId={ticketId} onCancel={() => setModal(false)} onCreated={() => { setModal(false); setSuccess(true); setRetry((value) => value + 1) }} />}
  </section>
}
