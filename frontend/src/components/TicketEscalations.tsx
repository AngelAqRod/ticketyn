import { useEffect, useRef, useState } from 'react'
import { ArrowUpRight, Plus } from 'lucide-react'
import { finishEscalation, listEscalations } from '../api/escalations'
import { getJson } from '../api/client'
import type { Escalation } from '../types/escalation'
import type { TicketUpdate } from '../types/ticketUpdate'
import { ticketynDateTimeToIso, ticketynDateTimeValue, ticketynTimezone } from '../lib/datetime'
import { formatDate, formatDuration } from '../lib/format'
import { RequestState } from './RequestState'
import { FeedbackMessage } from './FeedbackMessage'
import { EscalationModal } from './EscalationModal'

function RelatedInterventions({ ticketId, escalationId, scope = 'tickets' }: { ticketId: number; escalationId: number; scope?: string }) {
  const [items, setItems] = useState<TicketUpdate[]>([]), [error, setError] = useState<string | null>(null), [loading, setLoading] = useState(true), [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null)
    getJson<TicketUpdate[]>(`/api/${scope}/${ticketId}/updates?escalation_id=${escalationId}`, controller.signal).then((rows) => { if (!controller.signal.aborted) { setItems(rows); setLoading(false) } }).catch((failure: unknown) => { if (!controller.signal.aborted) { setLoading(false); setError(failure instanceof Error ? failure.message : 'No se pudieron cargar las intervenciones.') } })
    return () => controller.abort()
  }, [ticketId, escalationId, retry, scope])
  return <div className="mt-3"><RequestState compact loading={loading} error={error} empty={!items.length && !loading && !error} emptyTitle="Sin intervenciones relacionadas" emptyDescription="" onRetry={() => setRetry(retry + 1)} />
    <ol className="space-y-2">{items.map((item) => <li key={item.id} className="text-sm"><p className="text-xs text-muted">{formatDate(item.occurred_at)} · {item.responsible?.name ?? 'Sin asignar'} · {item.visibility === 'INTERNAL' ? 'Interna' : 'Pública'}</p><p className="whitespace-pre-wrap [overflow-wrap:anywhere]">{item.content}</p></li>)}</ol>
  </div>
}

