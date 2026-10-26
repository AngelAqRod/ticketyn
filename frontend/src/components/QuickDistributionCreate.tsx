import { DeviceTemplateChoice, manualTemplate, templatePayload, templateReady, type TemplateChoice } from './DeviceTemplateChoice'
import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { createPortal } from 'react-dom'
import { createDistributionDevice, listDistributionDevices } from '../api'
import { ApiError } from '../api/client'
import { usePermissions } from '../auth/permissions'
import type { DistributionDevice } from '../types/catalog'
import { FeedbackMessage } from './FeedbackMessage'
import { FormField } from './FormField'
import { RequestState } from './RequestState'

type Resource = DistributionDevice
type Props = {
  kind: 'device'
  parentId: number
  parentName: string
  onCreated: (item: Resource) => void
  onCancel: () => void
}

// Only case and whitespace are compared; interface aliases remain distinct.
const normalizedName = (name: string) => name.replace(/\s+/gu, ' ').trim().toLowerCase()
const message = (cause: unknown) => cause instanceof Error ? cause.message : 'No se pudo crear el registro.'

export function QuickDistributionCreate({ kind, parentId, parentName, onCreated, onCancel }: Props) {
  const access = usePermissions(), id = useId(), dialog = useRef<HTMLDialogElement>(null)
  const sending = useRef(false), request = useRef<AbortController | null>(null)
  const [template, setTemplate] = useState<TemplateChoice>(manualTemplate)
  const [name, setName] = useState(''), [description, setDescription] = useState('')
  const [rows, setRows] = useState<Resource[]>([]), [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null), [retry, setRetry] = useState(0)
  const [error, setError] = useState<string | null>(null), [fields, setFields] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const device = kind === 'device', noun = device ? 'equipo' : 'puerto'
  const module = device ? 'distribution_devices' : 'distribution_ports'
  const canCreate = access.can(`${module}.create`) && access.any(`${module}.lookup`, `${module}.view`)
  const read = (signal: AbortSignal) => listDistributionDevices(parentId, signal, true)
  useEffect(() => {
    const element = dialog.current!, previous = document.activeElement
    element.showModal()
    return () => { request.current?.abort(); element.close(); if (previous instanceof HTMLElement && previous.isConnected) previous.focus() }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setLoadError(null)
    if (!canCreate) { setLoading(false); setLoadError('No tienes permiso para crear este registro.'); return }
    read(controller.signal).then(items => {
      if (!controller.signal.aborted) { setRows(items); setLoading(false) }
    }).catch(cause => { if (!controller.signal.aborted) { setLoadError(message(cause)); setLoading(false) } })
    return () => controller.abort()
  }, [kind, parentId, retry, canCreate])

  async function submit(event: FormEvent) {
    // Portals still bubble through React: never submit the enclosing circuit.
    event.preventDefault(); event.stopPropagation()
    if (!templateReady(template) || sending.current || loading || loadError || !canCreate) return
    setError(null); setFields([])
    if (!name.trim() || Array.from(name.trim()).length > 255 || Array.from(description).length > 10000) {
      setError('Indica un nombre de hasta 255 caracteres y una descripción de hasta 10000 caracteres.'); setFields(['name', 'description']); return
    }
    sending.current = true; setSaving(true)
    const controller = new AbortController(); request.current = controller
    try {
      // Refresh before every attempt, including retries after an uncertain network result.
      const existing = await read(controller.signal)
      if (controller.signal.aborted) return
      setRows(existing)
      if (existing.some(item => normalizedName(item.name) === normalizedName(name))) {
        setError(`Ya existe un ${noun} con ese nombre en este ${device ? 'nodo' : 'equipo'}, incluso si está inactivo.`); setFields(['name']); return
      }
      const content = { name: name.trim(), description: description.trim() ? description : null }
      const created = await createDistributionDevice({ ...content, node_id: parentId, ...templatePayload(template) }, controller.signal)
      if (!controller.signal.aborted) onCreated(created)
    } catch (cause) {
      if (!controller.signal.aborted) {
        setError(cause instanceof ApiError && cause.status === 409 ? `No se pudo crear el ${noun}: ${cause.message} Revisa los registros existentes antes de reintentar.` : message(cause))
        setFields(cause instanceof ApiError ? cause.fields : [])
      }
    } finally { sending.current = false; if (!controller.signal.aborted) setSaving(false) }
  }

  return createPortal(<dialog ref={dialog} aria-labelledby={`${id}-title`} aria-describedby={`${id}-description`}
    className="quick-dialog fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-md overflow-y-auto rounded-2xl border border-sky-500/25 bg-[#0b1426] p-5 text-slate-100 shadow-2xl backdrop:bg-slate-950/80"
    onCancel={event => { event.preventDefault(); event.stopPropagation(); if (!sending.current) onCancel() }}>
    <h2 id={`${id}-title`} className="text-xl font-bold text-white">Nuevo {noun} de distribución</h2>
    <p id={`${id}-description`} className="mt-2 text-xs text-slate-300">Se creará un registro activo. El circuito se guarda por separado.</p>
    <p className="my-4 break-words text-sm text-slate-300">{device ? 'Nodo' : 'Equipo'}: <strong className="text-white">{parentName}</strong></p>
    <RequestState compact loading={loading} loadingText={`Consultando ${device ? 'equipos del nodo' : 'puertos del equipo'}...`} error={loadError} errorTitle="" onRetry={() => setRetry(value => value + 1)} />
    {!loading && !loadError && <div className="mb-4 text-xs text-slate-300">
      <p>{device ? 'Equipos' : 'Puertos'} ya registrados:</p>
      {rows.length ? <ul className="mt-1 max-h-28 overflow-y-auto space-y-1">{rows.map(item => <li key={item.id} className="break-words">{item.name}{!item.active && ' (Inactivo)'}</li>)}</ul> : <p>No hay {device ? 'equipos' : 'puertos'} registrados.</p>}
    </div>}
    <form aria-label={`Crear ${noun} de distribución`} onSubmit={submit} noValidate>
      <fieldset disabled={saving || loading || Boolean(loadError) || !canCreate} className="space-y-3">
        <legend className="sr-only">Datos del {noun}</legend>
        <DeviceTemplateChoice value={template} onChange={setTemplate} disabled={saving} />
        <FormField id={`${id}-name`} label="Nombre" required invalid={fields.includes('name')} describedBy={error ? `${id}-error` : undefined}>
          <input autoFocus id={`${id}-name`} required className="form-input" value={name} onChange={event => setName(event.target.value)} />
          <p className="mt-1 text-xs text-slate-300">Hasta 255 caracteres.</p>
        </FormField>
        <FormField id={`${id}-description-input`} label="Descripción (opcional)" invalid={fields.includes('description')} describedBy={error ? `${id}-error` : undefined}>
          <textarea id={`${id}-description-input`} rows={3} className="form-input" value={description} onChange={event => setDescription(event.target.value)} />
          <p className="mt-1 text-xs text-slate-300">Hasta 10000 caracteres.</p>
        </FormField>
      </fieldset>
      {error && <FeedbackMessage id={`${id}-error`} variant="error" className="mt-3">{error}</FeedbackMessage>}
      <div className="mt-5 flex justify-end gap-3">
        <button type="button" className="button-secondary rounded-full" disabled={saving} onClick={onCancel}>Cancelar</button>
        <button type="submit" className="button-primary button-primary--blue rounded-full" disabled={!templateReady(template) || saving || loading || Boolean(loadError) || !canCreate}>{saving ? 'Creando...' : 'Crear'}</button>
      </div>
    </form>
  </dialog>, document.body)
}
