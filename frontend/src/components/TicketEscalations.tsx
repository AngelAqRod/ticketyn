import { useEffect, useRef, useState } from 'react'
import { ArrowUpRight, Plus } from 'lucide-react'
import { finishEscalation, listEscalations } from '../api/escalations'
import { getJson } from '../api/client'
import type { Escalation } from '../types/escalation'
import type { TicketUpdate } from '../types/ticketUpdate'
import { formatDate } from '../lib/format'
import { RequestState } from './RequestState'
import { FeedbackMessage } from './FeedbackMessage'
import { EscalationModal } from './EscalationModal'

function RelatedInterventions({ ticketId, escalationId }: { ticketId: number; escalationId: number }) {
  const [items, setItems] = useState<TicketUpdate[]>([]), [error, setError] = useState<string | null>(null), [loading, setLoading] = useState(true), [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null)
    getJson<TicketUpdate[]>(`/api/tickets/${ticketId}/updates?escalation_id=${escalationId}`, controller.signal).then((rows) => { if (!controller.signal.aborted) { setItems(rows); setLoading(false) } }).catch((failure: unknown) => { if (!controller.signal.aborted) { setLoading(false); setError(failure instanceof Error ? failure.message : 'No se pudieron cargar las intervenciones.') } })
    return () => controller.abort()
  }, [ticketId, escalationId, retry])
  return <div className="mt-3"><RequestState compact loading={loading} error={error} empty={!items.length && !loading && !error} emptyTitle="Sin intervenciones relacionadas" emptyDescription="" onRetry={() => setRetry(retry + 1)} />
    <ol className="space-y-2">{items.map((item) => <li key={item.id} className="text-sm"><p className="text-xs text-muted">{formatDate(item.occurred_at)} · {item.responsible?.name ?? 'Sin asignar'} · {item.visibility === 'INTERNAL' ? 'Interna' : 'Pública'}</p><p className="whitespace-pre-wrap [overflow-wrap:anywhere]">{item.content}</p></li>)}</ol>
  </div>
}

export function TicketEscalations({ ticketId }: { ticketId: number }) {
  const [items, setItems] = useState<Escalation[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState<string | null>(null), [retry, setRetry] = useState(0)
  const [modal, setModal] = useState(false), [success, setSuccess] = useState<string | null>(null), [busy, setBusy] = useState<number | null>(null), [expanded, setExpanded] = useState<number | null>(null)
  const sending = useRef(false), operation = useRef<AbortController | null>(null)
  useEffect(() => { return () => operation.current?.abort() }, [])
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null)
    listEscalations(ticketId, controller.signal).then((rows) => { if (!controller.signal.aborted) { setItems(rows); setLoading(false) } }).catch((failure: unknown) => { if (!controller.signal.aborted) { setLoading(false); setError(failure instanceof Error ? failure.message : 'No se pudieron cargar los escalamientos.') } })
    return () => controller.abort()
  }, [ticketId, retry])
  async function finish(id: number) {
    if (sending.current) return
    const controller = new AbortController(); operation.current = controller
    sending.current = true; setBusy(id); setError(null); setSuccess(null)
    try {
      const result = await finishEscalation(ticketId, id, controller.signal)
      if (!controller.signal.aborted) { setItems((rows) => rows.map((row) => row.id === id ? result : row)); setSuccess('Escalamiento finalizado. El ticket conserva su estado y responsable.') }
    } catch (failure) { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'No se pudo finalizar.') }
    finally { sending.current = false; if (!controller.signal.aborted) setBusy(null) }
  }
  return <section className="panel mt-5 p-4 lg:p-5" aria-labelledby="escalations-heading">
    <div className="section-heading flex-wrap gap-3"><div className="flex items-center gap-2.5"><span className="icon-surface" aria-hidden="true"><ArrowUpRight size={16} /></span><h2 id="escalations-heading">Escalamientos</h2></div><button type="button" className="button-primary" onClick={() => { setSuccess(null); setModal(true) }}><Plus size={16} aria-hidden="true" />Nuevo escalamiento</button></div>
    {success && <FeedbackMessage variant="success" className="mb-3">{success}</FeedbackMessage>}
    <RequestState compact loading={loading} error={error} empty={!loading && !error && !items.length} emptyTitle="Sin escalamientos" emptyDescription="Este ticket no tiene solicitudes de apoyo." onRetry={() => setRetry(retry + 1)} />
    <ol className="space-y-3" aria-label="Historial de escalamientos">{items.map((item) => <li key={item.id} className="min-w-0 border-b border-slate-100 pb-3 last:border-b-0">
      <div className="flex flex-wrap items-center gap-2 text-sm"><span className="font-medium [overflow-wrap:anywhere]">{item.requester ? `${item.requester.name} → ` : ''}{item.recipient.name}{(item.recipient_position_name || item.recipient_level) ? ` · ${item.recipient_position_name || item.recipient_level}` : ''}{item.recipient_department_name ? ` — ${item.recipient_department_name}` : ''}</span><span className="chip chip-neutral">{item.status === 'ACTIVE' ? 'Activo' : 'Finalizado'}</span></div>
      <p className="mt-1 text-xs text-muted">{item.reason.name} · Creado: {formatDate(item.created_at)}{item.finished_at ? ` · Finalizado: ${formatDate(item.finished_at)}` : ''}</p>
      <p className="mt-2 whitespace-pre-wrap [overflow-wrap:anywhere] text-sm">{item.description}</p>
      <div className="mt-2 flex flex-wrap gap-2"><button type="button" className="button-ghost" aria-expanded={expanded === item.id} onClick={() => setExpanded(expanded === item.id ? null : item.id)}>Ver intervenciones</button>{item.status === 'ACTIVE' && <button type="button" className="button-secondary" disabled={busy !== null} onClick={() => void finish(item.id)}>{busy === item.id ? 'Finalizando...' : 'Finalizar escalamiento'}</button>}</div>
      {expanded === item.id && <RelatedInterventions ticketId={ticketId} escalationId={item.id} />}
    </li>)}</ol>
    {modal && <EscalationModal ticketId={ticketId} onCancel={() => setModal(false)} onCreated={() => { setModal(false); setSuccess('Escalamiento registrado. La responsabilidad principal no cambia.'); setRetry(retry + 1) }} />}
  </section>
}
