import { Can, usePermissions } from '../auth/permissions'
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
  const [tickets, setTickets] = useState(true)
  const [changes, setChanges] = useState(false)
  const [internals, setInternals] = useState(false)
  const [activations, setActivations] = useState(false)
  return (
    <div className="noc-settings space-y-5">
      <PageHeading
        title="Configuración"
        description="Numeración de tickets, cambios, incidencias internas y activaciones."
        telemetry={
          <span className="heading-telemetry">
            <span>Módulo:</span>
            <strong className="telemetry-value--slate">SISTEMA</strong>
            <span className="text-slate-600">·</span>
            <span>Ámbitos:</span>
            <strong className="telemetry-value--slate">4 Numeraciones</strong>
          </span>
        }
      />
      <Can permission="settings.ticket_number.view">
        <section className="panel noc-panel p-5 rounded-2xl bg-[#0b1426] border border-slate-700/60 shadow-xl">
          <button
            type="button"
            className="button-secondary noc-section-title rounded-full shadow-xs inline-flex items-center gap-2 text-xs font-mono font-bold uppercase tracking-wider"
            aria-expanded={tickets}
            onClick={() => setTickets(!tickets)}
          >
            <Hash size={14} className="text-slate-400" aria-hidden="true" />
            Numeración de tickets
          </button>
          {tickets && (
            <div className="mt-4 pt-4 border-t border-slate-700/60">
              <NumberingSettings />
            </div>
          )}
        </section>
      </Can>
      <Can permission="settings.change_number.view">
        <section className="panel noc-panel p-5 rounded-2xl bg-[#0b1426] border border-slate-700/60 shadow-xl">
          <button
            type="button"
            className="button-secondary noc-section-title rounded-full shadow-xs inline-flex items-center gap-2 text-xs font-mono font-bold uppercase tracking-wider"
            aria-expanded={changes}
            onClick={() => setChanges(!changes)}
          >
            <Hash size={14} className="text-slate-400" aria-hidden="true" />
            Numeración de cambios
          </button>
          {changes && (
            <div className="mt-4 pt-4 border-t border-slate-700/60">
              <NumberingSettings changeControl />
            </div>
          )}
        </section>
      </Can>
      <Can permission="settings.internal_ticket_number.view">
        <section className="panel noc-panel p-5 rounded-2xl bg-[#0b1426] border border-slate-700/60 shadow-xl">
          <button
            type="button"
            className="button-secondary noc-section-title rounded-full shadow-xs inline-flex items-center gap-2 text-xs font-mono font-bold uppercase tracking-wider"
            aria-expanded={internals}
            onClick={() => setInternals(!internals)}
          >
            <Hash size={14} className="text-slate-400" aria-hidden="true" />
            Numeración de tickets internos
          </button>
          {internals && (
            <div className="mt-4 pt-4 border-t border-slate-700/60">
              <NumberingSettings internal />
            </div>
          )}
        </section>
      </Can>
      <Can permission="settings.activation_number.view">
        <section className="panel noc-panel p-5 rounded-2xl bg-[#0b1426] border border-slate-700/60 shadow-xl">
          <button
            type="button"
            className="button-secondary noc-section-title rounded-full shadow-xs inline-flex items-center gap-2 text-xs font-mono font-bold uppercase tracking-wider"
            aria-expanded={activations}
            onClick={() => setActivations(!activations)}
          >
            <Hash size={14} className="text-slate-400" aria-hidden="true" />
            Numeración de activaciones
          </button>
          {activations && (
            <div className="mt-4 pt-4 border-t border-slate-700/60">
              <NumberingSettings activation />
            </div>
          )}
        </section>
      </Can>
    </div>
  )
}

