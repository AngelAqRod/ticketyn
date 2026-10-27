import { Can, usePermissions } from '../auth/permissions'
import { PaginationBar } from '../components/PaginationBar'
import { operationFilters } from '../lib/fmsFilters'
import { useEffect, useRef, useState } from 'react'
import { Plus, FileText, FileSpreadsheet } from 'lucide-react'
import { listCustomers } from '../api'
import { listOperations, downloadOperations } from '../api/fms'
import type { Customer } from '../types/catalog'
import type { FmsKind, Operation } from '../types/fms'
import { fmsTitles } from '../types/fms'
import { PageHeading } from '../components/PageHeading'
import { RequestState } from '../components/RequestState'
import { FeedbackMessage } from '../components/FeedbackMessage'
import { FormField } from '../components/FormField'
import { SearchableSelect } from '../components/SearchableSelect'
import { PeriodShortcuts } from '../components/PeriodShortcuts'
import { OperationModal } from '../components/OperationModal'
import { OperationsTable } from '../components/OperationsTable'
import { FilterBar } from '../components/FilterBar'
import type { FilterChipItem } from '../components/FilterChips'
import { ticketynDateTimeValue } from '../lib/datetime'
import { reportPeriod } from '../lib/reportPeriod'
import { useUrlFilters } from '../hooks/useUrlFilters'

