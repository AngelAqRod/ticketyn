import { Can, usePermissions } from '../auth/permissions'
import { PaginationBar } from '../components/PaginationBar'
import { CpeConfiguration } from '../components/CpeConfiguration'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { Network, Plus, Zap } from 'lucide-react'
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
  const access=usePermissions()
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
  const availableTabs=(['capacity-changes','circuit-lifecycle','cpe'] as const).filter(value=>access.can(value==='capacity-changes'?'capacity_changes.view':value==='circuit-lifecycle'?'lifecycle.view':'cpe.view'))
  const currentTab=availableTabs.includes(tab)?tab:availableTabs[0]
  const offset = currentTab && currentTab !== 'cpe' ? offsets[currentTab] : 0
  useEffect(() => {
    if (!currentTab || currentTab === 'cpe') return
    const controller = new AbortController(); setHistoryLoading(true); setHistoryError(null)
    listOperations(currentTab, new URLSearchParams({ circuit_id: String(id), limit: '10', offset: String(offset) }), controller.signal).then((data) => { if (!controller.signal.aborted) { setItems(data); setHistoryLoading(false) } }).catch((failure: unknown) => { if (!controller.signal.aborted) { setHistoryError(failure instanceof Error ? failure.message : 'No se pudo cargar el historial.'); setHistoryLoading(false) } })
    return () => controller.abort()
  }, [id, currentTab, offset, refresh])
  if (!detail || detail.circuit.id !== id) return <RequestState loading={loading} error={error} onRetry={() => setRefresh(refresh + 1)} />
  const c = detail.circuit, a = detail.initial_activation
  const info = [['Código', c.circuit_code], ['Sector', c.sector?.name ?? 'Sin asignar'], ['Cliente', detail.customer.name], ['Nodo', c.node?.name ?? 'Sin asignar'], ['IP de gestión CPE', c.cpe_management_ip || 'No asignada'], ['Modelo de CPE actual', c.cpe_model?.name ?? 'Sin asignar'], ['Tipo de servicio', c.service_type?.name ?? 'Sin asignar'], ['Descripción', c.description], ['Estado administrativo', c.active ? 'Activo' : 'Inactivo'], ['Fecha de creación', formatDate(c.created_at, ticketynTimezone)], ['Capacidad inicial', capacityLabel(c.initial_capacity, c.initial_capacity_unit)], ['Capacidad actual', capacityLabel(detail.current_capacity, detail.current_capacity_unit)]]
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
    <PageHeading
      title={c.circuit_code}
      description="Información e historial operativo del circuito."
      action={<div className="flex flex-wrap justify-end gap-2"><CircuitActions circuit={c} disabled={actionBusy || loading || editing || deleting || Boolean(modal)} onEdit={() => { setActionError(null); setEditing(true) }} onToggle={() => void toggle()} onDelete={() => setDeleting(true)} /></div>}
    />
    <RequestState compact className="workspace-caption" loading={loading} error={error} onRetry={() => setRefresh(refresh + 1)} />
    {actionError && <FeedbackMessage variant="error" className="mb-3">{actionError}</FeedbackMessage>}
    {actionNotice && <FeedbackMessage variant="success" className="mb-3">{actionNotice}</FeedbackMessage>}
    {success && <FeedbackMessage variant="success" className="mb-3">Operación registrada correctamente.</FeedbackMessage>}
    <div className="mb-5 grid items-start gap-4 lg:grid-cols-2">
      <section className="panel p-6 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl">
        <div className="flex items-center gap-2 border-b border-sky-500/15 pb-3 mb-4">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs" aria-hidden="true">
            <Network size={14} />
          </span>
          <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">Información general</h2>
        </div>
        <dl className="grid gap-x-6 gap-y-3.5 sm:grid-cols-2 text-xs">
          {info.map(([label, value]) => (
            <div key={label} className="min-w-0">
              <dt className="text-slate-400 font-mono uppercase tracking-wider text-[11px]">{label}</dt>
              <dd className="mt-1 [overflow-wrap:anywhere] text-white font-medium text-sm">
                {label === 'Código' ? (
                  <span className="text-sky-400 font-mono font-bold tracking-wide">{value}</span>
                ) : label === 'Capacidad actual' || label === 'Capacidad inicial' ? (
                  <span className="font-mono text-sky-300 font-semibold">{value}</span>
                ) : label === 'Estado administrativo' ? (
                  <span className={`status-badge ${c.active ? 'status-active' : 'status-neutral'}`}>{value}</span>
                ) : (
                  value
                )}
              </dd>
            </div>
          ))}
        </dl>
      </section>
      <section className="panel p-6 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl">
        <div className="flex items-center gap-2 border-b border-sky-500/15 pb-3 mb-4">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs" aria-hidden="true">
            <Zap size={14} />
          </span>
          <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">Activación inicial</h2>
        </div>
        {!access.can('activations.view') ? (
          <p className="text-sm text-slate-400 font-mono">Sin permiso para consultar la activación.</p>
        ) : a ? (
          <div className="space-y-3">
            <div className="p-3.5 rounded-xl bg-[#070d1a] border border-slate-800">
              <p className="font-mono font-bold text-emerald-400 text-base tracking-wide">{a.reference}</p>
              <p className="mt-1 text-xs text-slate-300 font-mono">{formatDate(a.effective_at, ticketynTimezone)} · <span className="text-slate-400">{a.responsible.name}</span></p>
            </div>
            <div>
              <Link className="button-ghost rounded-full text-sky-400 hover:text-sky-300 font-mono text-xs inline-flex items-center gap-1.5" to={`/activations/${a.id}`}>
                Ver detalle y bitácora →
              </Link>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-slate-400 font-mono">Sin registrar</p>
            <Can permission="activations.create">
              <button type="button" className="button-primary button-primary--blue rounded-full shadow-sm" onClick={() => setModal('activations')}>
                <Plus size={14} aria-hidden="true" />
                Registrar activación
              </button>
            </Can>
          </div>
        )}
      </section>
    </div>
    <section aria-label="Distribución actual del circuito" className="panel mb-5 rounded-2xl border border-sky-500/20 bg-[#0b1426] p-6">
      <h2 className="mb-4 text-xs font-bold uppercase tracking-wider text-white">Distribución actual</h2>
      <dl className="grid gap-4 sm:grid-cols-3">
        {([['Nodo de distribución', c.node?.name], ['Equipo de distribución', c.distribution_device?.name], ['Puerto de distribución', c.distribution_port?.name]] as const).map(([label, value]) => <div key={label} className="min-w-0">
          <dt className="text-xs text-slate-400">{label}</dt>
          <dd className="mt-1 break-words text-sm text-white">
            {label === 'Equipo de distribución' && c.distribution_device?.id && access.any('distribution_devices.view', 'distribution_devices.lookup') ? (
              <Link to={`/distribution-devices/${c.distribution_device.id}`} className="text-sky-400 hover:text-sky-300 font-medium hover:underline inline-flex items-center gap-1">
                {value} →
              </Link>
            ) : (
              value ?? 'No asignado'
            )}
          </dd>
        </div>)}
      </dl>
    </section>
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <div className="segmented-control segmented-control--soft segmented-control--blue" role="group" aria-label="Historial del circuito">
        <Can permission="capacity_changes.view"><button className="segment-button" aria-pressed={currentTab === 'capacity-changes'} onClick={() => setTab('capacity-changes')}>Capacidad</button></Can>
        <Can permission="lifecycle.view"><button className="segment-button" aria-pressed={currentTab === 'circuit-lifecycle'} onClick={() => setTab('circuit-lifecycle')}>Bajas / Reactivaciones</button></Can>
        <Can permission="cpe.view"><button className="segment-button" aria-pressed={currentTab === 'cpe'} onClick={() => setTab('cpe')}>Configuración CPE</button></Can>
      </div>
      {currentTab && currentTab !== 'cpe' && (currentTab==='capacity-changes'?access.can('capacity_changes.execute'):access.any('lifecycle.deactivate','lifecycle.reactivate')) && (
        <button ref={fallbackFocus} type="button" className="button-primary button-primary--blue rounded-full shadow-sm" disabled={actionBusy || loading} onClick={() => setModal(currentTab!)}>
          <Plus size={14} aria-hidden="true" />
          Nueva operación
        </button>
      )}
    </div>
    {!currentTab ? null : currentTab === 'cpe' ? <CpeConfiguration key={id} circuitId={id} /> : <>
    {historyLoading || historyError || !items.length ? <RequestState className="rounded-2xl bg-[#0b1426] border border-slate-800/80 shadow-xl p-8 text-center" loading={historyLoading} error={historyError} empty={!items.length} emptyTitle="Sin operaciones registradas." onRetry={() => setRefresh(refresh + 1)} /> : <OperationsTable showAssignments={false} kind={currentTab} items={items} />}
    <PaginationBar page={Math.floor(offset / 10) + 1} info={<p className="text-xs">Página {Math.floor(offset / 10) + 1} · 10 registros por página</p>} previousDisabled={historyLoading || offset === 0} nextDisabled={historyLoading || Boolean(historyError) || items.length < 10} onPrevious={() => setOffsets({ ...offsets, [currentTab]: Math.max(0, offset - 10) })} onNext={() => setOffsets({ ...offsets, [currentTab]: offset + 10 })} />
    </>}
    {editing && access.can("circuits.edit") && <CircuitEditModal circuit={c} onCancel={() => setEditing(false)} onSaved={(saved) => { setEditing(false); setDetail((old) => old ? { ...old, circuit: saved } : old); setActionNotice('Cambios guardados correctamente.'); setRefresh(refresh + 1) }} />}
    {deleting && access.can("circuits.delete") && <CatalogDeleteConfirmation item={c} fallbackFocus={fallbackFocus} onCancel={() => setDeleting(false)} onBusyChange={setActionBusy} onDeleted={() => navigate('/circuits', { state: { deletedCircuitCode: c.circuit_code } })} />}
    {modal && <OperationModal kind={modal} circuit={c} onCancel={() => setModal(null)} onSaved={() => { const savedKind = modal; setModal(null); setSuccess(true); if (savedKind === 'capacity-changes' || savedKind === 'circuit-lifecycle') setOffsets((current) => ({ ...current, [savedKind]: 0 })); setRefresh(refresh + 1) }} />}
  </>
}
