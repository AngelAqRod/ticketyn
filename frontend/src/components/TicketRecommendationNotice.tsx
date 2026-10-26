import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, BellOff, CheckCircle2, ShieldAlert, X } from 'lucide-react'
import { getTicketRecommendations, createTicketAck, revokeTicketAck } from '../api/recommendations'
import type { TicketRecommendationsResponse } from '../types/recommendation'
import { formatDate } from '../lib/format'
import { ticketynTimezone } from '../lib/datetime'
import { FeedbackMessage } from './FeedbackMessage'

interface Props {
  ticketId: number
  internal?: boolean
  ticketStatus?: string
  refreshKey?: number
  onTicketStatusChange?: (status: string) => void
  onEscalate?: () => void
}

export function TicketRecommendationNotice({ ticketId, internal = false, ticketStatus = 'OPEN', refreshKey = 0, onTicketStatusChange, onEscalate }: Props) {
  const [data, setData] = useState<TicketRecommendationsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [ackModalOpen, setAckModalOpen] = useState(false)
  const [revoking, setRevoking] = useState(false)
  const [retry, setRetry] = useState(0)

  // ACK form state
  const [durationType, setDurationType] = useState<'1H' | '4H' | '8H' | 'INDEFINITE'>('1H')
  const [reason, setReason] = useState('')
  const [savingAck, setSavingAck] = useState(false)
  const [ackError, setAckError] = useState<string | null>(null)
  const ackDialog = useRef<HTMLDialogElement>(null)

  const refresh = useRef<() => void>(() => {})
  const statusChanged = useRef(onTicketStatusChange)
  statusChanged.current = onTicketStatusChange
  const lastRefresh = useRef({ ticketId, internal, refreshKey, retry })

  useEffect(() => {
    let disposed = false, closed = ticketStatus !== 'OPEN', inFlight = false, queued = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let controller: AbortController | undefined
    const clearTimer = () => { clearTimeout(timer); timer = undefined }
    const visible = () => document.visibilityState !== 'hidden'
    setData(null); setError(null); setLoading(!closed); setAckModalOpen(false)
    async function load() {
      if (disposed || closed || !visible()) return
      clearTimer()
      if (inFlight) { queued = true; return }
      inFlight = true; queued = false
      controller = new AbortController()
      try {
        const res = await getTicketRecommendations(ticketId, internal, controller.signal)
        if (disposed) return
        if (!res || res.ticket_id !== ticketId || !['OPEN', 'CLOSED'].includes(res.ticket_status)) {
          throw new Error('Respuesta de recomendaciones no válida.')
        }
        setData(res); setError(null)
        if (res.ticket_status !== 'OPEN') {
          closed = true
          statusChanged.current?.(res.ticket_status)
        }
      } catch (err: unknown) {
        if (!disposed) setError(err instanceof Error ? err.message : 'Error al cargar recomendaciones.')
      } finally {
        inFlight = false
        if (!disposed) {
          setLoading(false)
          if (!closed && visible()) {
            if (queued) void load()
            else timer = setTimeout(() => void load(), 60_000)
          }
        }
      }
    }
    function visibilityChanged() {
      clearTimer(); queued = false
      if (visible()) void load()
    }
    refresh.current = () => { void load() }
    if (!closed) {
      document.addEventListener('visibilitychange', visibilityChanged)
      void load()
    }
    return () => {
      disposed = true; clearTimer(); controller?.abort()
      document.removeEventListener('visibilitychange', visibilityChanged)
      refresh.current = () => {}
    }
  }, [ticketId, internal, ticketStatus])

  useEffect(() => {
    const previous = lastRefresh.current
    if (previous.ticketId === ticketId && previous.internal === internal &&
        (previous.refreshKey !== refreshKey || previous.retry !== retry)) refresh.current()
    lastRefresh.current = { ticketId, internal, refreshKey, retry }
  }, [ticketId, internal, refreshKey, retry])

  useEffect(() => {
    if (ackModalOpen) {
      ackDialog.current?.showModal()
    } else {
      ackDialog.current?.close()
    }
  }, [ackModalOpen])

  async function handleAckSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!reason.trim()) {
      setAckError('El motivo del reconocimiento es obligatorio.')
      return
    }
    setSavingAck(true)
    setAckError(null)
    try {
      await createTicketAck(ticketId, { duration_type: durationType, reason: reason.trim() }, internal)
      setAckModalOpen(false)
      setReason('')
      setDurationType('1H')
      setRetry((r) => r + 1)
    } catch (err: unknown) {
      setAckError(err instanceof Error ? err.message : 'No se pudo registrar el reconocimiento.')
    } finally {
      setSavingAck(false)
    }
  }

  async function handleRevokeAck() {
    setRevoking(true)
    try {
      await revokeTicketAck(ticketId, { reason: 'Retiro manual' }, internal)
      setRetry((r) => r + 1)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'No se pudo retirar el reconocimiento.')
    } finally {
      setRevoking(false)
    }
  }

  if (ticketStatus !== 'OPEN' || loading || !data || data.ticket_id !== ticketId || data.ticket_status !== 'OPEN' || !Array.isArray(data.recommendations)) return null

  // Case A: Active ACK -> show discrete indicator, no active alarm
  if (data.has_active_ack && data.active_ack) {
    const ack = data.active_ack
    return (
      <div className="rounded-2xl border border-sky-500/20 bg-[#071328] p-4 text-xs font-mono text-slate-300 shadow-md">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-start gap-2.5">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/30 text-sky-400">
              <BellOff size={14} aria-hidden="true" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold uppercase tracking-wider text-sky-300">
                  Recomendaciones de escalamiento reconocidas
                </span>
                <span className="rounded-full border border-sky-400/30 bg-sky-950/60 px-2 py-0.5 text-[10px] text-sky-300">
                  ACK {ack.duration_type === 'INDEFINITE' ? 'Indefinido' : ack.duration_type}
                </span>
              </div>
              <p className="mt-1 text-slate-400">
                Reconocido por: <span className="text-slate-200">{ack.acknowledged_by?.name ?? 'Usuario'}</span>
                {ack.acknowledged_by_position ? ` (${ack.acknowledged_by_position.name})` : ''} ·{' '}
                {ack.acknowledged_at ? formatDate(ack.acknowledged_at, ticketynTimezone) : ''}
              </p>
              <p className="mt-0.5 text-slate-400">
                Vencimiento:{' '}
                <span className="text-slate-200">
                  {ack.expires_at ? formatDate(ack.expires_at, ticketynTimezone) : 'Hasta retiro manual'}
                </span>
              </p>
              <p className="mt-1 text-slate-300 italic whitespace-pre-wrap">«{ack.reason}»</p>
            </div>
          </div>
          {data.can_acknowledge && (
            <button
              type="button"
              className="button-ghost rounded-full text-xs text-sky-400 hover:text-sky-300"
              disabled={revoking}
              onClick={() => void handleRevokeAck()}
            >
              {revoking ? 'Retirando...' : 'Retirar reconocimiento'}
            </button>
          )}
        </div>
      </div>
    )
  }

  // Case B: Recommendations present
  if (data.recommendations.length > 0) {
    const destNames = data.recommendations.map((r) => r.target_position_name).join(', ')
    return (
      <>
        <div className="rounded-2xl border border-amber-500/30 bg-amber-950/20 p-4 shadow-lg">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-start gap-2.5">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-400">
                <AlertTriangle size={16} aria-hidden="true" />
              </span>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold font-mono uppercase tracking-wider text-amber-300">
                    Escalamiento recomendado
                  </h3>
                  <span className="rounded-full border border-amber-500/30 bg-amber-900/40 px-2 py-0.5 text-[10px] font-mono text-amber-300">
                    {data.elapsed_minutes} min transcurridos
                  </span>
                </div>
                <p className="mt-1 text-sm text-slate-200">
                  Este ticket lleva {data.elapsed_minutes} minutos en la etapa actual ({data.stage_name}). Se
                  recomienda escalar a: <strong className="text-amber-200 font-semibold">{destNames}</strong>.
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {data.can_acknowledge && (
                <button
                  type="button"
                  className="button-secondary rounded-full text-xs"
                  onClick={() => {
                    setAckError(null)
                    setAckModalOpen(true)
                  }}
                >
                  <BellOff size={13} className="mr-1" aria-hidden="true" />
                  Reconocer (ACK)
                </button>
              )}
              {onEscalate && (
                <button
                  type="button"
                  className="button-primary rounded-full text-xs"
                  onClick={onEscalate}
                >
                  Escalar ticket
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Modal ACK */}
        <dialog
          ref={ackDialog}
          aria-labelledby="ack-modal-heading"
          aria-modal="true"
          className="quick-dialog noc-modal fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto bg-[#0b1426] border border-sky-500/25 rounded-2xl p-5 text-slate-100 shadow-2xl backdrop:bg-slate-950/80"
          onCancel={(e) => {
            e.preventDefault()
            if (!savingAck) setAckModalOpen(false)
          }}
        >
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400">
                <BellOff size={14} aria-hidden="true" />
              </span>
              <h2 id="ack-modal-heading" className="text-sm font-bold font-mono text-white uppercase tracking-wider">
                Reconocer alarma de escalamiento (ACK)
              </h2>
            </div>
            <button
              type="button"
              className="text-slate-400 hover:text-white"
              onClick={() => setAckModalOpen(false)}
              disabled={savingAck}
            >
              <X size={16} aria-hidden="true" />
            </button>
          </div>

          <p className="mt-3 text-xs text-slate-400">
            El reconocimiento (ACK) silencia exclusivamente las alarmas automáticas de escalamiento para este
            ticket durante el tiempo seleccionado.
          </p>
          <p className="mt-1 text-xs text-amber-300 font-semibold">
            Importante: Reconocer no equivale a resolver ni cerrar el ticket, ni altera el responsable ni el estado.
          </p>

          <form onSubmit={(e) => void handleAckSubmit(e)} className="mt-4 space-y-4">
            <div>
              <label htmlFor="ack-duration" className="text-xs font-mono text-slate-300 block mb-1">
                Duración del silenciamiento
              </label>
              <select
                id="ack-duration"
                className="form-input"
                value={durationType}
                onChange={(e) => setDurationType(e.target.value as any)}
                disabled={savingAck}
              >
                <option value="1H">1 hora</option>
                <option value="4H">4 horas</option>
                <option value="8H">8 horas</option>
                <option value="INDEFINITE">Hasta retirarlo manualmente (Indefinido)</option>
              </select>
            </div>

            <div>
              <label htmlFor="ack-reason" className="text-xs font-mono text-slate-300 block mb-1">
                Motivo del reconocimiento <span className="text-rose-400">*</span>
              </label>
              <textarea
                id="ack-reason"
                className="form-input"
                rows={3}
                required
                maxLength={10000}
                placeholder="Indica la razón operativa para silenciar la alarma de escalamiento..."
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                disabled={savingAck}
              />
            </div>

            {ackError && <FeedbackMessage variant="error">{ackError}</FeedbackMessage>}

            <div className="mt-5 flex justify-end gap-2 border-t border-slate-800 pt-3">
              <button
                type="button"
                className="button-secondary rounded-full"
                disabled={savingAck}
                onClick={() => setAckModalOpen(false)}
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="button-primary rounded-full font-semibold"
                disabled={savingAck}
              >
                {savingAck ? 'Confirmando...' : 'Confirmar reconocimiento'}
              </button>
            </div>
          </form>
        </dialog>
      </>
    )
  }

  return null
}
