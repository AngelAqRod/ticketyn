import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Hash, Save, CheckCircle2 } from 'lucide-react'
import { PageHeading } from '../components/PageHeading'
import { FormField } from '../components/FormField'
import { getTicketNumberConfig, updateTicketNumberConfig } from '../api/settings'
import type { TicketNumberConfig, TicketNumberChanges } from '../types/settings'

export function Settings() {
  const [config, setConfig] = useState<TicketNumberConfig | null>(null)
  const [prefix, setPrefix] = useState('')
  const [separator, setSeparator] = useState('')
  const [nextNumber, setNextNumber] = useState('')
  const [padding, setPadding] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [retry, setRetry] = useState(0)
  const sending = useRef(false)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  function populate(data: TicketNumberConfig) {
    setConfig(data); setPrefix(data.prefix); setSeparator(data.separator)
    setNextNumber(String(data.next_number)); setPadding(String(data.padding))
  }
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(null)
    getTicketNumberConfig(controller.signal).then((data) => {
      if (!controller.signal.aborted) { populate(data); setLoading(false) }
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) { setError(failure instanceof Error ? failure.message : 'No se pudo cargar la configuración.'); setLoading(false) }
    })
    return () => controller.abort()
  }, [retry])
  const number = Number(nextNumber), width = Number(padding)
  const validNumber = nextNumber !== '' && Number.isInteger(number) && number > 0 && number <= 2147483647
  const validPadding = padding !== '' && Number.isInteger(width) && width >= 0 && width <= 20
  const preview = validNumber && validPadding ? `${prefix}${separator}${String(number).padStart(width, '0')}` : '—'
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!config || sending.current) return
    setSuccess(false); setError(null)
    if (!validNumber || !validPadding) { setError('Introduce un próximo número entero positivo (máximo 2147483647) y un padding entero entre 0 y 20.'); return }
    const values = { prefix, separator, next_number: number, padding: width }
    const changes: TicketNumberChanges = {}
    for (const key of ['prefix', 'separator', 'next_number', 'padding'] as const) {
      if (values[key] !== config[key]) Object.assign(changes, { [key]: values[key] })
    }
    sending.current = true; setSaving(true)
    try {
      const saved = await updateTicketNumberConfig(changes)
      if (alive.current) { populate(saved); setSuccess(true) }
    } catch (failure) {
      if (alive.current) setError(failure instanceof Error ? failure.message : 'No se pudo guardar la configuración.')
    } finally { sending.current = false; if (alive.current) setSaving(false) }
  }
  return <>
    <PageHeading title="Configuración" description="Personaliza la numeración de tickets de esta instalación." />
    {loading ? <p role="status" className="panel p-5">Cargando configuración...</p> : !config ? <div className="panel p-5"><p role="alert">{error}</p><button type="button" className="button-secondary mt-3" onClick={() => setRetry(retry + 1)}>Reintentar</button></div> : <div className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
      <form className="form-surface" aria-label="Numeración de tickets" onSubmit={submit} noValidate aria-busy={saving}>
        <h2 className="mb-4 flex items-center gap-2 text-lg font-bold"><Hash size={20} aria-hidden="true" />Numeración de tickets</h2>
        <fieldset disabled={saving} className="grid gap-4 sm:grid-cols-2"><legend className="sr-only">Formato de referencia</legend>
          <FormField id="number-prefix" label="Prefijo"><input id="number-prefix" className="form-input" value={prefix} onChange={(event) => { setPrefix(event.target.value); setSuccess(false) }} /></FormField>
          <FormField id="number-separator" label="Separador"><input id="number-separator" className="form-input" value={separator} onChange={(event) => { setSeparator(event.target.value); setSuccess(false) }} /></FormField>
          <FormField id="number-next" label="Próximo número"><input id="number-next" type="number" min="1" max="2147483647" step="1" className="form-input" value={nextNumber} onChange={(event) => { setNextNumber(event.target.value); setSuccess(false) }} /></FormField>
          <FormField id="number-padding" label="Longitud / Padding"><input id="number-padding" type="number" min="0" max="20" step="1" className="form-input" value={padding} onChange={(event) => { setPadding(event.target.value); setSuccess(false) }} /></FormField>
        </fieldset>
        <p className="mt-3 text-xs leading-5 text-muted">Prefijo y separador pueden estar vacíos. El separador admite varios caracteres. Padding agrega ceros a la izquierda sin recortar el número.</p>
        {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>}
        {success && <p role="status" className="mt-4 flex items-center gap-2 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900"><CheckCircle2 size={16} aria-hidden="true" />Configuración guardada correctamente.</p>}
        <div className="mt-5 flex justify-end border-t border-slate-200 pt-4"><button type="submit" className="button-primary" disabled={saving}><Save size={15} aria-hidden="true" />{saving ? 'Guardando...' : 'Guardar cambios'}</button></div>
      </form>
      <aside className="rounded-xl bg-[var(--navy)] p-6 text-white" aria-label="Vista previa de referencia">
        <p className="text-xs font-semibold tracking-wide text-blue-200 uppercase">Próxima referencia · Vista previa</p>
        <output className="mt-4 block break-all font-mono text-3xl font-bold" aria-label="Próxima referencia">{preview}</output>
        <p className="mt-5 border-t border-white/20 pt-4 text-sm leading-6 text-blue-100">Los cambios afectan únicamente a los tickets creados posteriormente.</p>
        <p className="mt-3 text-xs leading-5 text-blue-200">Las referencias existentes son inmutables. Esta vista previa no crea tickets ni consume números.</p>
      </aside>
    </div>}
  </>
}
