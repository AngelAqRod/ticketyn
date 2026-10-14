import { useEffect, useMemo, useRef, useState } from 'react'
import { FileText, RefreshCw, SlidersHorizontal, Zap, Users, Network, Gauge, Power, TrendingUp, TrendingDown } from 'lucide-react'
import { listSectors, listNodes, listResponsibles } from '../api'
import { FeedbackMessage } from '../components/FeedbackMessage'
import { downloadFile, getJson } from '../api/client'
import { PageHeading } from '../components/PageHeading'
import { PeriodShortcuts } from '../components/PeriodShortcuts'
import { FormField } from '../components/FormField'
import { SearchableSelect } from '../components/SearchableSelect'
import { RequestState } from '../components/RequestState'
import { SectionHeading } from '../components/SectionHeading'
import { MetricStrip } from '../components/MetricStrip'
import { TrendChart, ActivityChart, DistributionChart } from '../components/ReportCharts'
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
    if (exportBusy.current || invalid || !summary || loading) return
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
    if (invalid) { setLoading(false); return }
    const controller = new AbortController()
    setLoading(true)
    Promise.all([
      getJson<FmsReportSummary>(`/api/fms/reports/${kind}/summary?${queryKey}`, controller.signal),
      getJson<Operation[]>(`/api/fms/reports/${kind}/details?${queryKey}&limit=50&offset=${offset}`, controller.signal),
    ]).then(([summary, rows]) => { if (!controller.signal.aborted) { setSummary(summary); setItems(rows); setLoading(false) } }).catch((error: unknown) => { if (!controller.signal.aborted) { setError(failureText(error)); setLoading(false) } })
    return () => controller.abort()
  }, [kind, queryKey, offset, invalid, retry])
  const k = summary?.kpis
  const metrics = kind === 'activations' ? [
    { label: 'Total de activaciones', value: k?.total, icon: <Zap size={20} /> },
    { label: 'Clientes distintos atendidos', value: k?.distinct_customers, icon: <Users size={20} /> },
    { label: 'Circuitos distintos activados', value: k?.distinct_circuits, icon: <Network size={20} /> },
  ] : kind === 'capacity-changes' ? [
    { label: 'Incrementos registrados', value: k?.increases, icon: <TrendingUp size={20} /> },
    { label: 'Decrementos registrados', value: k?.decreases, icon: <TrendingDown size={20} /> },
    { label: 'Capacidad agregada conocida', value: capacity(k?.known_added_mbps), icon: <Gauge size={20} /> },
    { label: 'Capacidad reducida conocida', value: capacity(k?.known_reduced_mbps), icon: <Gauge size={20} /> },
    { label: 'Variación neta conocida', value: capacity(k?.known_net_mbps), icon: <Gauge size={20} /> },
  ] : [
    { label: 'Total de bajas', value: k?.deactivations, icon: <Power size={20} /> },
    { label: 'Total de reactivaciones', value: k?.reactivations, icon: <Zap size={20} /> },
    { label: 'Circuitos distintos con bajas', value: k?.distinct_deactivated_circuits, icon: <Network size={20} /> },
    { label: 'Circuitos distintos con reactivaciones', value: k?.distinct_reactivated_circuits, icon: <Network size={20} /> },
  ]
  const trendTitle = kind === 'activations' ? 'Evolución de activaciones' : kind === 'capacity-changes' ? 'Evolución de incrementos y decrementos' : 'Evolución de bajas y reactivaciones'
  return <>
    <PageHeading title={fmsReportTitles[kind]} description="Análisis por fecha efectiva de la operación." action={<div className="flex flex-wrap gap-2"><button type="button" className="button-secondary" onClick={() => setRetry(retry + 1)} disabled={loading}><RefreshCw size={14} aria-hidden="true" />Actualizar</button><button type="button" className="button-secondary" disabled={Boolean(invalid) || loading || !summary || exporting} onClick={exportPdf}><FileText size={14} aria-hidden="true" />{exporting ? 'Generando PDF...' : 'Exportar PDF'}</button></div>} />
    <section className="filter-toolbar" aria-label="Filtros de reportería FMS">
      <p className="toolbar-heading gap-3"><span className="icon-surface" aria-hidden="true"><SlidersHorizontal size={15} /></span>Filtros del reporte</p>
      <div className="mb-3"><PeriodShortcuts includeAll label="Período del reporte" value={selection.period} onChange={(period) => change({ period, from: period === 'custom' ? selection.from : '', to: period === 'custom' ? selection.to : '' })} /></div>
      <div className="segmented-control max-w-full flex-wrap" role="group" aria-label="Tipo de reporte">{[['general', 'General'], ['sector', 'Por Sector'], ['node', 'Por Nodo'], ['responsible', 'Por Responsable']].map(([value, label]) => <button key={value} type="button" className="segment-button" aria-pressed={view === value} onClick={() => change({ view: value, sector_id: '', node_id: '', responsible_id: '' })}>{label}</button>)}</div>
      <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        {scoped && <FormField id="fms-dimension" label={dimension.label}><SearchableSelect id="fms-dimension" label={dimension.label} value={params.get(dimension.key) ?? ''} options={catalogs[view === 'node' ? 1 : view === 'responsible' ? 2 : 0].map((row) => ({ value: String(row.id), label: row.name }))} onChange={(value) => change({ [dimension.key]: value })} placeholder={`Selecciona un ${dimension.label.toLowerCase()}`} disabled={Boolean(catalogError)} emptyMessage="No hay registros disponibles." noMatchMessage="No se encontraron registros." /></FormField>}
        {selection.period === 'custom' && <><FormField id="fms-from" label="Desde"><input className="form-input" id="fms-from" type="date" value={params.get('from') ?? selection.from} onChange={(event) => change({ from: event.target.value })} /></FormField><FormField id="fms-to" label="Hasta"><input className="form-input" id="fms-to" type="date" value={params.get('to') ?? selection.to} onChange={(event) => change({ to: event.target.value })} /></FormField></>}
      </div>
      <p className="mt-2 text-xs text-muted">{selection.period === 'all' ? 'Todo el período' : `${selection.from} — ${selection.to}`} · {ticketynTimezone}</p>
      {catalogError && <RequestState compact error={catalogError} onRetry={() => setRetry(retry + 1)} />}
    </section>
    {exportError && <FeedbackMessage variant="error" className="mb-3">{exportError}</FeedbackMessage>}
    {exporting && <RequestState compact loading loadingText="Generando PDF..." />}
    {invalid ? selection.error || !['general', 'sector', 'node', 'responsible'].includes(view) ? <RequestState compact error={invalid} errorTitle="" /> : <RequestState compact empty emptyTitle={invalid} emptyDescription="" /> : loading ? <RequestState loading loadingText="Cargando reporte..." /> : error ? <RequestState error={error} onRetry={() => setRetry(retry + 1)} /> : summary && <>
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-3 text-xs text-muted"><h2 className="font-semibold text-ink">{scoped ? `Reporte por ${dimension.label} — ${summary[view === 'node' ? 'node' : view === 'responsible' ? 'responsible' : 'sector']?.name ?? ''}` : 'Reporte General'}</h2><span>Generado: {formatDate(summary.generated_at, ticketynTimezone)}</span></div>
      <SectionHeading number="02" title="Resumen" /><MetricStrip variant="light" items={metrics.map((item) => ({ ...item, value: <span className="[overflow-wrap:anywhere]">{item.value}</span> }))} />
      <p className="my-3 text-[11px] leading-4 text-muted">Fecha efectiva y Sector/Nodo registrados en cada operación. {kind === 'activations' ? 'Circuitos activados durante el período; no representa su estado administrativo actual.' : kind === 'capacity-changes' ? `${k?.unknown_variations ?? 0} operaciones sin capacidad anterior conocida cuentan como operaciones, pero no aportan variación. Las capacidades muestran únicamente variaciones conocidas.` : 'Bajas y reactivaciones son eventos; su diferencia no representa circuitos actualmente fuera de servicio.'}</p>
      {summary.trend.every((row) => row.count === 0) && <RequestState compact empty emptyTitle="No hay operaciones en este período." emptyDescription="" />}
      <section className="report-section analytics-card"><SectionHeading number="03" title={trendTitle} />{kind === 'activations' ? <TrendChart trend={summary.trend} granularity={summary.period.granularity} title={trendTitle} countLabel="Activaciones" timeZone={ticketynTimezone} /> : <ActivityChart rows={summary.trend.map((row) => ({ start_at: row.start_at, started: row.first, closed: row.second }))} title={trendTitle} firstLabel={kind === 'capacity-changes' ? 'Incrementos' : 'Bajas'} secondLabel={kind === 'capacity-changes' ? 'Decrementos' : 'Reactivaciones'} timeZone={ticketynTimezone} granularity={summary.period.granularity} />}</section>
      {kind === 'activations' && !scoped && <RankingSection title="Clientes con más circuitos distintos activados" rows={summary.customers} countLabel="Circuitos distintos" emptyText="Sin activaciones." destination={(row) => `/activations?${new URLSearchParams({ customer_id: String(row.id), period: selection.period, ...(selection.period === 'custom' ? { from: selection.from, to: selection.to } : {}) })}`} />}
      {kind === 'circuit-lifecycle' && <section className="report-section analytics-card"><SectionHeading number="04" title="Distribución de bajas por motivo" /><DistributionChart title="Motivos de baja" rows={summary.reasons} /></section>}
      <SectionHeading number={kind === 'activations' && scoped || kind === 'capacity-changes' ? '04' : '05'} title="Detalle de operaciones" />
      {items.length ? <OperationsTable kind={kind} items={items} /> : <RequestState compact empty emptyTitle="No hay operaciones en esta página." emptyDescription="" />}
      <div className="mt-3 flex flex-wrap items-center justify-end gap-2"><button type="button" className="button-secondary" disabled={!offset} onClick={() => change({ offset: String(Math.max(0, offset - 50)) }, false)}>Anterior</button><span className="text-xs text-muted">Página {Math.floor(offset / 50) + 1}</span><button type="button" className="button-secondary" disabled={items.length < 50} onClick={() => change({ offset: String(offset + 50) }, false)}>Siguiente</button></div>
    </>}
  </>
}
