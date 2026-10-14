import { FileDown } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { getJson } from '../api/client'
import { Link, useParams } from 'react-router'
import { listResponsibles } from '../api'
import { getActivation, listActivationInterventions, createActivationIntervention, downloadActivationReport } from '../api/fms'
import type { ActivationIntervention, Operation } from '../types/fms'
import type { Customer, NamedCatalog } from '../types/catalog'
import { ticketynDateTimeValue, ticketynDateTimeToIso, ticketynTimezone } from '../lib/datetime'
import { capacityLabel } from '../types/fms'
import { formatDate } from '../lib/format'
import { PageHeading } from '../components/PageHeading'
import { FormField } from '../components/FormField'
import { RequestState } from '../components/RequestState'
import { FeedbackMessage } from '../components/FeedbackMessage'
import { SearchableSelect } from '../components/SearchableSelect'

export function ActivationDetail() {
  const id = Number(useParams().id), [activation, setActivation] = useState<Operation | null>(null), [items, setItems] = useState<ActivationIntervention[]>([]), [people, setPeople] = useState<NamedCatalog[]>([])
  const exportingRef = useRef(false)
  const [exporting, setExporting] = useState(false), [exportError, setExportError] = useState<string | null>(null)
  async function exportPdf() {
    if (exportingRef.current) return
    exportingRef.current = true; setExporting(true); setExportError(null)
    try { await downloadActivationReport(id) }
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
  return <><PageHeading title={activation.reference ?? 'Activación'} description="Activación e intervenciones técnicas, independientes de tickets." action={<button type="button" className="button-secondary" disabled={exporting} onClick={exportPdf}><FileDown size={16} aria-hidden="true" />Exportar PDF</button>} />
    {exporting && <RequestState loading compact loadingText="Generando archivo..." className="mb-3" />}
    {exportError && <FeedbackMessage variant="error" className="mb-3">{exportError}</FeedbackMessage>}
    <section className="panel mb-4 p-5" aria-label="Información de activación"><dl className="grid gap-3 sm:grid-cols-2"><div><dt className="text-xs text-muted">Circuito</dt><dd><Link to={`/circuits/${activation.circuit_id}`}>{activation.circuit.circuit_code}</Link></dd></div><div><dt className="text-xs text-muted">Descripción del circuito</dt><dd className="[overflow-wrap:anywhere] text-sm">{activation.circuit.description?.trim() || 'Sin descripción'}</dd></div><div><dt className="text-xs text-muted">Nodo</dt><dd className="text-sm">{activation.node?.name ?? 'Sin registrar'}</dd></div><div><dt className="text-xs text-muted">Sector</dt><dd className="text-sm">{activation.sector?.name ?? 'Sin registrar'}</dd></div><div><dt className="text-xs text-muted">Cliente</dt><dd className="text-sm">{customer?.name}</dd></div><div><dt className="text-xs text-muted">Fecha efectiva de activación</dt><dd className="text-sm">{formatDate(activation.effective_at, ticketynTimezone)}</dd></div><div><dt className="text-xs text-muted">Tipo de servicio</dt><dd className="[overflow-wrap:anywhere] text-sm">{activation.service_type_name || 'Sin registrar'}</dd></div><div><dt className="text-xs text-muted">CPE de activación</dt><dd className="[overflow-wrap:anywhere] text-sm">{activation.cpe_activation || 'Sin registrar'}</dd></div><div><dt className="text-xs text-muted">Capacidad inicial</dt><dd className="text-sm">{capacityLabel(activation.initial_capacity, activation.initial_capacity_unit)}</dd></div><div><dt className="text-xs text-muted">Responsable</dt><dd className="text-sm">{activation.responsible.name}</dd></div></dl></section>
    {success && <FeedbackMessage variant="success">Intervención registrada correctamente.</FeedbackMessage>}
    <section className="panel p-5" aria-labelledby="activation-log-title"><div className="mb-3 flex flex-wrap items-center justify-between gap-3"><h2 id="activation-log-title" className="section-label">Bitácora de activación</h2><button className="button-primary" onClick={() => setShow(true)}>Nueva intervención</button></div>{!items.length ? <RequestState compact empty emptyTitle="Sin intervenciones registradas." /> : <ol className="space-y-3" aria-label="Intervenciones de activación">{items.map((item) => <li key={item.id} className="border-b border-slate-100 pb-3"><p className="text-xs text-muted">{formatDate(item.occurred_at, ticketynTimezone)} · {item.responsible.name}</p><p className="mt-2 whitespace-pre-wrap [overflow-wrap:anywhere] text-sm">{item.content}</p></li>)}</ol>}</section>
    <div className="pagination-bar"><p className="text-xs text-muted">Página {Math.floor(offset / 50) + 1}</p><div className="flex gap-2"><button className="button-secondary" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 50))}>Anterior</button><button className="button-secondary" disabled={items.length < 50} onClick={() => setOffset(offset + 50)}>Siguiente</button></div></div>
    {show && <ActivationInterventionModal id={id} people={people} onCancel={() => setShow(false)} onSaved={() => { setShow(false); setOffset(0); setSuccess(true); setRefresh(refresh + 1) }} />}</>
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
  return <dialog ref={dialog} className="quick-dialog fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto bg-white p-5 text-ink backdrop:bg-slate-900/30" aria-labelledby="activation-intervention-title" onCancel={(event) => { event.preventDefault(); if (!sending.current) onCancel() }}><h2 id="activation-intervention-title" className="mb-4 text-xl font-semibold">Nueva intervención</h2><form onSubmit={submit} aria-label="Registrar intervención de activación" aria-describedby={error ? 'activation-intervention-error' : undefined}><fieldset disabled={saving} className="space-y-3"><FormField id="activation-intervention-date" label="Fecha y hora de intervención" required><input id="activation-intervention-date" className="form-input" type="datetime-local" required value={date} onChange={(event) => setDate(event.target.value)} /></FormField><FormField id="activation-intervention-person" label="Responsable" required><SearchableSelect placeholder="Selecciona una opción" emptyMessage="No hay registros disponibles." noMatchMessage="Sin coincidencias." required id="activation-intervention-person" label="Responsable" value={person} onChange={setPerson} options={people.map((item) => ({ value: String(item.id), label: item.name }))} /></FormField><FormField id="activation-intervention-content" label="Descripción" required><textarea id="activation-intervention-content" className="form-input" required maxLength={10000} value={content} onChange={(event) => setContent(event.target.value)} /></FormField></fieldset>{error && <FeedbackMessage id="activation-intervention-error" variant="error">{error}</FeedbackMessage>}<div className="mt-4 flex justify-end gap-2"><button className="button-secondary" type="button" disabled={saving} onClick={onCancel}>Cancelar</button><button className="button-primary" type="submit" disabled={saving}>{saving ? 'Guardando...' : 'Registrar intervención'}</button></div></form></dialog>
}