export function Operations({ kind }: { kind: FmsKind }) {
  const access=usePermissions(), module=kind==='activations'?'activations':kind==='capacity-changes'?'capacity_changes':'lifecycle'
  const mayCreate=kind==='circuit-lifecycle'?access.any('lifecycle.deactivate','lifecycle.reactivate'):access.can(module+(kind==='activations'?'.create':'.execute'))
  const { params, change, clear } = useUrlFilters(['customer_id', 'period', 'from', 'to', 'operation_type'])
  const [items, setItems] = useState<Operation[]>([]), [customers, setCustomers] = useState<Customer[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState<string | null>(null), [refresh, setRefresh] = useState(0), [modal, setModal] = useState(false), [success, setSuccess] = useState(false)
  const exportingRef = useRef(false)
  const [exporting, setExporting] = useState(false), [exportError, setExportError] = useState<string | null>(null)
  const offset = Math.max(0, Number(params.get('offset') ?? 0) || 0), key = params.toString()
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null)
    try {
      const request = operationFilters(new URLSearchParams(key))
      request.set('limit', '50'); request.set('offset', String(offset))
      Promise.all([listOperations(kind, request, controller.signal), listCustomers(controller.signal, true)]).then(([rows, clients]) => { if (!controller.signal.aborted) { setItems(rows); setCustomers(clients); setLoading(false) } }).catch((failure: unknown) => { if (!controller.signal.aborted) { setError(failure instanceof Error ? failure.message : 'No se pudo cargar el historial.'); setLoading(false) } })
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Período inválido.'); setLoading(false) }
    return () => controller.abort()
  }, [kind, key, offset, refresh])
  let filterError: string | null = null
  try { operationFilters(params) } catch (failure) { filterError = failure instanceof Error ? failure.message : 'Período inválido.' }
  async function exportOperations(format: 'pdf' | 'xlsx') {
    if (exportingRef.current || filterError) return
    exportingRef.current = true; setExporting(true); setExportError(null)
    try { await downloadOperations(kind, format, operationFilters(params)) }
    catch (failure) { setExportError(failure instanceof Error ? failure.message : 'No se pudo exportar el listado.') }
    finally { exportingRef.current = false; setExporting(false) }
  }

  // Cada chip quita solo su condición; el período personalizado incluye sus fechas, así que se quita completo.
  const filterChips: FilterChipItem[] = []
  if (params.get('customer_id')) {
    const cust = customers.find(c => String(c.id) === params.get('customer_id'))
    filterChips.push({ label: 'Cliente', value: cust?.name ?? `#${params.get('customer_id')}`, onRemove: () => change({ customer_id: '' }) })
  }
  if (params.get('period') && params.get('period') !== 'all') {
    const p = params.get('period')
    const pLabel = p === '1' ? 'Hoy' : p === 'yesterday' ? 'Ayer' : p === '7' ? 'Últimos 7 días' : p === '15' ? 'Últimos 15 días' : p === '30' ? 'Último mes' : p === 'custom' ? `${params.get('from') || '—'} a ${params.get('to') || '—'}` : p!
    filterChips.push({ label: 'Período', value: pLabel, onRemove: () => change({ period: '', from: '', to: '' }) })
  }
  if (params.get('operation_type')) {
    const t = params.get('operation_type')
    const tLabel = t === 'INCREASE' ? 'Incremento' : t === 'DECREASE' ? 'Decremento' : t === 'DEACTIVATE' ? 'Baja' : t === 'REACTIVATE' ? 'Reactivación' : t!
    filterChips.push({ label: 'Tipo', value: tLabel, onRemove: () => change({ operation_type: '' }) })
  }

  const isFms = kind === 'activations' || kind === 'capacity-changes' || kind === 'circuit-lifecycle'

  return <>
    <PageHeading
      title={fmsTitles[kind]}
      description="Registros operativos independientes de los tickets y del estado administrativo."
      telemetry={<span className="heading-telemetry"><span className={isFms ? 'telemetry-value--emerald' : 'telemetry-value--blue'}>{items.length}</span> registros</span>}
      action={<div className="flex flex-wrap gap-2">
        <Can permission={module+".export"}><button type="button" className="button-secondary rounded-full shadow-xs" disabled={exporting || Boolean(filterError)} onClick={() => exportOperations('pdf')}><FileText size={14} aria-hidden="true" />Exportar PDF</button></Can>
        <Can permission={module+".export"}><button type="button" className="button-secondary rounded-full shadow-xs" disabled={exporting || Boolean(filterError)} onClick={() => exportOperations('xlsx')}><FileSpreadsheet size={14} aria-hidden="true" />Exportar Excel</button></Can>
        {mayCreate&&<button type="button" className={`button-primary ${isFms ? 'button-primary--emerald' : 'button-primary--blue'} rounded-full shadow-sm`} onClick={() => setModal(true)}><Plus size={14} aria-hidden="true" />Nueva operación</button>}
      </div>}
    />
    {exporting && <RequestState loading compact loadingText="Generando archivo..." className="mb-3 workspace-caption" />}
    {exportError && <FeedbackMessage variant="error" className="mb-3">{exportError}</FeedbackMessage>}
    {success && <FeedbackMessage variant="success" className="mb-3">Operación registrada correctamente.</FeedbackMessage>}
    <FilterBar
      label="Filtros operativos"
      theme={isFms ? 'emerald' : 'blue'}
      chips={filterChips}
      onClear={clear}
      quick={<>
        <div className="filter-bar-quick">
          <FormField id="fms-customer" label="Cliente">
            <SearchableSelect placeholder="Selecciona una opción" emptyMessage="No hay registros disponibles." noMatchMessage="Sin coincidencias." id="fms-customer" label="Cliente" value={params.get('customer_id') ?? ''} onChange={(value) => change({ customer_id: value })} options={customers.map((item) => ({ value: String(item.id), label: `${item.customer_code} — ${item.name}` }))} />
          </FormField>
        </div>
        {kind !== 'activations' && <div className="filter-bar-quick"><FormField id="fms-type" label="Tipo"><select id="fms-type" className="form-input" value={params.get('operation_type') ?? ''} onChange={(event) => change({ operation_type: event.target.value })}><option value="">Todos</option>{kind === 'capacity-changes' ? <><option value="INCREASE">Incrementos</option><option value="DECREASE">Decrementos</option></> : <><option value="DEACTIVATE">Bajas</option><option value="REACTIVATE">Reactivaciones</option></>}</select></FormField></div>}
      </>}
      primary={<>
        <PeriodShortcuts includeAll value={params.get('period') ?? 'all'} onChange={(value) => {
          if (value !== 'custom') { change({ period: value, from: '', to: '' }); return }
          try { const range = reportPeriod(new URLSearchParams({ period: params.get('period') === 'custom' ? 'all' : params.get('period') ?? 'all' })); const today = ticketynDateTimeValue().slice(0, 10); change({ period: value, from: range.from || today, to: range.to || today }) } catch { const today = ticketynDateTimeValue().slice(0, 10); change({ period: value, from: today, to: today }) }
        }} label="Período operativo" labels={{ '7': 'Últimos 7 días', '15': 'Últimos 15 días', '30': 'Último mes' }} />
        {params.get('period') === 'custom' && ['from', 'to'].map((field) => <FormField key={field} id={`fms-${field}`} label={field === 'from' ? 'Desde' : 'Hasta'}><input id={`fms-${field}`} type="date" className="form-input" value={params.get(field) ?? ''} onChange={(event) => change({ [field]: event.target.value })} /></FormField>)}
      </>}
    />
    {loading || error || !items.length ? <RequestState className="rounded-2xl bg-[#0b1426] border border-slate-800/80 shadow-xl p-8 text-center" loading={loading} error={error} empty={!items.length} emptyTitle="Sin operaciones registradas." onRetry={() => setRefresh(refresh + 1)} /> : <OperationsTable kind={kind} items={items} />}
    <PaginationBar page={Math.floor(offset / 50) + 1} info={<span className="text-xs">Página {Math.floor(offset / 50) + 1}</span>} previousDisabled={loading || offset === 0} nextDisabled={loading || Boolean(error) || items.length < 50} onPrevious={() => change({ offset: String(Math.max(0, offset - 50)) }, false)} onNext={() => change({ offset: String(offset + 50) }, false)} />
    {modal && mayCreate && <OperationModal kind={kind} onCancel={() => setModal(false)} onSaved={() => { setModal(false); setSuccess(true); setRefresh(refresh + 1) }} />}
  </>
}
