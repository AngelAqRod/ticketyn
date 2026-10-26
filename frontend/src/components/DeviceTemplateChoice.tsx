import { useEffect, useId, useState } from 'react'
import { getDeviceTemplate, listDeviceTemplates, type DeviceTemplate, type TemplatePreview } from '../api/deviceTemplates'
import { FormField } from './FormField'
import { SearchableSelect } from './SearchableSelect'
import { FeedbackMessage } from './FeedbackMessage'

export interface TemplateChoice { mode: 'manual' | 'template'; template_id?: number; template_token?: string }
export const manualTemplate: TemplateChoice = { mode: 'manual' }
export const templateReady = (value: TemplateChoice) => value.mode === 'manual' || Boolean(value.template_id && value.template_token)
export const templatePayload = (value: TemplateChoice) => value.mode === 'template' ? { template_id: value.template_id, template_token: value.template_token } : {}

export function TemplateGroupsPreview({ preview }: { preview: TemplatePreview }) {
  return <div className="space-y-2 text-sm">
    <p className="font-semibold">{preview.groups.length} grupos · {preview.total_ports} puertos</p>
    {preview.groups.map((g, i) => <details key={i} className="rounded-lg border border-slate-600/40 p-2">
      <summary>Grupo {i + 1}: {g.nomenclature_name} · {g.numbering_format} · {g.start}–{g.end} · {g.names.length} puertos</summary>
      {g.warning && <FeedbackMessage variant="error">{g.warning}</FeedbackMessage>}
      <p className="mt-2 break-words font-mono text-xs">{g.names.join(', ')}</p>
    </details>)}
  </div>
}

export function DeviceTemplateChoice({ value, onChange, disabled = false }: {
  value: TemplateChoice; onChange: (value: TemplateChoice) => void; disabled?: boolean
}) {
  const id = useId()
  const [rows, setRows] = useState<DeviceTemplate[]>([]), [preview, setPreview] = useState<DeviceTemplate | null>(null)
  const [error, setError] = useState(''), [loading, setLoading] = useState(false), [retry, setRetry] = useState(0)
  useEffect(() => {
    if (value.mode !== 'template') return
    const controller = new AbortController()
    setLoading(true); setError(''); setPreview(null)
    const load = value.template_id ? getDeviceTemplate(value.template_id, controller.signal).then(item => {
      if (!controller.signal.aborted) {
        setPreview(item)
        onChange({ mode: 'template', template_id: item.id, template_token: item.usable ? item.preview_token : undefined })
      }
    }) : listDeviceTemplates(controller.signal).then(items => { if (!controller.signal.aborted) setRows(items) })
    load.catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'No se pudieron consultar las plantillas.') })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
    // Token refresh must not restart its own request.
  }, [value.mode, value.template_id, retry])
  return <fieldset disabled={disabled} className="space-y-3 rounded-xl border border-purple-500/20 p-3">
    <legend className="px-1 text-sm font-semibold">Modalidad de creación</legend>
    <div className="flex flex-wrap gap-4">
      <label><input type="radio" name={`${id}-mode`} checked={value.mode === 'manual'} onChange={() => onChange(manualTemplate)} /> Crear manualmente</label>
      <label><input type="radio" name={`${id}-mode`} checked={value.mode === 'template'} onChange={() => onChange({ mode: 'template' })} /> Crear desde plantilla</label>
    </div>
    {value.mode === 'template' && <>
      <FormField id={`${id}-template`} label="Plantilla" required><SearchableSelect id={`${id}-template`} label="Plantilla" value={value.template_id ? String(value.template_id) : ''}
        options={rows.map(item => ({ value: String(item.id), label: `${item.name} · ${item.total_ports} puertos` }))}
        onChange={id => { setPreview(null); onChange({ mode: 'template', template_id: id ? Number(id) : undefined }) }} disabled={loading} emptyMessage="No hay plantillas activas." noMatchMessage="Sin coincidencias." placeholder="Selecciona una plantilla" /></FormField>
      {loading && <p role="status">Consultando plantilla…</p>}
      {error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}
      {preview && <><TemplateGroupsPreview preview={preview} />{!preview.usable && <FeedbackMessage variant="error">Esta plantilla no está habilitada para nuevos equipos. Regulariza sus nomenclaturas en Administración.</FeedbackMessage>}</>}
      <button type="button" className="button-secondary" disabled={loading} onClick={() => { onChange({ ...value, template_token: undefined }); setRetry(n => n + 1) }}>Volver a comprobar</button>
      <p className="text-xs text-slate-400">Los puertos se crean junto con el equipo. Editar una plantilla posteriormente no modifica equipos existentes.</p>
    </>}
  </fieldset>
}
