import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { listEscalationReasons, listResponsibles } from '../api'
import { createEscalation } from '../api/escalations'
import type { Responsible, EscalationReason } from '../types/catalog'
import { FormField } from './FormField'
import { SearchableSelect } from './SearchableSelect'
import { RequestState } from './RequestState'
import { FeedbackMessage } from './FeedbackMessage'

export function EscalationModal({ ticketId, onCreated, onCancel }: { ticketId: number; onCreated: () => void; onCancel: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null), input = useRef<HTMLTextAreaElement>(null), sending = useRef(false)
  const request = useRef<AbortController | null>(null)
  const [people, setPeople] = useState<Responsible[]>([]), [reasons, setReasons] = useState<EscalationReason[]>([])
  const [loading, setLoading] = useState(true), [loadError, setLoadError] = useState<string | null>(null), [retry, setRetry] = useState(0)
  const [recipient, setRecipient] = useState(''), [reason, setReason] = useState(''), [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false), [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const element = dialog.current!, previous = document.activeElement
    element.showModal(); input.current?.focus()
    return () => { request.current?.abort(); element.close(); if (previous instanceof HTMLElement && previous.isConnected) previous.focus() }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setLoadError(null)
    Promise.all([listResponsibles(controller.signal), listEscalationReasons(controller.signal)]).then(([persons, rows]) => {
      if (!controller.signal.aborted) { setPeople(persons); setReasons(rows); setLoading(false) }
    }).catch((failure: unknown) => { if (!controller.signal.aborted) { setLoading(false); setLoadError(failure instanceof Error ? failure.message : 'No se pudieron cargar los catálogos.') } })
    return () => controller.abort()
  }, [retry])
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (sending.current || loading || loadError) return
    if (!recipient || !reason || !description.trim()) { setError('Completa destinatario, motivo y descripción.'); return }
    const controller = new AbortController(); request.current = controller
    sending.current = true; setSaving(true); setError(null)
    try {
      await createEscalation(ticketId, { recipient_id: Number(recipient), reason_id: Number(reason), description }, controller.signal)
      if (!controller.signal.aborted) onCreated()
    } catch (failure) { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'No se pudo registrar el escalamiento.') }
    finally { sending.current = false; if (!controller.signal.aborted) setSaving(false) }
  }
  return <dialog ref={dialog} aria-labelledby="escalation-modal-heading" aria-modal="true" className="quick-dialog fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto bg-white p-5 text-ink backdrop:bg-slate-900/30" onCancel={(event) => { event.preventDefault(); if (!sending.current) onCancel() }}
    onKeyDownCapture={(event) => { if (event.key === 'Escape' && event.target instanceof HTMLElement && event.target.getAttribute('role') === 'combobox' && event.target.getAttribute('aria-expanded') === 'false') { event.preventDefault(); event.stopPropagation(); if (!sending.current) onCancel() } }}>
    <header className="quick-dialog-header"><h2 id="escalation-modal-heading" className="text-lg font-semibold">Nuevo escalamiento</h2></header>
    <p className="my-3 text-xs text-muted">Solicitar apoyo no cambia el responsable, departamento ni estado del ticket. El solicitante no se registra automáticamente.</p>
    <RequestState compact loading={loading} error={loadError} onRetry={() => setRetry(retry + 1)} />
    <form aria-label="Registrar escalamiento" noValidate aria-describedby={error ? "escalation-save-error" : undefined} onSubmit={(event) => void submit(event)}>
      <fieldset disabled={saving} className="min-w-0 space-y-3">
        <FormField id="escalation-description" label="Descripción de la solicitud" required><textarea ref={input} id="escalation-description" className="form-input" rows={3} required maxLength={10000} value={description} onChange={(event) => setDescription(event.target.value)} /></FormField>
        <FormField id="escalation-recipient" label="Destinatario" required><SearchableSelect id="escalation-recipient" label="Destinatario" required disabled={loading || Boolean(loadError)} value={recipient} onChange={setRecipient} options={people.map((person) => ({ value: String(person.id), label: `${person.name}${person.position ? ` · ${person.position.name}${person.department ? ` — ${person.department.name}` : ''}` : ''}`, disabled: !person.active }))} placeholder="Selecciona destinatario" emptyMessage="No hay responsables activos." noMatchMessage="Sin coincidencias." /></FormField>
        <FormField id="escalation-reason" label="Motivo" required><SearchableSelect id="escalation-reason" label="Motivo" required disabled={loading || Boolean(loadError)} value={reason} onChange={setReason} options={reasons.map((item) => ({ value: String(item.id), label: item.name, disabled: !item.active }))} placeholder="Selecciona motivo" emptyMessage="Crea motivos en Catálogos." noMatchMessage="Sin coincidencias." /></FormField>
      </fieldset>
      {error && <FeedbackMessage id="escalation-save-error" variant="error" className="mt-3">{error}</FeedbackMessage>}
      <div className="mt-4 flex flex-wrap justify-end gap-2"><button type="button" className="button-secondary" disabled={saving} onClick={onCancel}>Cancelar</button><button type="submit" className="button-primary" disabled={saving || loading || Boolean(loadError)}>{saving ? 'Registrando...' : 'Registrar escalamiento'}</button></div>
    </form>
  </dialog>
}
