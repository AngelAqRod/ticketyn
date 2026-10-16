import { CatalogAdmin } from '../components/CatalogAdmin'
import { RequestState } from '../components/RequestState'
import { FeedbackMessage } from '../components/FeedbackMessage'
import { ApiError } from '../api/client'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Hash, Save } from 'lucide-react'
import { PageHeading } from '../components/PageHeading'
import { FormField } from '../components/FormField'
import { getTicketNumberConfig, updateTicketNumberConfig } from '../api/settings'
import type { TicketNumberConfig, TicketNumberChanges } from '../types/settings'

export function Settings() {
  const [changes, setChanges] = useState(false)
  const [internals, setInternals] = useState(false)
  const [activations, setActivations] = useState(false), [reasons, setReasons] = useState(false)
  return <div className="noc-settings"><PageHeading title="Configuración" description="Numeración de tickets, activaciones y motivos de baja." /><NumberingSettings /><section className="panel noc-panel mt-5 p-5"><button className="button-secondary noc-section-title" aria-expanded={changes} onClick={() => setChanges(!changes)}>Numeración de cambios</button>{changes && <div className="mt-4"><NumberingSettings changeControl /></div>}</section><section className="panel noc-panel mt-5 p-5"><button className="button-secondary noc-section-title" aria-expanded={internals} onClick={() => setInternals(!internals)}>Numeración de tickets internos</button>{internals && <div className="mt-4"><NumberingSettings internal /></div>}</section><section className="panel noc-panel mt-5 p-5"><button className="button-secondary noc-section-title" aria-expanded={activations} onClick={() => setActivations(!activations)}>Numeración de activaciones</button>{activations && <div className="mt-4"><NumberingSettings activation /></div>}</section><section className="panel noc-panel mt-5 p-5"><button className="button-secondary noc-section-title" aria-expanded={reasons} onClick={() => setReasons(!reasons)}>Motivos de baja</button>{reasons && <div className="mt-4"><CatalogAdmin kind="deactivation-reasons" embedded /></div>}</section></div>
}