export function TicketEscalations({ ticketId, internal = false }: { ticketId: number; internal?: boolean }) {
  const scope = internal ? 'internal-tickets' : 'tickets'
  const [items, setItems] = useState<Escalation[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState<string | null>(null), [retry, setRetry] = useState(0)
  const [editing, setEditing] = useState<Escalation | undefined>(), [finishing, setFinishing] = useState<number | null>(null), [finishTime, setFinishTime] = useState(ticketynDateTimeValue())
  const finishDialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    if (finishing === null) return
    const previous = document.activeElement, dialog = finishDialog.current!
    dialog.showModal(); dialog.querySelector<HTMLInputElement>('input')?.focus()
    return () => { dialog.close(); if (previous instanceof HTMLElement && previous.isConnected) previous.focus() }
  }, [finishing])
  const [modal, setModal] = useState(false), [success, setSuccess] = useState<string | null>(null), [busy, setBusy] = useState<number | null>(null), [expanded, setExpanded] = useState<number | null>(null)
  const sending = useRef(false), operation = useRef<AbortController | null>(null)
  useEffect(() => { return () => operation.current?.abort() }, [])
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null)
    listEscalations(ticketId, controller.signal, scope).then((rows) => { if (!controller.signal.aborted) { setItems(rows); setLoading(false) } }).catch((failure: unknown) => { if (!controller.signal.aborted) { setLoading(false); setError(failure instanceof Error ? failure.message : 'No se pudieron cargar los escalamientos.') } })
    return () => controller.abort()
  }, [ticketId, retry, scope])
  async function finish(id: number) {
    if (sending.current) return
    const controller = new AbortController(); operation.current = controller
    sending.current = true; setBusy(id); setError(null); setSuccess(null)
    try {
      const finishedAt = ticketynDateTimeToIso(finishTime)
      const selected = items.find((row) => row.id === id)!
      if (new Date(finishedAt) < new Date(selected.started_at)) throw new Error('La finalización no puede ser anterior al inicio.')
      const result = await finishEscalation(ticketId, id, controller.signal, finishedAt, scope)
      if (!controller.signal.aborted) { setItems((rows) => rows.map((row) => row.id === id ? result : row)); setFinishing(null); setSuccess('Escalamiento finalizado. El ticket conserva su estado y responsable.') }
    } catch (failure) { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'No se pudo finalizar.') }
    finally { sending.current = false; if (!controller.signal.aborted) setBusy(null) }
  }
  return <section className="panel noc-panel ticket-noc-escalations mt-5 p-4 lg:p-5" aria-labelledby="escalations-heading">
    <div className="section-heading flex-wrap gap-3"><div className="noc-section-title flex items-center gap-2.5"><span className="icon-surface" aria-hidden="true"><ArrowUpRight size={16} /></span><h2 id="escalations-heading">Escalamientos</h2></div><button type="button" className="button-primary" onClick={() => { setSuccess(null); setEditing(undefined); setModal(true) }}><Plus size={16} aria-hidden="true" />Nuevo escalamiento</button></div>
    {success && <FeedbackMessage variant="success" className="mb-3">{success}</FeedbackMessage>}
    <RequestState compact loading={loading} error={error} empty={!loading && !error && !items.length} emptyTitle="Sin escalamientos" emptyDescription="Este ticket no tiene solicitudes de apoyo." onRetry={() => setRetry(retry + 1)} />
    <ol className="space-y-3" aria-label="Historial de escalamientos">{items.map((item) => <li key={item.id} className="min-w-0 border-b border-slate-100 pb-3 last:border-b-0">
      <div className="flex flex-wrap items-center gap-2 text-sm"><span className="font-medium [overflow-wrap:anywhere]">{item.requester ? `${item.requester.name} → ` : ''}{item.recipient?.name ?? `Pendiente de asignación — ${item.recipient_department_name ?? 'Departamento histórico desconocido'}`}{(item.recipient_position_name || item.recipient_level) ? ` · ${item.recipient_position_name || item.recipient_level}` : ''}{item.recipient_department_name ? ` — ${item.recipient_department_name}` : ''}</span><span className="chip chip-neutral">{item.status === 'ACTIVE' ? 'Activo' : 'Finalizado'}</span></div>
      <p className="mt-1 text-xs text-muted">{item.reason.name} · Inicio: {formatDate(item.started_at, ticketynTimezone)}{item.finished_at ? ` · Finalizado: ${formatDate(item.finished_at, ticketynTimezone)}` : ''}</p>
      {item.finished_at && <p className="mt-1 text-xs text-muted">Duración: {formatDuration((new Date(item.finished_at).getTime() - new Date(item.started_at).getTime()) / 1000)}</p>}
      <p className="mt-2 whitespace-pre-wrap [overflow-wrap:anywhere] text-sm">{item.description}</p>
      <div className="mt-2 flex flex-wrap gap-2"><button type="button" className="button-ghost" aria-expanded={expanded === item.id} onClick={() => setExpanded(expanded === item.id ? null : item.id)}>Ver intervenciones</button><button type="button" className="button-secondary" onClick={() => { setEditing(item); setModal(true) }}>Editar escalamiento</button>{item.status === 'ACTIVE' && <button type="button" className="button-secondary" disabled={busy !== null} onClick={() => { setFinishTime(ticketynDateTimeValue()); setFinishing(item.id) }}>{busy === item.id ? 'Finalizando...' : 'Finalizar escalamiento'}</button>}</div>
      {expanded === item.id && <><RelatedInterventions scope={scope} ticketId={ticketId} escalationId={item.id} /><EscalationAuditView scope={scope} ticketId={ticketId} escalationId={item.id} /></>}
      <section aria-label="Metadatos del escalamiento" className="mt-3 border-t border-slate-200 bg-slate-50/50 p-4"><h3 className="section-label mb-2">METADATOS</h3><dl className="flex flex-wrap gap-x-8 gap-y-2">{[["Fecha de creación", item.created_at], ["Última actualización", item.updated_at]].map(([label, value]) => <div key={label} className="flex flex-wrap items-baseline gap-2"><dt className="text-xs text-slate-500">{label}</dt><dd className="text-xs tabular-nums text-slate-600">{formatDate(value, ticketynTimezone)}</dd></div>)}</dl></section>
    </li>)}</ol>
    {finishing !== null && <dialog ref={finishDialog} aria-labelledby="finish-escalation-heading" className="quick-dialog noc-modal fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto bg-white p-5 text-ink backdrop:bg-slate-900/30" onCancel={(event) => { event.preventDefault(); if (!sending.current) setFinishing(null) }}><h2 id="finish-escalation-heading">Finalizar escalamiento</h2><form onSubmit={(event) => { event.preventDefault(); void finish(finishing) }}><label htmlFor="escalation-finish-time">Finalización operativa</label><input autoFocus id="escalation-finish-time" type="datetime-local" className="form-input" required disabled={busy !== null} value={finishTime} onChange={(event) => setFinishTime(event.target.value)} />{error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}<div className="mt-4 flex gap-2"><button type="button" className="button-secondary" disabled={busy !== null} onClick={() => setFinishing(null)}>Cancelar</button><button type="submit" className="button-primary" disabled={busy !== null}>Confirmar finalización</button></div></form></dialog>}
    {modal && <EscalationModal item={editing} ticketId={ticketId} onCancel={() => setModal(false)} onCreated={() => { setModal(false); setSuccess(editing ? 'Escalamiento actualizado. La responsabilidad principal no cambia.' : 'Escalamiento registrado. La responsabilidad principal no cambia.'); setRetry(retry + 1) }} />}
  </section>
}

function auditValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return '—'
  if ((key === 'started_at' || key === 'finished_at') && typeof value === 'string') return formatDate(value, ticketynTimezone)
  if (key === 'status') return value === 'ACTIVE' ? 'Activo' : 'Finalizado'
  return String(value)
}

function EscalationAuditView({ ticketId, escalationId, scope = 'tickets' }: { ticketId: number; escalationId: number; scope?: string }) {
  const [rows, setRows] = useState<{ id: number; event: string; actor: string | null; created_at: string; changes: Record<string, { before: unknown; after: unknown }> }[]>([])
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    getJson<typeof rows>(`/api/${scope}/${ticketId}/escalations/${escalationId}/audit`, controller.signal).then(setRows).catch((failure: unknown) => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'No se pudo cargar la auditoría.') })
    return () => controller.abort()
  }, [ticketId, escalationId])
  return <div className="mt-3 text-xs"><h3 className="section-label">Historial de cambios</h3><RequestState compact error={error} />{rows.map((row) => <div key={row.id} className="mt-2"><p>{formatDate(row.created_at, ticketynTimezone)} · {row.event === 'created' ? 'Creación' : row.event === 'finished' ? 'Finalización' : 'Modificación'} · {row.actor ?? 'Usuario no identificado'}</p>{Object.entries(row.changes).map(([key, change]) => <p key={key}>{{ started_at: 'Inicio operativo', finished_at: 'Finalización operativa', department_id: 'Departamento ID', recipient_id: 'Responsable ID', recipient_department_name: 'Departamento', recipient_position_name: 'Puesto', recipient_level: 'Nivel histórico', status: 'Estado' }[key] ?? key}: {auditValue(key, change.before)} → {auditValue(key, change.after)}</p>)}</div>)}</div>
}
