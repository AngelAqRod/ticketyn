import { CpeConfiguration } from '../components/CpeConfiguration'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { updateCircuit } from '../api'
import { confirmDeactivation } from '../lib/catalogActions'
import { CircuitActions } from '../components/CircuitActions'
import { CircuitEditModal } from '../components/CircuitEditModal'
import { CatalogDeleteConfirmation } from '../components/CatalogDeleteConfirmation'
import { getCircuitDetail, listOperations } from '../api/fms'
import type { CircuitOperationalDetail, FmsKind, Operation } from '../types/fms'
import { capacityLabel } from '../types/fms'
import { formatDate } from '../lib/format'
import { ticketynTimezone } from '../lib/datetime'
import { PageHeading } from '../components/PageHeading'
import { RequestState } from '../components/RequestState'
import { FeedbackMessage } from '../components/FeedbackMessage'
import { OperationModal } from '../components/OperationModal'
import { OperationsTable } from '../components/OperationsTable'

export function CircuitDetail() {
  const navigate = useNavigate(), actionSending = useRef(false), actionRequest = useRef<AbortController | null>(null), fallbackFocus = useRef<HTMLButtonElement>(null)
  const [editing, setEditing] = useState(false), [deleting, setDeleting] = useState(false), [actionBusy, setActionBusy] = useState(false), [actionError, setActionError] = useState<string | null>(null), [actionNotice, setActionNotice] = useState<string | null>(null)
  const id = Number(useParams().id), [detail, setDetail] = useState<CircuitOperationalDetail | null>(null), [error, setError] = useState<string | null>(null), [loading, setLoading] = useState(true), [refresh, setRefresh] = useState(0), [success, setSuccess] = useState(false)
  useEffect(() => { actionRequest.current = null; actionSending.current = false; setActionBusy(false); setEditing(false); setDeleting(false); setActionError(null); setActionNotice(null); return () => actionRequest.current?.abort() }, [id])
  const [tab, setTab] = useState<'capacity-changes' | 'circuit-lifecycle' | 'cpe'>('capacity-changes'), [modal, setModal] = useState<FmsKind | null>(null)
  const [offsets, setOffsets] = useState({ 'capacity-changes': 0, 'circuit-lifecycle': 0 }), [items, setItems] = useState<Operation[]>([]), [historyLoading, setHistoryLoading] = useState(true), [historyError, setHistoryError] = useState<string | null>(null)
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null)
    getCircuitDetail(id, controller.signal).then((data) => { if (!controller.signal.aborted) { setDetail(data); setLoading(false) } }).catch((failure: unknown) => { if (!controller.signal.aborted) { setError(failure instanceof Error ? failure.message : 'No se pudo cargar el circuito.'); setLoading(false) } })
    return () => controller.abort()
  }, [id, refresh])
  const offset = tab === 'cpe' ? 0 : offsets[tab]
  useEffect(() => {
    if (tab === 'cpe') return
    const controller = new AbortController(); setHistoryLoading(true); setHistoryError(null)
    listOperations(tab, new URLSearchParams({ circuit_id: String(id), limit: '10', offset: String(offset) }), controller.signal).then((data) => { if (!controller.signal.aborted) { setItems(data); setHistoryLoading(false) } }).catch((failure: unknown) => { if (!controller.signal.aborted) { setHistoryError(failure instanceof Error ? failure.message : 'No se pudo cargar el historial.'); setHistoryLoading(false) } })
    return () => controller.abort()
  }, [id, tab, offset, refresh])
  if (!detail || detail.circuit.id !== id) return <RequestState loading={loading} error={error} onRetry={() => setRefresh(refresh + 1)} />
  const c = detail.circuit, a = detail.initial_activation
  const info = [['Código', c.circuit_code], ['Sector', c.sector?.name ?? 'Sin asignar'], ['Cliente', detail.customer.name], ['Nodo', c.node?.name ?? 'Sin asignar'], ['Modelo de CPE actual', c.cpe_model?.name ?? 'Sin asignar'], ['Tipo de servicio', c.service_type?.name ?? 'Sin asignar'], ['Descripción', c.description], ['Estado administrativo', c.active ? 'Activo' : 'Inactivo'], ['Fecha de creación', formatDate(c.created_at, ticketynTimezone)], ['Capacidad inicial', capacityLabel(c.initial_capacity, c.initial_capacity_unit)], ['Capacidad actual', capacityLabel(detail.current_capacity, detail.current_capacity_unit)]]
  async function toggle() {
    if (actionSending.current || (c.active && !confirmDeactivation())) return
    const request = new AbortController(); actionRequest.current = request
    actionSending.current = true; setActionBusy(true); setActionError(null); setActionNotice(null)
    try {
      const saved = await updateCircuit(c.id, { active: !c.active }, request.signal)
      if (!request.signal.aborted) { setDetail((old) => old ? { ...old, circuit: saved } : old); setActionNotice(saved.active ? 'Registro activado correctamente.' : 'Registro desactivado. Los tickets históricos conservan su referencia.') }
    } catch (failure) { if (!request.signal.aborted) setActionError(failure instanceof Error ? failure.message : 'No se pudo cambiar el estado administrativo.') }
    finally { if (actionRequest.current === request) { actionSending.current = false; if (!request.signal.aborted) setActionBusy(false) } }
  }
  return <>
    <PageHeading title={c.circuit_code} description="Información e historial operativo del circuito." action={<div className="flex flex-wrap justify-end gap-2"><CircuitActions circuit={c} disabled={actionBusy || loading || editing || deleting || Boolean(modal)} onEdit={() => { setActionError(null); setEditing(true) }} onToggle={() => void toggle()} onDelete={() => setDeleting(true)} /></div>} />
    <RequestState compact loading={loading} error={error} onRetry={() => setRefresh(refresh + 1)} />
    {actionError && <FeedbackMessage variant="error" className="mb-3">{actionError}</FeedbackMessage>}
    {actionNotice && <FeedbackMessage variant="success" className="mb-3">{actionNotice}</FeedbackMessage>}
    {success && <FeedbackMessage variant="success" className="mb-3">Operación registrada correctamente.</FeedbackMessage>}
    <div className="mb-5 grid gap-4 lg:grid-cols-2"><section className="panel p-5"><h2 className="section-label mb-4">Información general</h2><dl className="grid gap-3 sm:grid-cols-2">{info.map(([label, value]) => <div key={label} className="min-w-0"><dt className="text-xs text-muted">{label}</dt><dd className="[overflow-wrap:anywhere] text-sm">{value}</dd></div>)}</dl></section>
      <section className="panel p-5"><h2 className="section-label mb-4">Activación inicial</h2>{a ? <><p className="font-mono font-semibold">{a.reference}</p><p className="mt-2 text-sm">{formatDate(a.effective_at, ticketynTimezone)} · {a.responsible.name}</p><Link className="button-ghost mt-3" to={`/activations/${a.id}`}>Ver detalle y bitácora</Link></> : <><p className="text-sm text-muted">Sin registrar</p><button type="button" className="button-secondary mt-3" onClick={() => setModal('activations')}>Registrar activación</button></>}</section></div>
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3"><div className="segmented-control" role="group" aria-label="Historial del circuito"><button className="segment-button" aria-pressed={tab === 'capacity-changes'} onClick={() => setTab('capacity-changes')}>Capacidad</button><button className="segment-button" aria-pressed={tab === 'circuit-lifecycle'} onClick={() => setTab('circuit-lifecycle')}>Bajas / Reactivaciones</button><button className="segment-button" aria-pressed={tab === 'cpe'} onClick={() => setTab('cpe')}>Configuración CPE</button></div>{tab !== 'cpe' && <button ref={fallbackFocus} type="button" className="button-primary" disabled={actionBusy || loading} onClick={() => setModal(tab)}>Nueva operación</button>}</div>
    {tab === 'cpe' ? <CpeConfiguration key={id} circuitId={id} /> : <>
    {historyLoading || historyError || !items.length ? <RequestState loading={historyLoading} error={historyError} empty={!items.length} emptyTitle="Sin operaciones registradas." onRetry={() => setRefresh(refresh + 1)} /> : <OperationsTable showAssignments={false} kind={tab} items={items} />}
    <div className="pagination-bar"><p className="text-xs text-muted">Página {Math.floor(offset / 10) + 1} · 10 registros por página</p><div className="flex gap-2"><button className="button-secondary" disabled={historyLoading || offset === 0} onClick={() => setOffsets({ ...offsets, [tab]: Math.max(0, offset - 10) })}>Anterior</button><button className="button-secondary" disabled={historyLoading || Boolean(historyError) || items.length < 10} onClick={() => setOffsets({ ...offsets, [tab]: offset + 10 })}>Siguiente</button></div></div>
    </>}
    {editing && <CircuitEditModal circuit={c} onCancel={() => setEditing(false)} onSaved={(saved) => { setEditing(false); setDetail((old) => old ? { ...old, circuit: saved } : old); setActionNotice('Cambios guardados correctamente.'); setRefresh(refresh + 1) }} />}
    {deleting && <CatalogDeleteConfirmation item={c} fallbackFocus={fallbackFocus} onCancel={() => setDeleting(false)} onBusyChange={setActionBusy} onDeleted={() => navigate('/circuits', { state: { deletedCircuitCode: c.circuit_code } })} />}
    {modal && <OperationModal kind={modal} circuit={c} onCancel={() => setModal(null)} onSaved={() => { const savedKind = modal; setModal(null); setSuccess(true); if (savedKind === 'capacity-changes' || savedKind === 'circuit-lifecycle') setOffsets((current) => ({ ...current, [savedKind]: 0 })); setRefresh(refresh + 1) }} />}
  </>
}
