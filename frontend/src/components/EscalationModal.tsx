import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { listEscalationReasons, listResponsibles, listDepartments } from '../api'
import { createEscalation, editEscalation } from '../api/escalations'
import type { Responsible, EscalationReason, NamedCatalog } from '../types/catalog'
import type { Escalation } from '../types/escalation'
import { ticketynDateTimeToIso, ticketynDateTimeValue } from '../lib/datetime'
import { FormField } from './FormField'
import { SearchableSelect } from './SearchableSelect'
import { RequestState } from './RequestState'
import { FeedbackMessage } from './FeedbackMessage'

export function EscalationModal({ ticketId, onCreated, onCancel, item, internal = false }: { ticketId: number; internal?: boolean; onCreated: () => void; onCancel: () => void; item?: Escalation }) {
  const dialog = useRef<HTMLDialogElement>(null), input = useRef<HTMLTextAreaElement>(null), sending = useRef(false)
  const request = useRef<AbortController | null>(null)
  const [people, setPeople] = useState<Responsible[]>([]), [reasons, setReasons] = useState<EscalationReason[]>([])
  const [loading, setLoading] = useState(true), [loadError, setLoadError] = useState<string | null>(null), [retry, setRetry] = useState(0)
  const [recipient, setRecipient] = useState(item?.recipient_id ? String(item.recipient_id) : ''), [reason, setReason] = useState(item ? String(item.reason_id) : ''), [description, setDescription] = useState(item?.description ?? '')
  const [departments, setDepartments] = useState<NamedCatalog[]>([]), [department, setDepartment] = useState(item?.department_id ? String(item.department_id) : '')
  const [started, setStarted] = useState(ticketynDateTimeValue(item ? new Date(item.started_at) : new Date())), [finished, setFinished] = useState(item?.finished_at ? ticketynDateTimeValue(new Date(item.finished_at)) : '')
  const [saving, setSaving] = useState(false), [error, setError] = useState<string | null>(null)
  useEffect(() => {
    const element = dialog.current!, previous = document.activeElement
    element.showModal(); if (item) element.querySelector<HTMLInputElement>('input[type="datetime-local"]')?.focus(); else input.current?.focus()
    return () => { request.current?.abort(); element.close(); if (previous instanceof HTMLElement && previous.isConnected) previous.focus() }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setLoadError(null)
    Promise.all([listResponsibles(controller.signal), listEscalationReasons(controller.signal), listDepartments(controller.signal)]).then(([persons, rows, areas]) => {
      if (!controller.signal.aborted) { setPeople(persons); setReasons(rows); setDepartments(areas); setLoading(false) }
    }).catch((failure: unknown) => { if (!controller.signal.aborted) { setLoading(false); setLoadError(failure instanceof Error ? failure.message : 'No se pudieron cargar los catálogos.') } })
    return () => controller.abort()
  }, [retry])
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (sending.current || loading || loadError) return
    if ((!department && (!item || recipient !== (item.recipient_id ? String(item.recipient_id) : ''))) || !reason || !description.trim()) { setError('Completa departamento, motivo y descripción.'); return }
    const controller = new AbortController(); request.current = controller
    sending.current = true; setSaving(true); setError(null)
    try {
      const startedAt = ticketynDateTimeToIso(started)
      if (item?.status === 'FINISHED' && !finished) throw new Error('Completa la finalización operativa.')
      const finishedAt = finished ? ticketynDateTimeToIso(finished) : undefined
      if (finishedAt && finishedAt < startedAt) throw new Error('La finalización no puede ser anterior al inicio.')
      const destination = { recipient_id: recipient ? Number(recipient) : null, department_id: Number(department), started_at: startedAt }
      if (item) {
        const changes: Record<string, unknown> = {}
        if (recipient !== (item.recipient_id ? String(item.recipient_id) : '')) changes.recipient_id = destination.recipient_id
        if (department && Number(department) !== item.department_id) changes.department_id = destination.department_id
        if (started !== ticketynDateTimeValue(new Date(item.started_at))) changes.started_at = startedAt
        if (item.status === 'FINISHED' && finished !== ticketynDateTimeValue(new Date(item.finished_at!))) changes.finished_at = finishedAt
        await editEscalation(ticketId, item.id, changes, controller.signal, internal ? 'internal-tickets' : 'tickets')
      }
      else await createEscalation(ticketId, { ...destination, reason_id: Number(reason), description }, controller.signal, internal ? 'internal-tickets' : 'tickets')
      if (!controller.signal.aborted) onCreated()
    } catch (failure) { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'No se pudo registrar el escalamiento.') }
    finally { sending.current = false; if (!controller.signal.aborted) setSaving(false) }
  }
  return <dialog ref={dialog} aria-labelledby="escalation-modal-heading" aria-modal="true" className="quick-dialog noc-modal fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto bg-white p-5 text-ink backdrop:bg-slate-900/30" onCancel={(event) => { event.preventDefault(); if (!sending.current) onCancel() }}
    onKeyDownCapture={(event) => { if (event.key === 'Escape' && event.target instanceof HTMLElement && event.target.getAttribute('role') === 'combobox' && event.target.getAttribute('aria-expanded') === 'false') { event.preventDefault(); event.stopPropagation(); if (!sending.current) onCancel() } }}>
    <header className="quick-dialog-header"><h2 id="escalation-modal-heading" className="text-lg font-semibold">{item ? 'Editar escalamiento' : 'Nuevo escalamiento'}</h2></header>
    <p className="my-3 text-xs text-muted">Solicitar apoyo no cambia el responsable, departamento ni estado del ticket. El solicitante no se registra automáticamente. Fechas en America/Guatemala.</p>
    <RequestState compact loading={loading} error={loadError} onRetry={() => setRetry(retry + 1)} />
    <form aria-label="Registrar escalamiento" noValidate aria-describedby={error ? "escalation-save-error" : undefined} onSubmit={(event) => void submit(event)}>
      <fieldset disabled={saving} className="min-w-0 space-y-3">
        <FormField id="escalation-description" label="Descripción de la solicitud" required><textarea ref={input} id="escalation-description" className="form-input" rows={3} disabled={Boolean(item)} required maxLength={10000} value={description} onChange={(event) => setDescription(event.target.value)} /></FormField>
        <FormField id="escalation-started" label="Inicio operativo" required><input id="escalation-started" type="datetime-local" className="form-input" required value={started} onChange={(event) => setStarted(event.target.value)} /></FormField>
        {item?.status === 'FINISHED' && <FormField id="escalation-finished" label="Finalización operativa" required><input id="escalation-finished" type="datetime-local" className="form-input" required value={finished} onChange={(event) => setFinished(event.target.value)} /></FormField>}
        <FormField id="escalation-department" label="Departamento de destino" required={!item || item.department_id !== null}><SearchableSelect id="escalation-department" label="Departamento de destino" required={!item || item.department_id !== null} value={department} onChange={(value) => { setDepartment(value); if (people.find((person) => String(person.id) === recipient)?.department_id !== Number(value)) setRecipient('') }} disabled={loading || Boolean(loadError)} options={departments.map((area) => ({ value: String(area.id), label: area.name, disabled: !area.active }))} placeholder="Selecciona departamento" emptyMessage="No hay departamentos." noMatchMessage="Sin coincidencias." /></FormField>
        <FormField id="escalation-recipient" label="Destinatario (opcional)"><SearchableSelect id="escalation-recipient" label="Destinatario" disabled={loading || Boolean(loadError)} value={recipient} onChange={(value) => { setRecipient(value); const selected = people.find((person) => String(person.id) === value); if (selected?.department_id) setDepartment(String(selected.department_id)) }} options={people.filter((person) => !department || person.department_id === Number(department)).map((person) => ({ value: String(person.id), label: `${person.name}${person.position ? ` · ${person.position.name}${person.department ? ` — ${person.department.name}` : ''}` : ''}`, disabled: !person.active }))} placeholder="Selecciona destinatario" emptyMessage="No hay responsables activos." noMatchMessage="Sin coincidencias." /></FormField>
        <FormField id="escalation-reason" label="Motivo" required><SearchableSelect id="escalation-reason" label="Motivo" required disabled={Boolean(item) || loading || Boolean(loadError)} value={reason} onChange={setReason} options={reasons.map((item) => ({ value: String(item.id), label: item.name, disabled: !item.active }))} placeholder="Selecciona motivo" emptyMessage="Crea motivos en Catálogos." noMatchMessage="Sin coincidencias." /></FormField>
      </fieldset>
      {error && <FeedbackMessage id="escalation-save-error" variant="error" className="mt-3">{error}</FeedbackMessage>}
      <div className="mt-4 flex flex-wrap justify-end gap-2"><button type="button" className="button-secondary" disabled={saving} onClick={onCancel}>Cancelar</button><button type="submit" className="button-primary" disabled={saving || loading || Boolean(loadError)}>{saving ? 'Registrando...' : item ? 'Guardar cambios' : 'Registrar escalamiento'}</button></div>
    </form>
  </dialog>
}
