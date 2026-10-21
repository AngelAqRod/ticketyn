import { Can, usePermissions } from '../auth/permissions'
import { FilterHeading } from '../components/FilterHeading'
import { PaginationBar } from '../components/PaginationBar'
import { useEffect, useMemo, useRef, useState } from 'react'
import { FileText, RefreshCw, Zap, Users, Network, Gauge, Power, TrendingUp, TrendingDown } from 'lucide-react'
import { listSectors, listNodes, listResponsibles } from '../api'
import { FeedbackMessage } from '../components/FeedbackMessage'
import { downloadFile, getJson } from '../api/client'
import { PageHeading } from '../components/PageHeading'
import { PeriodShortcuts } from '../components/PeriodShortcuts'
import { FormField } from '../components/FormField'
import { SearchableSelect } from '../components/SearchableSelect'
import { RequestState } from '../components/RequestState'
import { SectionHeading } from '../components/SectionHeading'
import { MetricStrip, type MetricItem } from '../components/MetricStrip'
import { TrendChart, ActivityChart, DistributionChart } from '../components/ReportCharts'
import { chartPalette } from '../components/chartTheme'
import { RankingSection } from '../components/RankingSection'
import { OperationsTable } from '../components/OperationsTable'
import { useUrlFilters } from '../hooks/useUrlFilters'
import { reportFilterKeys, reportPeriod } from '../lib/reportPeriod'
import { formatDate } from '../lib/format'
import { formatCapacity } from '../lib/capacity'
import { ticketynTimezone } from '../lib/datetime'
import type { FmsKind, Operation } from '../types/fms'
import type { FmsReportSummary } from '../types/fmsReport'

export const fmsReportTitles: Record<FmsKind, string> = { activations: 'Reportería de activaciones', 'capacity-changes': 'Reportería de cambios de capacidad', 'circuit-lifecycle': 'Reportería de bajas y reactivaciones' }
const failureText = (error: unknown) => error instanceof Error ? error.message : 'No se pudo cargar el reporte.'
function capacity(value?: string) { return value?.startsWith('-') ? `−${formatCapacity(value.slice(1), 'Mbps')}` : formatCapacity(value, 'Mbps') }

