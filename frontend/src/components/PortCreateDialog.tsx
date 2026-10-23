import '../styles/distribution.css'
import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { createPortal } from 'react-dom'
import { listPortNomenclatures, previewPorts, createPortRange } from '../api/portNomenclatures'
import type { NumberFormat, PortGeneration, PortNomenclature, PortPreview } from '../api/portNomenclatures'
import { createDistributionPort } from '../api/distribution'
import { usePermissions } from '../auth/permissions'
import { useDistributionDialog } from '../hooks/useDistributionDialog'
import type { DistributionPort } from '../types/distribution'
import { FeedbackMessage } from './FeedbackMessage'
import { FormField } from './FormField'
import { RequestState } from './RequestState'
import { SearchableSelect } from './SearchableSelect'

const message = (error: unknown) => error instanceof Error ? error.message : 'No se pudieron comprobar los puertos.'
type Props = {
  deviceId: number
  deviceName: string
  initialMode?: 'single' | 'complete' | 'missing'
  circuitContext?: boolean
  onCreated: (ports: DistributionPort[]) => void
  onClose: () => void
}

export function PortCreateDialog({ deviceId, deviceName, initialMode = 'single', circuitContext = false, onCreated, onClose }: Props) {
  const id = useId(), dialog = useDistributionDialog(true), access = usePermissions()
  const allowed = access.can('distribution_ports.create')
  const [catalog, setCatalog] = useState<PortNomenclature[]>([])
  const [loading, setLoading] = useState(true), [loadError, setLoadError] = useState<string | null>(null)
  const [nomenclatureId, setNomenclatureId] = useState(''), [format, setFormat] = useState<NumberFormat>('N')
  const [positions, setPositions] = useState<string[]>(['0', '0', '0'])
  const [start, setStart] = useState('1'), [end, setEnd] = useState('24'), [description, setDescription] = useState('')
  const [mode, setMode] = useState(initialMode), [retry, setRetry] = useState(0)
  const [checking, setChecking] = useState(false), [checked, setChecked] = useState<{ key: string; value: PortPreview } | null>(null)
  const [error, setError] = useState<string | null>(null), [saving, setSaving] = useState(false)
  const sending = useRef(false), mutation = useRef<AbortController | null>(null)
  useEffect(() => () => mutation.current?.abort(), [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setLoadError(null)
    if (!allowed) { setLoading(false); return }
    listPortNomenclatures(controller.signal).then(rows => {
      if (!controller.signal.aborted) { setCatalog(rows); setLoading(false) }
    }).catch(cause => { if (!controller.signal.aborted) { setLoadError(message(cause)); setLoading(false) } })
    return () => controller.abort()
  }, [allowed, retry])
  const selected = catalog.find(row => String(row.id) === nomenclatureId)
  const count = format.split('/').length - 1
  const fixed = positions.slice(0, count)
  const numbers = [...fixed, start, ...(mode === 'single' ? [] : [end])]
  const validNumbers = numbers.every(value => /^\d+$/.test(value) && Number.isSafeInteger(Number(value)))
  const rangeEnd = mode === 'single' ? Number(start) : Number(end)
  const validRange = validNumbers && rangeEnd >= Number(start) && rangeEnd - Number(start) < 256
  const input: PortGeneration = { distribution_device_id: deviceId, nomenclature_id: Number(nomenclatureId), numbering_format: format,
    positions: fixed.map(Number), start: Number(start), ...(mode === 'single' ? {} : { end: rangeEnd }),
    mode: mode === 'missing' ? 'missing' : 'complete', description: description.trim() ? description : null }
  const key = JSON.stringify(input)
  const valid = allowed && selected?.active && selected.formats.includes(format) && validRange && Array.from(description).length <= 10000
  const preview = valid && checked?.key === key ? checked.value : null
  useEffect(() => {
    const controller = new AbortController()
    setChecked(null); setChecking(false)
    if (!valid) return
    setChecking(true)
    const timer = window.setTimeout(() => {
      previewPorts(JSON.parse(key), controller.signal).then(value => {
        if (!controller.signal.aborted) { setChecked({ key, value }); setChecking(false) }
      }).catch(cause => { if (!controller.signal.aborted) { setError(message(cause)); setChecking(false) } })
    }, 200)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [key, Boolean(valid), retry])

  async function submit(event: FormEvent) {
    event.preventDefault(); event.stopPropagation()
    if (sending.current || !preview || preview.blocked || preview.create_count === 0) return
    sending.current = true; setSaving(true); setError(null)
    const controller = new AbortController(); mutation.current = controller
    try {
      const payload = { ...input, preview_token: preview.preview_token }
      const created = mode === 'single' ? [await createDistributionPort(payload, controller.signal)] : (await createPortRange(payload, controller.signal)).created
      if (!controller.signal.aborted) onCreated(created)
    } catch (cause) {
      if (!controller.signal.aborted) {
        setError(message(cause)); setChecked(null); setRetry(value => value + 1)
      }
    } finally { sending.current = false; if (!controller.signal.aborted) setSaving(false) }
  }
  const title = initialMode === 'single' ? 'Nuevo puerto de distribución' : 'Crear puertos masivamente'
  return createPortal(<dialog ref={dialog} aria-labelledby={`${id}-title`} className="distribution-theme port-create-dialog quick-dialog fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-2xl overflow-y-auto rounded-2xl border border-purple-500/25 bg-[#0b1426] p-5 text-slate-100 shadow-2xl backdrop:bg-slate-950/80"
    onCancel={event => { event.preventDefault(); event.stopPropagation(); if (!sending.current) onClose() }}>
    <h2 id={`${id}-title`} className="text-xl font-bold text-purple-200">{title}</h2>
    <p className="mt-2 text-sm">Equipo: <strong>{deviceName}</strong></p>
    {circuitContext && <p className="mt-2 text-sm text-slate-300">Los puertos confirmados permanecen registrados aunque canceles el circuito. El circuito se guarda por separado.</p>}
    <RequestState compact loading={loading} error={loadError} loadingText="Consultando nomenclaturas..." onRetry={() => setRetry(value => value + 1)} />
    {!allowed && <FeedbackMessage variant="error">Sin permiso para crear puertos.</FeedbackMessage>}
    {!loading && !loadError && catalog.length === 0 && <p className="mt-4 text-slate-300">No hay nomenclaturas activas. Solicita a Administración que configure una en Catálogos → Nomenclaturas de puertos.</p>}
    <form aria-label="Crear puertos de distribución" onSubmit={submit} noValidate className="mt-5 space-y-4">
      <fieldset disabled={saving || loading || Boolean(loadError) || !allowed} className="space-y-4">
        <legend className="sr-only">Nomenclatura y numeración de puertos</legend>
        <FormField id={`${id}-mode`} label="Modalidad de creación"><select id={`${id}-mode`} className="form-input" value={mode} onChange={event => { setMode(event.target.value as typeof mode); setError(null) }}>
          <option value="single">Individual</option><option value="complete">Crear rango completo</option><option value="missing">Completar puertos faltantes</option>
        </select></FormField>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField id={`${id}-nomenclature`} label="Nomenclatura" required><SearchableSelect id={`${id}-nomenclature`} label="Nomenclatura" value={nomenclatureId} onChange={value => {
            setNomenclatureId(value); setFormat(catalog.find(row => String(row.id) === value)?.formats[0] ?? 'N'); setError(null)
          }} options={catalog.filter(row => row.active).map(row => ({ value: String(row.id), label: `${row.name} (${row.prefix})` }))} placeholder="Selecciona una nomenclatura" emptyMessage="No hay nomenclaturas activas." noMatchMessage="No se encontraron nomenclaturas." /></FormField>
          <FormField id={`${id}-format`} label="Formato numérico" required><select id={`${id}-format`} className="form-input" disabled={!selected} value={format} onChange={event => { setFormat(event.target.value as NumberFormat); setError(null) }}>
            {(selected?.formats ?? []).map(value => <option key={value} value={value}>{value}</option>)}</select></FormField>
        </div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          {fixed.map((value, index) => <FormField key={index} id={`${id}-position-${index}`} label={`Posición ${format.split('/')[index]}`} required><input id={`${id}-position-${index}`} type="number" min="0" step="1" className="form-input" value={value} onChange={event => { setPositions(current => current.map((old, i) => i === index ? event.target.value : old)); setError(null) }} /></FormField>)}
          <FormField id={`${id}-start`} label={mode === 'single' ? 'Número del puerto' : 'Número inicial'} required><input id={`${id}-start`} className="form-input" type="number" min="0" step="1" value={start} onChange={event => { setStart(event.target.value); setError(null) }} /></FormField>
          {mode !== 'single' && <FormField id={`${id}-end`} label="Número final" required><input id={`${id}-end`} className="form-input" type="number" min="0" step="1" value={end} onChange={event => { setEnd(event.target.value); setError(null) }} /></FormField>}
        </div>
        {!validRange && <FeedbackMessage variant="error">Usa enteros no negativos y un rango ordenado de hasta 256 nombres solicitados.</FeedbackMessage>}
        <FormField id={`${id}-description`} label="Descripción (opcional)"><textarea id={`${id}-description`} rows={2} maxLength={10000} className="form-input" value={description} onChange={event => setDescription(event.target.value)} /></FormField>
      </fieldset>
      <div aria-live="polite" aria-busy={checking}>
        {checking && <p className="text-sm text-slate-300">Comprobando nombres con el servidor...</p>}
        {preview && <section aria-label="Vista previa de puertos" className="space-y-3 border-t border-purple-500/20 pt-4">
          <h3 className="font-semibold text-purple-200">{selected?.name} · {selected?.prefix} · {format}</h3>
          <p className="text-sm">Rango: {start}{mode !== 'single' && ` a ${end}`} · {preview.total} nombres · {preview.existing_count} existentes · {preview.create_count} por crear</p>
          {preview.blocked ? <FeedbackMessage variant="error">Hay {preview.existing_count} nombres en conflicto. El rango completo está bloqueado; no se creará ningún puerto.</FeedbackMessage>
            : mode === 'missing' && <p className="text-sm text-purple-200">Se conservarán {preview.existing_count} puertos existentes y se crearán {preview.create_count} puertos faltantes.</p>}
          {!preview.blocked && preview.create_count === 0 && <p className="text-sm text-slate-300">El rango ya está completo. No hay puertos faltantes.</p>}
          <ul className="grid max-h-48 grid-cols-1 gap-2 overflow-y-auto text-sm sm:grid-cols-2" aria-label="Nombres generados">{preview.names.map(row => <li key={row.name} className="flex items-center justify-between gap-2 rounded-lg bg-slate-900 px-3 py-2">
            <code className="break-all">{row.name}</code><span className={row.existing ? 'text-amber-300' : 'text-purple-300'}>{row.existing ? (mode === 'missing' ? 'Conservado' : 'Existente') : 'Nuevo'}</span>
          </li>)}</ul>
        </section>}
      </div>
      {error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}
      <div className="flex flex-wrap justify-end gap-3 border-t border-purple-500/20 pt-4">
        <button type="button" className="button-secondary rounded-full" disabled={saving || checking || !valid} onClick={() => { setError(null); setRetry(value => value + 1) }}>Comprobar de nuevo</button>
        <button type="button" className="button-secondary rounded-full" disabled={saving} onClick={onClose}>Cancelar</button>
        <button type="submit" className="button-primary button-primary--blue rounded-full" disabled={saving || checking || !preview || preview.blocked || preview.create_count === 0}>{saving ? 'Creando...' : 'Crear puertos'}</button>
      </div>
    </form>
  </dialog>, document.body)
}
