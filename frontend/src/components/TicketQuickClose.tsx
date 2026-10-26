import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { CheckCircle2 } from 'lucide-react'
import { usePermissions } from '../auth/permissions'
import { postJson } from '../api/client'
import { ticketynDateTimeToIso, ticketynTimezone } from '../lib/datetime'
import { FeedbackMessage } from './FeedbackMessage'
import { FormField } from './FormField'

interface ClosableTicket {
  id: number; reference: string; status: string; start_at: string; updated_at: string
  resolution?: string | null; customer_resolution?: string | null
}
interface Props<T extends ClosableTicket> { ticket: T; internal?: boolean; onClosed: (ticket: T) => void }

export function TicketQuickClose<T extends ClosableTicket>({ ticket, internal = false, onClosed }: Props<T>) {
  const [open, setOpen] = useState(false)
  const access = usePermissions()
  if (ticket.status !== 'OPEN' || !access.can(internal ? 'internal_tickets.close' : 'tickets.close')) return null
  return <>
    <button type="button" className="button-secondary rounded-full border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:border-emerald-400/60 hover:bg-emerald-500/20 hover:text-emerald-200 active:bg-emerald-500/25 focus-visible:outline-emerald-300 disabled:opacity-50" onClick={() => setOpen(true)}>
      <CheckCircle2 size={15} aria-hidden="true" />Cerrar ticket
    </button>
    {open && <CloseTicketDialog key={ticket.id} ticket={ticket} internal={internal} onClosed={onClosed} onCancel={() => setOpen(false)} />}
  </>
}

function CloseTicketDialog<T extends ClosableTicket>({ ticket, internal, onClosed, onCancel }: Props<T> & { onCancel: () => void }) {
  // Freeze the revision and prefill together; a background refresh cannot authorize a stale edit.
  const [initial] = useState(ticket)
  const [mode, setMode] = useState('now'), [date, setDate] = useState('')
  const [resolution, setResolution] = useState(initial.resolution ?? '')
  const [customerResolution, setCustomerResolution] = useState(initial.customer_resolution ?? '')
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const dialog = useRef<HTMLDialogElement>(null), sending = useRef(false), request = useRef<AbortController | null>(null)
  const id = useId(), access = usePermissions()
  const canEditPublic = access.can('tickets.edit')
  useEffect(() => {
    const previous = document.activeElement, element = dialog.current!
    element.showModal()
    return () => {
      request.current?.abort(); element.close()
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus()
    }
  }, [])
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (sending.current) return
    setError('')
    let end: string | null = null
    try {
      if (mode === 'manual') {
        end = ticketynDateTimeToIso(date)
        if (new Date(end) < new Date(initial.start_at)) throw new Error('La fecha de cierre debe ser igual o posterior a la apertura.')
        if (new Date(end) > new Date()) throw new Error('La fecha de cierre no puede estar en el futuro.')
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Introduce una fecha y hora válidas.'); return }
    const body: Record<string, unknown> = { expected_updated_at: initial.updated_at, end_at: end }
    if (resolution !== (initial.resolution ?? '')) body.resolution = resolution.trim() ? resolution : null
    if (!internal && canEditPublic && customerResolution !== (initial.customer_resolution ?? '')) body.customer_resolution = customerResolution.trim() ? customerResolution : null
    sending.current = true; setBusy(true)
    const controller = new AbortController(); request.current = controller
    try {
      const closed = await postJson<T>(`/api/${internal ? 'internal-tickets' : 'tickets'}/${initial.id}/close`, body, controller.signal)
      if (!controller.signal.aborted) onClosed(closed)
    } catch (cause) { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'No se pudo cerrar el ticket.'); }
    finally { sending.current = false; if (!controller.signal.aborted) setBusy(false) }
  }
  return <dialog ref={dialog} aria-labelledby={`${id}-title`} aria-describedby={`${id}-reference`} aria-modal="true"
    onCancel={event => { event.preventDefault(); if (!sending.current) onCancel() }}
    className="fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-xl overflow-y-auto quick-dialog border border-sky-500/25 bg-[#0b1426] p-5 text-slate-100 shadow-2xl backdrop:bg-slate-950/80 rounded-2xl">
    <h2 id={`${id}-title`} className="text-lg font-semibold">Cerrar ticket {internal ? 'interno' : 'de cliente'}</h2>
    <p id={`${id}-reference`} className="mt-1 mb-4 text-sm font-mono text-slate-300">{initial.reference}</p>
    <form onSubmit={submit} aria-label="Cierre rápido de ticket" className="grid gap-4">
      {error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}
      <fieldset disabled={busy} className="grid gap-4">
        <fieldset className="grid gap-2"><legend className="form-label mb-2">Fecha de cierre</legend>
          <label className="flex items-center gap-2 text-sm"><input type="radio" name="close-mode" checked={mode === 'now'} onChange={() => setMode('now')} />Cerrar ahora</label>
          <label className="flex items-center gap-2 text-sm"><input type="radio" name="close-mode" checked={mode === 'manual'} onChange={() => setMode('manual')} />Cerrar con fecha y hora específicas</label>
        </fieldset>
        {mode === 'manual' && <FormField id={`${id}-date`} label="Fecha y hora de cierre (24 h)" required describedBy={`${id}-zone`}>
          <input id={`${id}-date`} type="datetime-local" step="1" lang="es-GT" className="form-input" value={date} onChange={event => setDate(event.target.value)} required />
          <p id={`${id}-zone`} className="mt-1 text-xs text-slate-400">Zona horaria: {ticketynTimezone}. Se enviará como un instante UTC.</p>
        </FormField>}
        <FormField id={`${id}-resolution`} label="Resolución interna — Opcional">
          <textarea id={`${id}-resolution`} className="form-input min-h-24" rows={3} maxLength={10000} value={resolution} onChange={event => setResolution(event.target.value)} />
        </FormField>
        {!internal && <FormField id={`${id}-customer`} label="Resolución para el cliente — Opcional">
          <textarea id={`${id}-customer`} className="form-input min-h-24" rows={3} maxLength={10000} disabled={!canEditPublic} value={customerResolution} onChange={event => setCustomerResolution(event.target.value)} />
          {!canEditPublic && <p className="mt-1 text-xs text-slate-400">Modificar este texto requiere permiso de edición de tickets; su contenido se conservará.</p>}
        </FormField>}
      </fieldset>
      <p className="text-xs text-slate-400">Puedes cerrar sin documentar una resolución. La edición y reapertura seguirán disponibles según tus permisos.</p>
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" className="button-secondary" disabled={busy} onClick={onCancel}>Cancelar</button>
        <button type="submit" className="button-primary" disabled={busy}>{busy ? 'Cerrando…' : 'Confirmar cierre'}</button>
      </div>
    </form>
  </dialog>
}
