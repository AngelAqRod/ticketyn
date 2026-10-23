import { operationalChoice } from '../lib/responsibles'
import { Can } from '../auth/permissions'
import { PaginationBar } from '../components/PaginationBar'
import { FileDown, Zap, Cpu, History, Plus } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { getJson } from '../api/client'
import { Link, useParams } from 'react-router'
import { listResponsibles } from '../api'
import { getActivation, listActivationInterventions, createActivationIntervention, downloadActivationReport, downloadCustomerActivationReport } from '../api/fms'
import type { ActivationIntervention, Operation } from '../types/fms'
import type { Customer, NamedCatalog } from '../types/catalog'
import { ticketynDateTimeValue, ticketynDateTimeToIso, ticketynTimezone } from '../lib/datetime'
import { capacityLabel, activationDistributionLabel } from '../types/fms'
import { formatDate } from '../lib/format'
import { PageHeading } from '../components/PageHeading'
import { FormField } from '../components/FormField'
import { RequestState } from '../components/RequestState'
import { FeedbackMessage } from '../components/FeedbackMessage'
import { SearchableSelect } from '../components/SearchableSelect'
import { ActivationNotificationActions } from '../components/ActivationNotificationActions'

export function ActivationDetail() {
  const id = Number(useParams().id), [activation, setActivation] = useState<Operation | null>(null), [items, setItems] = useState<ActivationIntervention[]>([]), [people, setPeople] = useState<NamedCatalog[]>([])
  const exportingRef = useRef(false)
  const [exporting, setExporting] = useState(false), [exportError, setExportError] = useState<string | null>(null)
  async function exportPdf(customer = false) {
    if (exportingRef.current) return
    exportingRef.current = true; setExporting(true); setExportError(null)
    try { await (customer ? downloadCustomerActivationReport(id) : downloadActivationReport(id)) }
    catch (failure) { setExportError(failure instanceof Error ? failure.message : 'No se pudo exportar la activación.') }
    finally { exportingRef.current = false; setExporting(false) }
  }
  const [customer, setCustomer] = useState<Customer | null>(null)
  const [offset, setOffset] = useState(0), [loading, setLoading] = useState(true), [error, setError] = useState<string | null>(null), [refresh, setRefresh] = useState(0), [show, setShow] = useState(false)
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null)
    Promise.all([getActivation(id, controller.signal).then(async (activation) => ({ activation, customer: await getJson<Customer>(`/api/customers/${activation.circuit.customer_id}`, controller.signal) })), listActivationInterventions(id, offset, controller.signal), listResponsibles(controller.signal)]).then(([a, rows, p]) => { if (!controller.signal.aborted) { setActivation(a.activation); setCustomer(a.customer); setItems(rows); setPeople(p); setLoading(false) } }).catch((failure: unknown) => { if (!controller.signal.aborted) { setError(failure instanceof Error ? failure.message : 'No se pudo cargar la activación.'); setLoading(false) } })
    return () => controller.abort()
  }, [id, offset, refresh])
  const [success, setSuccess] = useState(false)
  if (loading || error || !activation) return <RequestState loading={loading} error={error} onRetry={() => setRefresh(refresh + 1)} />
  return <>
    <PageHeading
      title={activation.reference ?? 'Activación'}
      description="Activación e intervenciones técnicas, independientes de tickets."
      telemetry={<span className="heading-telemetry"><span className="telemetry-value--emerald">{items.length}</span> intervenciones</span>}
      action={<div className="flex flex-wrap items-center gap-2">
        <Can permission="activations.export"><button type="button" className="button-secondary rounded-full shadow-xs text-xs" disabled={exporting} onClick={() => void exportPdf()}><FileDown size={14} aria-hidden="true" />Descargar PDF interno</button><button type="button" className="button-secondary rounded-full shadow-xs text-xs" disabled={exporting} onClick={() => void exportPdf(true)}><FileDown size={14} aria-hidden="true" />Descargar PDF para cliente</button></Can>
        <ActivationNotificationActions key={id} activationId={id} />
      </div>}
    />
    {exporting && <RequestState loading compact loadingText="Generando archivo..." className="mb-3 workspace-caption" />}
    {exportError && <FeedbackMessage variant="error" className="mb-3">{exportError}</FeedbackMessage>}
    {success && <FeedbackMessage variant="success" className="mb-3">Intervención registrada correctamente.</FeedbackMessage>}

    <div className="grid gap-6 lg:grid-cols-2 mb-6">
      <section className="panel p-6 rounded-2xl bg-[#0b1426] border border-emerald-500/20 shadow-xl" aria-label="Información de activación">
        <div className="flex items-center gap-2 border-b border-emerald-500/15 pb-3 mb-4">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs" aria-hidden="true">
            <Zap size={14} />
          </span>
          <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">Información de activación</h2>
        </div>
        <dl className="grid gap-4 sm:grid-cols-2 text-xs">
          <div>
            <dt className="font-mono text-xs uppercase tracking-wider text-slate-400">Circuito</dt>
            <dd className="mt-1 font-mono font-bold text-sky-400 text-sm">
              <Can permission="circuits.view" fallback={activation.circuit.circuit_code}>
                <Link to={`/circuits/${activation.circuit_id}`} className="hover:text-sky-300 hover:underline">{activation.circuit.circuit_code}</Link>
              </Can>
            </dd>
          </div>
          <div>
            <dt className="font-mono text-xs uppercase tracking-wider text-slate-400">Cliente</dt>
            <dd className="mt-1 text-white font-semibold text-sm">{customer?.name ?? '—'}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="font-mono text-xs uppercase tracking-wider text-slate-400">Descripción del circuito</dt>
            <dd className="mt-1 [overflow-wrap:anywhere] text-slate-200 text-sm">{activation.circuit.description?.trim() || 'Sin descripción'}</dd>
          </div>
          <div>
            <dt className="font-mono text-xs uppercase tracking-wider text-slate-400">Nodo</dt>
            <dd className="mt-1 font-mono text-slate-300 text-sm">{activation.node?.name ?? 'Sin registrar'}</dd>
          </div>
          <div>
            <dt className="font-mono text-xs uppercase tracking-wider text-slate-400">Sector</dt>
            <dd className="mt-1 font-mono text-slate-300 text-sm">{activation.sector?.name ?? 'Sin registrar'}</dd>
          </div>
          <div>
            <dt className="font-mono text-xs uppercase tracking-wider text-slate-400">Equipo de distribución</dt>
            <dd className="mt-1 text-slate-300 text-sm [overflow-wrap:anywhere]">{activationDistributionLabel(activation, 'distribution_device_name')}</dd>
          </div>
          <div>
            <dt className="font-mono text-xs uppercase tracking-wider text-slate-400">Puerto</dt>
            <dd className="mt-1 text-slate-300 text-sm [overflow-wrap:anywhere]">{activationDistributionLabel(activation, 'distribution_port_name')}</dd>
          </div>
          <div>
            <dt className="font-mono text-xs uppercase tracking-wider text-slate-400">Fecha efectiva de activación</dt>
            <dd className="mt-1 font-mono text-slate-300 text-sm">{formatDate(activation.effective_at, ticketynTimezone)}</dd>
          </div>
          <div>
            <dt className="font-mono text-xs uppercase tracking-wider text-slate-400">Tipo de servicio</dt>
            <dd className="mt-1 font-mono text-emerald-300 text-sm">{activation.service_type_name || 'Sin registrar'}</dd>
          </div>
          <div>
            <dt className="font-mono text-xs uppercase tracking-wider text-slate-400">Capacidad inicial</dt>
            <dd className="mt-1">
              <span className="font-mono font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/25 px-2.5 py-0.5 rounded-md text-xs inline-block">
                {capacityLabel(activation.initial_capacity, activation.initial_capacity_unit)}
              </span>
            </dd>
          </div>
          <div>
            <dt className="font-mono text-xs uppercase tracking-wider text-slate-400">Responsable</dt>
            <dd className="mt-1 text-slate-200 text-sm">{activation.responsible.name}</dd>
          </div>
        </dl>
      </section>

      <section className="panel p-6 rounded-2xl bg-[#0b1426] border border-emerald-500/20 shadow-xl flex flex-col gap-4" aria-labelledby="activation-notes-title">
        <div className="flex items-center gap-2 border-b border-emerald-500/15 pb-3">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs" aria-hidden="true">
            <Cpu size={14} />
          </span>
          <h2 id="activation-notes-title" className="text-xs font-bold font-mono text-white uppercase tracking-wider">Notas internas de activación</h2>
        </div>
        <div>
          <span className="block font-mono text-xs uppercase tracking-wider text-slate-400 mb-1.5">CPE de activación</span>
          <div className="p-3 rounded-xl bg-[#070d1a] border border-slate-800 text-sky-200 font-mono text-xs [overflow-wrap:anywhere]">
            {activation.cpe_activation || 'Sin registrar'}
          </div>
        </div>
        <div className="flex-1 flex flex-col">
          <span className="block font-mono text-xs uppercase tracking-wider text-slate-400 mb-1.5">Notas técnicas</span>
          <div className="p-3.5 rounded-xl bg-[#070d1a] border border-slate-800 flex-1 min-h-[90px]">
            <p className={`text-sm whitespace-pre-wrap [overflow-wrap:anywhere] font-mono ${activation.activation_notes ? 'text-slate-200' : 'text-slate-500'}`}>
              {activation.activation_notes || 'Sin notas de activación.'}
            </p>
          </div>
        </div>
      </section>
    </div>

    <section className="panel p-6 rounded-2xl bg-[#0b1426] border border-emerald-500/20 shadow-xl mb-6" aria-labelledby="customer-activation-notes-title">
      <h2 id="customer-activation-notes-title" className="mb-3 text-xs font-bold font-mono text-white uppercase tracking-wider">Notas para cliente</h2>
      <p className="text-sm whitespace-pre-wrap [overflow-wrap:anywhere] font-mono text-slate-200">{activation.customer_activation_notes || 'Sin notas para cliente registradas.'}</p>
    </section>

    <section className="panel p-6 rounded-2xl bg-[#0b1426] border border-emerald-500/20 shadow-xl" aria-labelledby="activation-log-title">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-emerald-500/15 pb-3">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs" aria-hidden="true">
            <History size={14} />
          </span>
          <h2 id="activation-log-title" className="text-xs font-bold font-mono text-white uppercase tracking-wider">Bitácora de activación</h2>
        </div>
        <Can permission="activations.followup">
          <button className="button-primary button-primary--emerald rounded-full shadow-sm text-xs" onClick={() => setShow(true)}>
            <Plus size={14} aria-hidden="true" />
            Nueva intervención
          </button>
        </Can>
      </div>
      {!items.length ? (
        <RequestState compact empty emptyTitle="Sin intervenciones registradas." className="rounded-xl bg-[#070d1a] border border-slate-800/80 p-8 text-center text-slate-400 font-mono" />
      ) : (
        <ol className="space-y-3" aria-label="Intervenciones de activación">
          {items.map((item) => (
            <li key={item.id} className="p-4 rounded-xl bg-[#070d1a] border border-slate-800/80 hover:border-slate-700 transition-colors">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs font-mono">
                <span className="text-emerald-400 font-semibold">{formatDate(item.occurred_at, ticketynTimezone)}</span>
                <span className="text-slate-400">{item.responsible.name}</span>
              </div>
              <p className="mt-2 whitespace-pre-wrap [overflow-wrap:anywhere] text-sm text-slate-200 leading-relaxed font-mono">
                {item.content}
              </p>
            </li>
          ))}
        </ol>
      )}
      <div className="mt-4">
        <PaginationBar page={Math.floor(offset / 50) + 1} info={<p className="text-xs font-mono text-slate-400">Página {Math.floor(offset / 50) + 1}</p>} previousDisabled={!offset} nextDisabled={items.length < 50} onPrevious={() => setOffset(Math.max(0, offset - 50))} onNext={() => setOffset(offset + 50)} />
      </div>
    </section>

    {show && <Can permission="activations.followup"><ActivationInterventionModal id={id} people={people} onCancel={() => setShow(false)} onSaved={() => { setShow(false); setOffset(0); setSuccess(true); setRefresh(refresh + 1) }} /></Can>}
  </>
}

