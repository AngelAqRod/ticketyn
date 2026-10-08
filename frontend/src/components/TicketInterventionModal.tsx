import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Plus } from 'lucide-react'
import { listResponsibles } from '../api'
import { ApiError } from '../api/client'
import { createTicketUpdate } from '../api/ticketUpdates'
import type { Responsible } from '../types/catalog'
import type { TicketUpdateVisibility } from '../types/ticketUpdate'
import { localDateTimeToIso, localDateTimeValue } from '../lib/datetime'
import { FormField } from './FormField'
import { SearchableSelect } from './SearchableSelect'
import { RequestState } from './RequestState'
import { FeedbackMessage } from './FeedbackMessage'

const message = (error: unknown) => error instanceof Error ? error.message : 'No se pudo completar la solicitud.'

export function TicketInterventionModal({ ticketId, onCreated, onCancel }: { ticketId: number; onCreated: () => void; onCancel: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const initialFocus = useRef<HTMLTextAreaElement>(null)
  const [responsibles, setResponsibles] = useState<Responsible[]>([])
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [catalogRetry, setCatalogRetry] = useState(0)
  const [content, setContent] = useState('')
  const [intervention, setIntervention] = useState(() => localDateTimeValue().split('T'))
  const [responsibleId, setResponsibleId] = useState('')
  const [visibility, setVisibility] = useState<TicketUpdateVisibility>('INTERNAL')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [invalid, setInvalid] = useState<string[]>([])
  const sending = useRef(false)
  const submitController = useRef<AbortController | null>(null)
  const errorId = `follow-up-${ticketId}-error`

  useEffect(() => {
    const element = dialog.current!
    const previousFocus = document.activeElement
    element.showModal()
    initialFocus.current?.focus()
    return () => {
      submitController.current?.abort()
      element.close()
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus()
    }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    setCatalogLoading(true); setCatalogError(null)
    listResponsibles(controller.signal).then((items) => {
      if (!controller.signal.aborted) { setResponsibles(items); setCatalogLoading(false) }
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) { setCatalogError(message(error)); setCatalogLoading(false) }
    })
    return () => controller.abort()
  }, [catalogRetry])

  const unavailable = catalogLoading || Boolean(catalogError)
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (sending.current || unavailable) return
    setSaveError(null); setInvalid([])
    if (!content.trim()) { setSaveError('Escribe la descripción de la intervención.'); setInvalid(['content']); return }
    let occurredAt: string
    try { occurredAt = localDateTimeToIso(`${intervention[0]}T${intervention[1]}`) }
    catch (error) { setSaveError(message(error)); setInvalid(['occurred_at']); return }
    const controller = new AbortController()
    submitController.current = controller
    sending.current = true; setSaving(true)
    try {
      await createTicketUpdate(ticketId, { content, occurred_at: occurredAt,
        responsible_id: responsibleId ? Number(responsibleId) : null, visibility }, controller.signal)
      if (!controller.signal.aborted) {
        onCreated()
      }
    } catch (error) {
      if (!controller.signal.aborted) { setSaveError(message(error)); setInvalid(error instanceof ApiError ? error.fields : []) }
    } finally {
      sending.current = false
      if (!controller.signal.aborted) setSaving(false)
    }
  }
  const fieldProps = (field: string) => ({ invalid: invalid.includes(field), describedBy: invalid.includes(field) ? errorId : undefined })

  return <dialog ref={dialog} aria-labelledby="intervention-heading" aria-modal="true"
    className="quick-dialog fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto bg-white p-5 text-ink backdrop:bg-slate-900/30"
    onKeyDownCapture={(event) => {
      // El combobox maneja Escape cuando está abierto; cerrado, debe permitir salir del modal.
      const target = event.target
      if (event.key === 'Escape' && target instanceof HTMLElement && target.getAttribute('role') === 'combobox' && target.getAttribute('aria-expanded') === 'false') {
        event.preventDefault(); event.stopPropagation()
        if (!sending.current) onCancel()
      }
    }}
    onCancel={(event) => { event.preventDefault(); event.stopPropagation(); if (!sending.current) onCancel() }}>
    <header className="quick-dialog-header"><h2 id="intervention-heading" className="text-lg font-semibold">Nueva intervención</h2></header>
    <form aria-label="Registrar actualización" noValidate onSubmit={(event) => void submit(event)} className="mt-4">
      <RequestState compact loading={catalogLoading} error={catalogError} loadingText="Cargando responsables..." errorTitle="" onRetry={() => setCatalogRetry(catalogRetry + 1)} retryText="Reintentar responsables" />
      <fieldset disabled={saving} className="min-w-0 space-y-3">
        <FormField id="follow-up-content" label="Descripción de la intervención" required {...fieldProps('content')}>
          <textarea ref={initialFocus} id="follow-up-content" className="form-input" rows={3} required value={content} onChange={(event) => setContent(event.target.value)} />
        </FormField>
        <div className="grid min-w-0 gap-3 sm:grid-cols-2">
          <FormField id="follow-up-responsible" label="Responsable de la intervención" {...fieldProps('responsible_id')}>
            <SearchableSelect id="follow-up-responsible" label="Responsable de la intervención" value={responsibleId} options={responsibles.map((item) => ({ value: String(item.id), label: item.name, disabled: !item.active }))} onChange={setResponsibleId} disabled={saving || catalogLoading || Boolean(catalogError)} placeholder="Sin asignar" emptyMessage="No hay responsables activos." noMatchMessage="Sin coincidencias." />
          </FormField>
          <FormField id="follow-up-visibility" label="Visibilidad" {...fieldProps('visibility')}>
            <select id="follow-up-visibility" className="form-input" value={visibility} onChange={(event) => setVisibility(event.target.value as TicketUpdateVisibility)}><option value="INTERNAL">Interna</option><option value="PUBLIC">Pública</option></select>
          </FormField>
          <FormField id="follow-up-date" label="Fecha de intervención" required {...fieldProps('occurred_at')}>
            <input id="follow-up-date" type="date" className="form-input" required value={intervention[0]} onChange={(event) => setIntervention([event.target.value, intervention[1]])} />
          </FormField>
          <FormField id="follow-up-time" label="Hora de intervención" required {...fieldProps('occurred_at')}>
            <input id="follow-up-time" type="time" className="form-input" required value={intervention[1]} onChange={(event) => setIntervention([intervention[0], event.target.value])} />
          </FormField>
        </div>
      </fieldset>
      {saveError && <FeedbackMessage variant="error" id={errorId} className="mt-3">{saveError}</FeedbackMessage>}
      <div className="mt-3 flex flex-wrap justify-end gap-2"><button type="button" className="button-secondary" disabled={saving} onClick={onCancel}>Cancelar</button><button type="submit" className="button-primary" disabled={saving || unavailable}><Plus size={16} aria-hidden="true" />{saving ? 'Registrando...' : 'Registrar actualización'}</button></div>
    </form>
  </dialog>
}