export function FmsReports({ kind }: { kind: FmsKind }) {
  const access=usePermissions(), module='reports.'+(kind==='activations'?'activations':kind==='capacity-changes'?'capacity_changes':'lifecycle'), mayView=access.can(module+'.view')
  const { params, change } = useUrlFilters(reportFilterKeys)
  const [today] = useState(() => new Date())
  const key = params.toString()
  const selection = useMemo(() => {
    const filters = new URLSearchParams(key)
    filters.delete('recipient_id')
    if (!filters.has('period') && !filters.has('from') && !filters.has('to')) filters.set('period', 'all')
    try { return { ...reportPeriod(filters, today), error: '' } }
    catch (error) { return { ...reportPeriod(new URLSearchParams({ period: 'all' }), today), period: filters.get('period') ?? 'custom', error: failureText(error) } }
  }, [key, today])
  const view = params.get('view') ?? 'general'
  const dimension = view === 'node' ? { key: 'node_id', label: 'Nodo' } : view === 'responsible' ? { key: 'responsible_id', label: 'Responsable' } : { key: 'sector_id', label: 'Sector' }
  const scoped = view !== 'general'
  const invalid = selection.error || (!['general', 'sector', 'node', 'responsible'].includes(view) ? 'Tipo de reporte inválido.' : scoped && !params.get(dimension.key) ? `Selecciona un ${dimension.label.toLowerCase()} para consultar el reporte.` : '')
  const query = new URLSearchParams(Object.entries({ ...selection.query, granularity: 'auto' }).map(([name, value]) => [name, String(value)]))
  const queryKey = query.toString()
  useEffect(() => { setExportError('') }, [kind, queryKey])
  const rawOffset = Number(params.get('offset') ?? 0)
  const offset = Number.isInteger(rawOffset) && rawOffset >= 0 ? rawOffset : 0
  const exportBusy = useRef(false)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')
  async function exportPdf() {
    if (exportBusy.current || invalid || (mayView&&(!summary||loading))) return
    exportBusy.current = true; setExporting(true); setExportError('')
    try { await downloadFile(`/api/fms/reports/${kind}/export/pdf?${queryKey}`, `ticketyn-analisis-${kind}-${view === 'node' ? 'nodo' : view === 'responsible' ? 'responsable' : view}.pdf`) }
    catch (error) { setExportError(failureText(error)) }
    finally { exportBusy.current = false; setExporting(false) }
  }
  const [retry, setRetry] = useState(0)
  const [summary, setSummary] = useState<FmsReportSummary | null>(null)
  const [items, setItems] = useState<Operation[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [catalogs, setCatalogs] = useState<{ id: number; name: string }[][]>([[], [], []])
  const [catalogError, setCatalogError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    setCatalogError('')
    Promise.all([listSectors(controller.signal, true), listNodes(controller.signal, true), listResponsibles(controller.signal, true)]).then((rows) => { if (!controller.signal.aborted) setCatalogs(rows) }).catch((error: unknown) => { if (!controller.signal.aborted) setCatalogError(failureText(error)) })
    return () => controller.abort()
  }, [retry])
  useEffect(() => {
    setSummary(null); setItems([]); setError('')
    if (invalid||!mayView) { setLoading(false); return }
    const controller = new AbortController()
    setLoading(true)
    Promise.all([
      getJson<FmsReportSummary>(`/api/fms/reports/${kind}/summary?${queryKey}`, controller.signal),
      getJson<Operation[]>(`/api/fms/reports/${kind}/details?${queryKey}&limit=50&offset=${offset}`, controller.signal),
    ]).then(([summary, rows]) => { if (!controller.signal.aborted) { setSummary(summary); setItems(rows); setLoading(false) } }).catch((error: unknown) => { if (!controller.signal.aborted) { setError(failureText(error)); setLoading(false) } })
    return () => controller.abort()
  }, [kind, queryKey, offset, invalid, retry, mayView])
  const k = summary?.kpis
  const totalCount = kind === 'activations' ? (k?.total ?? 0) : kind === 'capacity-changes' ? ((k?.increases ?? 0) + (k?.decreases ?? 0)) : ((k?.deactivations ?? 0) + (k?.reactivations ?? 0))
  const totalLabel = kind === 'activations' ? 'activaciones' : kind === 'capacity-changes' ? 'cambios de capacidad' : 'bajas y reactivaciones'
  const metrics: MetricItem[] = kind === 'activations' ? [
    { color: 'mint', label: 'Total de activaciones', value: k?.total, icon: <Zap size={20} /> },
    { color: 'ice', label: 'Clientes distintos atendidos', value: k?.distinct_customers, icon: <Users size={20} /> },
    { color: 'indigo', label: 'Circuitos distintos activados', value: k?.distinct_circuits, icon: <Network size={20} /> },
  ] : kind === 'capacity-changes' ? [
    { color: 'mint', label: 'Incrementos registrados', value: k?.increases, icon: <TrendingUp size={20} /> },
    { color: 'amber', label: 'Decrementos registrados', value: k?.decreases, icon: <TrendingDown size={20} /> },
    { color: 'mint', label: 'Capacidad agregada conocida', value: capacity(k?.known_added_mbps), icon: <Gauge size={20} /> },
    { color: 'slate', label: 'Capacidad reducida conocida', value: capacity(k?.known_reduced_mbps), icon: <Gauge size={20} /> },
    { color: 'cyan', label: 'Variación neta conocida', value: capacity(k?.known_net_mbps), icon: <Gauge size={20} /> },
  ] : [
    { color: 'rose', label: 'Total de bajas', value: k?.deactivations, icon: <Power size={20} /> },
    { color: 'mint', label: 'Total de reactivaciones', value: k?.reactivations, icon: <Zap size={20} /> },
    { color: 'ice', label: 'Circuitos distintos con bajas', value: k?.distinct_deactivated_circuits, icon: <Network size={20} /> },
    { color: 'cyan', label: 'Circuitos distintos con reactivaciones', value: k?.distinct_reactivated_circuits, icon: <Network size={20} /> },
  ]
  const trendTitle = kind === 'activations' ? 'Evolución de activaciones' : kind === 'capacity-changes' ? 'Evolución de incrementos y decrementos' : 'Evolución de bajas y reactivaciones'
  return <>
    <PageHeading
      title={fmsReportTitles[kind]}
      description="Análisis por fecha efectiva de la operación."
      telemetry={<span className="heading-telemetry"><span className="telemetry-value--emerald font-mono font-bold">{totalCount}</span> {totalLabel}</span>}
      action={<div className="flex flex-wrap gap-2">
        <button type="button" className="button-secondary rounded-full shadow-xs" onClick={() => setRetry(retry + 1)} disabled={loading}><RefreshCw size={14} aria-hidden="true" />Actualizar</button>
        <Can permission={module+".export"}><button type="button" className="button-secondary rounded-full shadow-xs" disabled={Boolean(invalid) || loading || (mayView&&!summary) || exporting} onClick={exportPdf}><FileText size={14} aria-hidden="true" />{exporting ? 'Generando PDF...' : 'Exportar PDF'}</button></Can>
      </div>}
    />
    <section className="filter-toolbar filter-toolbar--emerald mb-5" aria-label="Filtros de reportería FMS">
      <FilterHeading title="Filtros del reporte" theme="emerald" />
      <div className="mb-3 period-shortcuts--emerald">
        <PeriodShortcuts includeAll label="Período del reporte" value={selection.period} onChange={(period) => change({ period, from: period === 'custom' ? selection.from : '', to: period === 'custom' ? selection.to : '' })} />
      </div>
      <div className="segmented-control segmented-control--soft segmented-control--emerald max-w-full flex-wrap" role="group" aria-label="Tipo de reporte">
        {[['general', 'General'], ['sector', 'Por Sector'], ['node', 'Por Nodo'], ['responsible', 'Por Responsable']].map(([value, label]) => <button key={value} type="button" className="segment-button" aria-pressed={view === value} onClick={() => change({ view: value, sector_id: '', node_id: '', responsible_id: '' })}>{label}</button>)}
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        {scoped && <FormField id="fms-dimension" label={dimension.label}><SearchableSelect id="fms-dimension" label={dimension.label} value={params.get(dimension.key) ?? ''} options={catalogs[view === 'node' ? 1 : view === 'responsible' ? 2 : 0].map((row) => ({ value: String(row.id), label: row.name }))} onChange={(value) => change({ [dimension.key]: value })} placeholder={`Selecciona un ${dimension.label.toLowerCase()}`} disabled={Boolean(catalogError)} emptyMessage="No hay registros disponibles." noMatchMessage="No se encontraron registros." /></FormField>}
        {selection.period === 'custom' && <><FormField id="fms-from" label="Desde"><input className="form-input" id="fms-from" type="date" value={params.get('from') ?? selection.from} onChange={(event) => change({ from: event.target.value })} /></FormField><FormField id="fms-to" label="Hasta"><input className="form-input" id="fms-to" type="date" value={params.get('to') ?? selection.to} onChange={(event) => change({ to: event.target.value })} /></FormField></>}
      </div>
      <p className="mt-2 text-xs text-muted">{selection.period === 'all' ? 'Todo el período' : `${selection.from} — ${selection.to}`} · {ticketynTimezone}</p>
      {catalogError && <RequestState compact error={catalogError} onRetry={() => setRetry(retry + 1)} />}
    </section>
    {exportError && <FeedbackMessage variant="error" className="mb-3">{exportError}</FeedbackMessage>}
    {exporting && <RequestState compact loading className="workspace-caption" loadingText="Generando PDF..." />}
    {invalid ? selection.error || !['general', 'sector', 'node', 'responsible'].includes(view) ? <RequestState compact error={invalid} errorTitle="" className="workspace-caption" /> : <RequestState compact empty emptyTitle={invalid} emptyDescription="" /> : loading ? <RequestState loading loadingText="Cargando reporte..." /> : error ? <RequestState error={error} onRetry={() => setRetry(retry + 1)} /> : summary && <>
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-3 text-xs workspace-caption"><h2 className="font-semibold text-slate-200">{scoped ? `Reporte por ${dimension.label} — ${summary[view === 'node' ? 'node' : view === 'responsible' ? 'responsible' : 'sector']?.name ?? ''}` : 'Reporte General'}</h2><span className="font-mono text-slate-400">Generado: {formatDate(summary.generated_at, ticketynTimezone)}</span></div>
      <SectionHeading number="02" title="Resumen" /><MetricStrip variant="light" items={metrics.map((item) => ({ ...item, value: <span className="[overflow-wrap:anywhere]">{item.value}</span> }))} />
      <p className="my-3 text-[11px] leading-4 workspace-caption">Fecha efectiva y Sector/Nodo registrados en cada operación. {kind === 'activations' ? 'Circuitos activados durante el período; no representa su estado administrativo actual.' : kind === 'capacity-changes' ? `${k?.unknown_variations ?? 0} operaciones sin capacidad anterior conocida cuentan como operaciones, pero no aportan variación. Las capacidades muestran únicamente variaciones conocidas.` : 'Bajas y reactivaciones son eventos; su diferencia no representa circuitos actualmente fuera de servicio.'}</p>
      {summary.trend.every((row) => row.count === 0) && <RequestState compact empty emptyTitle="No hay operaciones en este período." emptyDescription="" />}
      <section className="report-section analytics-card chart-card chart-card--emerald mb-5"><SectionHeading number="03" title={trendTitle} />{kind === 'activations' ? <TrendChart trend={summary.trend} granularity={summary.period.granularity} title={trendTitle} countLabel="Activaciones" timeZone={ticketynTimezone} /> : <ActivityChart secondColor={chartPalette[1]} rows={summary.trend.map((row) => ({ start_at: row.start_at, started: row.first, closed: row.second }))} title={trendTitle} firstLabel={kind === 'capacity-changes' ? 'Incrementos' : 'Bajas'} secondLabel={kind === 'capacity-changes' ? 'Decrementos' : 'Reactivaciones'} timeZone={ticketynTimezone} granularity={summary.period.granularity} />}</section>
      {kind === 'activations' && !scoped && <div className="mb-5"><RankingSection className="chart-card--emerald" title="Clientes con más circuitos distintos activados" rows={summary.customers} countLabel="Circuitos distintos" emptyText="Sin activaciones." destination={(row) => `/activations?${new URLSearchParams({ customer_id: String(row.id), period: selection.period, ...(selection.period === 'custom' ? { from: selection.from, to: selection.to } : {}) })}`} /></div>}
      {kind === 'circuit-lifecycle' && <section className="report-section analytics-card chart-card chart-card--emerald mb-5"><SectionHeading number="04" title="Distribución de bajas por motivo" /><DistributionChart title="Motivos de baja" rows={summary.reasons} /></section>}
      <SectionHeading number={kind === 'activations' && scoped || kind === 'capacity-changes' ? '04' : '05'} title="Detalle de operaciones" />
      {items.length ? <OperationsTable kind={kind} items={items} /> : <RequestState compact empty emptyTitle="No hay operaciones en esta página." emptyDescription="" />}
      <PaginationBar className="mt-4" page={Math.floor(offset / 50) + 1} info={<span className="text-xs">Página {Math.floor(offset / 50) + 1}</span>} previousDisabled={!offset} nextDisabled={items.length < 50} onPrevious={() => change({ offset: String(Math.max(0, offset - 50)) }, false)} onNext={() => change({ offset: String(offset + 50) }, false)} />
    </>}
  </>
}