function ActivationInterventionModal({ id, people, onCancel, onSaved }: { id: number; people: NamedCatalog[]; onCancel: () => void; onSaved: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null), sending = useRef(false)
  const [date, setDate] = useState(ticketynDateTimeValue), [person, setPerson] = useState(''), [content, setContent] = useState(''), [error, setError] = useState<string | null>(null), [saving, setSaving] = useState(false)
  useEffect(() => { const element = dialog.current!, previous = document.activeElement; element.showModal(); element.querySelector('input')?.focus(); return () => { element.close(); if (previous instanceof HTMLElement && previous.isConnected) previous.focus() } }, [])
  async function submit(event: FormEvent) {
    event.preventDefault(); if (sending.current) return
    try {
      setError(null); if (!person || !content.trim()) throw new Error('Completa responsable y descripción.')
      const occurred_at = ticketynDateTimeToIso(date)
      sending.current = true; setSaving(true)
      await createActivationIntervention(id, { responsible_id: Number(person), occurred_at, content: content.trim() }); onSaved()
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'No se pudo registrar la intervención.') }
    finally { sending.current = false; setSaving(false) }
  }
  return <dialog ref={dialog} className="quick-dialog noc-modal fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto bg-[#0b1426] p-6 text-white border border-emerald-500/30 rounded-2xl shadow-2xl backdrop:bg-slate-950/70" aria-labelledby="activation-intervention-title" onCancel={(event) => { event.preventDefault(); if (!sending.current) onCancel() }}>
    <div className="flex items-center gap-2 border-b border-emerald-500/20 pb-3 mb-4">
      <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs" aria-hidden="true">
        <Plus size={14} />
      </span>
      <h2 id="activation-intervention-title" className="text-base font-bold font-mono text-white uppercase tracking-wider">Nueva intervención</h2>
    </div>
    <form onSubmit={submit} aria-label="Registrar intervención de activación" aria-describedby={error ? 'activation-intervention-error' : undefined}>
      <fieldset disabled={saving} className="space-y-3">
        <FormField id="activation-intervention-date" label="Fecha y hora de intervención" required>
          <input id="activation-intervention-date" className="form-input" type="datetime-local" required value={date} onChange={(event) => setDate(event.target.value)} />
        </FormField>
        <FormField id="activation-intervention-person" label="Responsable" required>
          <SearchableSelect placeholder="Selecciona una opción" emptyMessage="No hay registros disponibles." noMatchMessage="Sin coincidencias." required id="activation-intervention-person" label="Responsable" value={person} onChange={setPerson} options={people.filter(p => operationalChoice(p)).map((item) => ({ value: String(item.id), label: item.name }))} />
        </FormField>
        <FormField id="activation-intervention-content" label="Descripción" required>
          <textarea id="activation-intervention-content" className="form-input" required maxLength={10000} rows={4} value={content} onChange={(event) => setContent(event.target.value)} />
        </FormField>
      </fieldset>
      {error && <FeedbackMessage id="activation-intervention-error" variant="error" className="mt-3">{error}</FeedbackMessage>}
      <div className="mt-5 flex justify-end gap-2">
        <button className="button-secondary rounded-full" type="button" disabled={saving} onClick={onCancel}>Cancelar</button>
        <button className="button-primary button-primary--emerald rounded-full shadow-sm" type="submit" disabled={saving}>{saving ? 'Guardando...' : 'Registrar intervención'}</button>
      </div>
    </form>
  </dialog>
}