function NumberingSettings({ activation = false, internal = false, changeControl = false }: { activation?: boolean; internal?: boolean; changeControl?: boolean }) {
  const editable=usePermissions().can("settings."+(changeControl?"change_number":internal?"internal_ticket_number":activation?"activation_number":"ticket_number")+".edit")
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
      <form className="form-surface noc-panel p-6 rounded-2xl bg-[#0b1426] border border-slate-700/60 shadow-xl" aria-label={changeControl ? "Numeración de cambios" : internal ? "Numeración de tickets internos" : activation ? "Numeración de activaciones" : "Numeración de tickets"} onSubmit={submit} noValidate aria-busy={saving} aria-describedby={error ? (changeControl ? "change-number-settings-error" : internal ? "internal-number-settings-error" : activation ? "activation-number-settings-error" : "number-settings-error") : undefined}>
        <div className="flex items-center gap-2 border-b border-slate-700/60 pb-2.5 mb-4">
          <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-slate-800/80 border border-slate-700/80 text-slate-300 text-xs" aria-hidden="true">
            <Hash size={13} />
          </span>
          <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
            Numeración de {changeControl ? "cambios" : internal ? "tickets internos" : activation ? "activaciones" : "tickets"}
          </h2>
        </div>
        <fieldset disabled={saving||!editable} className="grid gap-4 sm:grid-cols-2"><legend className="sr-only">Formato de referencia</legend>
          <FormField describedBy={error ? (changeControl ? "change-number-settings-error" : internal ? "internal-number-settings-error" : activation ? "activation-number-settings-error" : "number-settings-error") : undefined} invalid={apiInvalidFields.includes("prefix")} id={changeControl ? "change-number-prefix" : internal ? "internal-number-prefix" : activation ? "activation-number-prefix" : "number-prefix"} label="Prefijo"><input id={changeControl ? "change-number-prefix" : internal ? "internal-number-prefix" : activation ? "activation-number-prefix" : "number-prefix"} className="form-input font-mono" value={prefix} onChange={(event) => { setPrefix(event.target.value); setSuccess(false) }} /></FormField>
          <FormField describedBy={error ? (changeControl ? "change-number-settings-error" : internal ? "internal-number-settings-error" : activation ? "activation-number-settings-error" : "number-settings-error") : undefined} invalid={apiInvalidFields.includes("separator")} id={changeControl ? "change-number-separator" : internal ? "internal-number-separator" : activation ? "activation-number-separator" : "number-separator"} label="Separador"><input id={changeControl ? "change-number-separator" : internal ? "internal-number-separator" : activation ? "activation-number-separator" : "number-separator"} className="form-input font-mono" value={separator} onChange={(event) => { setSeparator(event.target.value); setSuccess(false) }} /></FormField>
          <FormField describedBy={error ? (changeControl ? "change-number-settings-error" : internal ? "internal-number-settings-error" : activation ? "activation-number-settings-error" : "number-settings-error") : undefined} invalid={(Boolean(error) && !validNumber) || apiInvalidFields.includes("next_number")} id={changeControl ? "change-number-next" : internal ? "internal-number-next" : activation ? "activation-number-next" : "number-next"} label="Próximo número"><input id={changeControl ? "change-number-next" : internal ? "internal-number-next" : activation ? "activation-number-next" : "number-next"} type="number" min="1" max="2147483647" step="1" className="form-input font-mono" value={nextNumber} onChange={(event) => { setNextNumber(event.target.value); setSuccess(false) }} /></FormField>
          <FormField describedBy={error ? (changeControl ? "change-number-settings-error" : internal ? "internal-number-settings-error" : activation ? "activation-number-settings-error" : "number-settings-error") : undefined} invalid={(Boolean(error) && !validPadding) || apiInvalidFields.includes("padding")} id={changeControl ? "change-number-padding" : internal ? "internal-number-padding" : activation ? "activation-number-padding" : "number-padding"} label="Longitud / Padding"><input id={changeControl ? "change-number-padding" : internal ? "internal-number-padding" : activation ? "activation-number-padding" : "number-padding"} type="number" min="0" max="20" step="1" className="form-input font-mono" value={padding} onChange={(event) => { setPadding(event.target.value); setSuccess(false) }} /></FormField>
        </fieldset>
        <p className="mt-3 text-xs leading-5 text-slate-400 font-mono">Prefijo y separador pueden estar vacíos. El separador admite varios caracteres. Padding agrega ceros a la izquierda sin recortar el número.</p>
        {error && <FeedbackMessage id={changeControl ? "change-number-settings-error" : internal ? "internal-number-settings-error" : activation ? "activation-number-settings-error" : "number-settings-error"} variant="error" className="mt-4">{error}</FeedbackMessage>}
        {success && <FeedbackMessage variant="success" className="mt-4">Configuración guardada correctamente.</FeedbackMessage>}
        {editable&&<div className="mt-5 flex justify-end border-t border-slate-700/60 pt-4"><button type="submit" className="button-primary button-primary--slate rounded-full shadow-sm" disabled={saving}><Save size={15} aria-hidden="true" />{saving ? 'Guardando...' : 'Guardar cambios'}</button></div>}
      </form>
      <aside className="noc-settings-preview rounded-2xl p-6 text-white bg-[#0b1426] border border-slate-700/60 shadow-xl self-start" aria-label={changeControl ? "Vista previa de referencia de cambio" : internal ? "Vista previa de referencia de ticket interno" : activation ? "Vista previa de referencia de activación" : "Vista previa de referencia"}>
        <div className="flex items-center gap-2 border-b border-slate-700/60 pb-2.5 mb-4">
          <span className="flex h-2 w-2 rounded-full bg-slate-400 shadow-[0_0_8px_rgba(148,163,184,0.6)]" aria-hidden="true" />
          <p className="text-xs font-bold font-mono tracking-wider text-slate-300 uppercase">Próxima referencia · Vista previa</p>
        </div>
        <output className="my-5 block break-all font-mono text-3xl font-bold text-white tracking-wider" style={{ textShadow: '0 0 20px rgba(148, 163, 184, 0.35)' }} aria-label={internal ? "Próxima referencia de ticket interno" : activation ? "Próxima referencia de activación" : "Próxima referencia"}>{preview}</output>
        <p className="border-t border-slate-700/60 pt-4 text-xs leading-relaxed text-slate-300">Los cambios afectan únicamente a {internal ? "los tickets internos" : activation ? "las activaciones" : "los tickets"} creados posteriormente.</p>
        <p className="mt-2 text-xs leading-relaxed text-slate-400 font-mono">Las referencias existentes son inmutables. Esta vista previa no crea registros ni consume números.</p>
      </aside>
    </div>}
  </>
}