function NumberingSettings({ activation = false, internal = false, changeControl = false }: { activation?: boolean; internal?: boolean; changeControl?: boolean }) {
  const [config, setConfig] = useState<TicketNumberConfig | null>(null)
  const [prefix, setPrefix] = useState('')
  const [separator, setSeparator] = useState('')
  const [nextNumber, setNextNumber] = useState('')
  const [padding, setPadding] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [apiInvalidFields, setApiInvalidFields] = useState<string[]>([])
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
    setLoading(true); setError(null); setApiInvalidFields([])
    getTicketNumberConfig(controller.signal, activation, internal, changeControl).then((data) => {
      if (!controller.signal.aborted) { populate(data); setLoading(false) }
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) { setError(failure instanceof Error ? failure.message : 'No se pudo cargar la configuración.'); setLoading(false) }
    })
    return () => controller.abort()
  }, [retry, activation, internal, changeControl])
  const number = Number(nextNumber), width = Number(padding)
  const validNumber = nextNumber !== '' && Number.isInteger(number) && number > 0 && number <= 2147483647
  const validPadding = padding !== '' && Number.isInteger(width) && width >= 0 && width <= 20
  const preview = validNumber && validPadding ? `${prefix}${separator}${String(number).padStart(width, '0')}` : '—'
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!config || sending.current) return
    setSuccess(false); setError(null); setApiInvalidFields([])
    if (!validNumber || !validPadding) { setError('Introduce un próximo número entero positivo (máximo 2147483647) y un padding entero entre 0 y 20.'); return }
    const values = { prefix, separator, next_number: number, padding: width }
    const changes: TicketNumberChanges = {}
    for (const key of ['prefix', 'separator', 'next_number', 'padding'] as const) {
      if (values[key] !== config[key]) Object.assign(changes, { [key]: values[key] })
    }
    sending.current = true; setSaving(true)
    try {
      const saved = await updateTicketNumberConfig(changes, undefined, activation, internal, changeControl)
      if (alive.current) { populate(saved); setSuccess(true) }
    } catch (failure) {
      if (alive.current) { setError(failure instanceof Error ? failure.message : 'No se pudo guardar la configuración.'); setApiInvalidFields(failure instanceof ApiError ? failure.fields : []) }
    } finally { sending.current = false; if (alive.current) setSaving(false) }
  }
  return <>
    {loading ? <RequestState loading loadingText="Cargando configuración..." /> : !config ? <RequestState error={error} errorTitle="" onRetry={() => setRetry(retry + 1)} /> : <div className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
      <form className="form-surface noc-panel" aria-label={changeControl ? "Numeración de cambios" : internal ? "Numeración de tickets internos" : activation ? "Numeración de activaciones" : "Numeración de tickets"} onSubmit={submit} noValidate aria-busy={saving} aria-describedby={error ? (changeControl ? "change-number-settings-error" : internal ? "internal-number-settings-error" : activation ? "activation-number-settings-error" : "number-settings-error") : undefined}>
        <h2 className="noc-section-title mb-4 flex items-center gap-3 text-lg font-bold"><span className="icon-surface" aria-hidden="true"><Hash size={16} /></span>Numeración de {changeControl ? "cambios" : internal ? "tickets internos" : activation ? "activaciones" : "tickets"}</h2>
        <fieldset disabled={saving} className="grid gap-4 sm:grid-cols-2"><legend className="sr-only">Formato de referencia</legend>
          <FormField describedBy={error ? (changeControl ? "change-number-settings-error" : internal ? "internal-number-settings-error" : activation ? "activation-number-settings-error" : "number-settings-error") : undefined} invalid={apiInvalidFields.includes("prefix")} id={changeControl ? "change-number-prefix" : internal ? "internal-number-prefix" : activation ? "activation-number-prefix" : "number-prefix"} label="Prefijo"><input id={changeControl ? "change-number-prefix" : internal ? "internal-number-prefix" : activation ? "activation-number-prefix" : "number-prefix"} className="form-input" value={prefix} onChange={(event) => { setPrefix(event.target.value); setSuccess(false) }} /></FormField>
          <FormField describedBy={error ? (changeControl ? "change-number-settings-error" : internal ? "internal-number-settings-error" : activation ? "activation-number-settings-error" : "number-settings-error") : undefined} invalid={apiInvalidFields.includes("separator")} id={changeControl ? "change-number-separator" : internal ? "internal-number-separator" : activation ? "activation-number-separator" : "number-separator"} label="Separador"><input id={changeControl ? "change-number-separator" : internal ? "internal-number-separator" : activation ? "activation-number-separator" : "number-separator"} className="form-input" value={separator} onChange={(event) => { setSeparator(event.target.value); setSuccess(false) }} /></FormField>
          <FormField describedBy={error ? (changeControl ? "change-number-settings-error" : internal ? "internal-number-settings-error" : activation ? "activation-number-settings-error" : "number-settings-error") : undefined} invalid={(Boolean(error) && !validNumber) || apiInvalidFields.includes("next_number")} id={changeControl ? "change-number-next" : internal ? "internal-number-next" : activation ? "activation-number-next" : "number-next"} label="Próximo número"><input id={changeControl ? "change-number-next" : internal ? "internal-number-next" : activation ? "activation-number-next" : "number-next"} type="number" min="1" max="2147483647" step="1" className="form-input" value={nextNumber} onChange={(event) => { setNextNumber(event.target.value); setSuccess(false) }} /></FormField>
          <FormField describedBy={error ? (changeControl ? "change-number-settings-error" : internal ? "internal-number-settings-error" : activation ? "activation-number-settings-error" : "number-settings-error") : undefined} invalid={(Boolean(error) && !validPadding) || apiInvalidFields.includes("padding")} id={changeControl ? "change-number-padding" : internal ? "internal-number-padding" : activation ? "activation-number-padding" : "number-padding"} label="Longitud / Padding"><input id={changeControl ? "change-number-padding" : internal ? "internal-number-padding" : activation ? "activation-number-padding" : "number-padding"} type="number" min="0" max="20" step="1" className="form-input" value={padding} onChange={(event) => { setPadding(event.target.value); setSuccess(false) }} /></FormField>
        </fieldset>
        <p className="mt-3 text-xs leading-5 text-muted">Prefijo y separador pueden estar vacíos. El separador admite varios caracteres. Padding agrega ceros a la izquierda sin recortar el número.</p>
        {error && <FeedbackMessage id={changeControl ? "change-number-settings-error" : internal ? "internal-number-settings-error" : activation ? "activation-number-settings-error" : "number-settings-error"} variant="error" className="mt-4">{error}</FeedbackMessage>}
        {success && <FeedbackMessage variant="success" className="mt-4">Configuración guardada correctamente.</FeedbackMessage>}
        <div className="mt-5 flex justify-end border-t border-slate-200 pt-4"><button type="submit" className="button-primary" disabled={saving}><Save size={15} aria-hidden="true" />{saving ? 'Guardando...' : 'Guardar cambios'}</button></div>
      </form>
      <aside className="noc-settings-preview rounded-xl p-6 text-white" aria-label={changeControl ? "Vista previa de referencia de cambio" : internal ? "Vista previa de referencia de ticket interno" : activation ? "Vista previa de referencia de activación" : "Vista previa de referencia"}>
        <p className="text-xs font-semibold tracking-wide text-blue-200 uppercase">Próxima referencia · Vista previa</p>
        <output className="mt-4 block break-all font-mono text-3xl font-bold" aria-label={internal ? "Próxima referencia de ticket interno" : activation ? "Próxima referencia de activación" : "Próxima referencia"}>{preview}</output>
        <p className="mt-5 border-t border-white/20 pt-4 text-sm leading-6 text-blue-100">Los cambios afectan únicamente a {internal ? "los tickets internos" : activation ? "las activaciones" : "los tickets"} creados posteriormente.</p>
        <p className="mt-3 text-xs leading-5 text-blue-200">Las referencias existentes son inmutables. Esta vista previa no crea registros ni consume números.</p>
      </aside>
    </div>}
  </>
}
