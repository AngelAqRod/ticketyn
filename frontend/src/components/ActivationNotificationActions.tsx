import { usePermissions } from '../auth/permissions'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Mail } from 'lucide-react'
import { getActivationNotification, requestActivationNotification } from '../api/mailNotifications'
import type { ActivationNotificationStatus, NotificationState } from '../api/mailNotifications'
import { FeedbackMessage } from './FeedbackMessage'

const states: Record<NotificationState, string> = {
  PENDING: 'Solicitud pendiente.', PREPARING: 'En preparación.', SENDING: 'Enviando.',
  ACCEPTED: 'El servidor SMTP aceptó el mensaje. Esto no confirma su entrega al destinatario.',
  FAILED: 'No se pudo completar el envío. Puedes solicitar un nuevo intento manual.',
  PARTIAL: 'El servidor aceptó algunos destinatarios y rechazó otros. Reenviar podría duplicar el correo para quienes ya lo recibieron.',
  UNCERTAIN: 'El resultado del envío anterior es incierto. El correo podría haberse enviado; reenviar puede producir un duplicado.',
  CANCELLED: 'Solicitud cancelada.',
}
const active = new Set<NotificationState>(['PENDING', 'PREPARING', 'SENDING'])

export function ActivationNotificationActions({ activationId }: { activationId: number }) {
  const mayNotify=usePermissions().can("activations.notify")
  const [status, setStatus] = useState<ActivationNotificationStatus | null>(null)
  const [loading, setLoading] = useState(true), [posting, setPosting] = useState(false)
  const [loadError, setLoadError] = useState(''), [sendError, setSendError] = useState(''), [message, setMessage] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const alive = useRef(true), sending = useRef(false), reader = useRef<AbortController | null>(null)

  const refresh = useCallback(async () => {
    reader.current?.abort()
    const controller = new AbortController()
    reader.current = controller
    setLoading(true); setLoadError('')
    try {
      const value = await getActivationNotification(activationId, controller.signal)
      if (!controller.signal.aborted && alive.current) setStatus(value)
    } catch (failure) {
      if (!controller.signal.aborted && alive.current) {
        setStatus(null)
        setLoadError(failure instanceof Error ? failure.message : 'No se pudo consultar la notificación.')
      }
    } finally {
      if (!controller.signal.aborted && alive.current) setLoading(false)
    }
  }, [activationId])

  useEffect(() => {
    alive.current = true
    void refresh()
    return () => { alive.current = false; reader.current?.abort() }
  }, [refresh])
  useEffect(() => { setConfirmed(false) }, [status?.revision, status?.state])
  useEffect(() => {
    if (!status?.state || !active.has(status.state) || status.processor_paused || loading || posting) return
    const timer = setTimeout(() => void refresh(), 3000)
    return () => clearTimeout(timer)
  }, [status, loading, posting, refresh])

  async function request() {
    if (sending.current || loading || !status?.can_request || (status.state === 'UNCERTAIN' && !confirmed)) return
    sending.current = true; reader.current?.abort()
    setPosting(true); setSendError(''); setMessage('')
    try {
      const value = await requestActivationNotification(activationId, status.revision, status.state === 'UNCERTAIN' && confirmed)
      if (alive.current) {
        setStatus(value)
        setMessage(value.message ?? 'Notificación solicitada. El envío se procesará en segundo plano.')
      }
    } catch (failure) {
      if (alive.current) {
        setSendError(failure instanceof Error ? failure.message : 'No se pudo solicitar la notificación.')
        // Reconcile conflicts and lost HTTP responses by reading only. Never
        // retry a POST automatically or retain an actionable stale revision.
        await refresh()
      }
    } finally {
      sending.current = false
      if (alive.current) setPosting(false)
    }
  }

  return <section aria-label="Notificación por correo" aria-busy={loading || posting} className="min-w-0 max-w-sm space-y-2 text-sm text-white [overflow-wrap:anywhere]">
    <div className="flex flex-wrap items-center gap-2">
      {mayNotify && status && status.mode !== 'DISABLED' && <button type="button" className="button-primary button-primary--emerald rounded-full shadow-sm text-xs"
        disabled={loading || posting || !status.can_request || (status.state === 'UNCERTAIN' && !confirmed)} onClick={() => void request()}>
        <Mail size={14} aria-hidden="true" />{posting ? 'Solicitando…' : status.state === null ? 'Enviar notificación' : 'Enviar nuevamente'}
      </button>}
      <button type="button" className="button-secondary rounded-full shadow-xs text-xs" disabled={loading || posting} onClick={() => { setSendError(''); setMessage(''); setConfirmed(false); void refresh() }}>Consultar estado</button>
    </div>
    {loading && <p role="status" className="text-xs font-mono text-slate-400">Consultando notificación…</p>}
    {status && <div className="p-2.5 rounded-xl bg-[#070d1a] border border-slate-800/80 text-xs font-mono space-y-1.5">
      <p role="status" aria-live="polite" className="text-slate-300">{status.state ? states[status.state] : 'Sin envío solicitado.'}</p>
      {status.mode === 'DISABLED' && <p className="text-amber-300">Notificaciones desactivadas.</p>}
      {status.processor_paused && <p className="text-amber-400">Procesador pausado. Las solicitudes pendientes esperarán la revisión y reanudación desde Administración.</p>}
      {status.configuration_error && <FeedbackMessage variant="error">{status.configuration_error}</FeedbackMessage>}
      {mayNotify && status.mode !== 'DISABLED' && status.state === 'UNCERTAIN' && <label className="flex items-start gap-2 text-slate-300">
        <input type="checkbox" className="mt-1" disabled={posting || loading} checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />
        Confirmo que reenviar puede duplicar el correo.
      </label>}
    </div>}
    {loadError && <FeedbackMessage variant="error">{loadError}</FeedbackMessage>}
    {sendError && <FeedbackMessage variant="error">{sendError}</FeedbackMessage>}
    {message && <FeedbackMessage variant="success">{message}</FeedbackMessage>}
  </section>
}
