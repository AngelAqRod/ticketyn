import { useEffect, useMemo, useState } from 'react'
import { Download, RefreshCw } from 'lucide-react'
import { listSectors, listNodes, listResponsibles } from '../api'
import { downloadReport, getReport } from '../api/reports'
import { PageHeading } from '../components/PageHeading'
import { FormField } from '../components/FormField'
import { SearchableSelect } from '../components/SearchableSelect'
import { TicketTable } from '../components/TicketTable'
import { RequestState } from '../components/RequestState'
import { TrendChart, ActivityChart, DistributionChart } from '../components/ReportCharts'
import { RankingSection } from '../components/RankingSection'
import { SectionHeading } from '../components/SectionHeading'
import { MetricStrip } from '../components/MetricStrip'
import { useUrlFilters } from '../hooks/useUrlFilters'
import { useTickets } from '../hooks/useTickets'
import { reportFilterKeys, reportPeriod, ticketDrillDown } from '../lib/reportPeriod'
import { formatDate, formatDuration } from '../lib/format'
import type { ReportSummary, ReportRanking } from '../types/report'
import type { Sector } from '../types/catalog'

const message = (error: unknown) => error instanceof Error ? error.message : 'Ocurrió un error inesperado.'
export function Reports() {
  const { params, change } = useUrlFilters(reportFilterKeys)
  const [today] = useState(() => new Date())
  const filterKey = params.toString()
  const selection = useMemo(() => {
    try { return { ...reportPeriod(new URLSearchParams(filterKey), today), error: null } }
    catch (error) {
      const fallback = reportPeriod(new URLSearchParams(), today)
      const custom = params.get('period') === 'custom' || params.has('from') || params.has('to')
      return { ...fallback, period: custom ? 'custom' : params.get('period') ?? '30', from: params.get('from') ?? '', to: params.get('to') ?? '', error: message(error) }
    }
  }, [filterKey, today])
  const view = params.get('view') ?? 'general'
  const sectorView = view === 'sector'
  const dimension = view === 'node' ? { key: 'node_id', label: 'Nodo' } : view === 'responsible' ? { key: 'responsible_id', label: 'Responsable' } : { key: 'sector_id', label: 'Sector' }
  const scopedView = view !== 'general'
  const missingSector = scopedView && !params.get(dimension.key)
  const invalid = selection.error || (missingSector ? `Selecciona un ${dimension.label.toLowerCase()} para consultar el reporte.` : null)
  const queryKey = JSON.stringify(selection.query)
  const [summary, setSummary] = useState<ReportSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const [nodes, setNodes] = useState<Sector[]>([])
  const [responsibles, setResponsibles] = useState<Sector[]>([])
  const [sectors, setSectors] = useState<Sector[]>([])
  const [sectorError, setSectorError] = useState<string | null>(null)
  const [sectorLoading, setSectorLoading] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    setSectorLoading(true); setSectorError(null)
    Promise.all([listSectors(controller.signal, true), listNodes(controller.signal, true), listResponsibles(controller.signal, true)]).then(([rows, nodeRows, responsibleRows]) => { if (!controller.signal.aborted) { setSectors(rows); setNodes(nodeRows); setResponsibles(responsibleRows); setSectorLoading(false) } }).catch((failure: unknown) => { if (!controller.signal.aborted) { setSectorError(message(failure)); setSectorLoading(false) } })
    return () => controller.abort()
  }, [retry])
  useEffect(() => {
    setExportError(null)
    if (invalid) { setSummary(null); setLoading(false); setError(null); return }
    const controller = new AbortController()
    setLoading(true); setSummary(null); setError(null)
    getReport(selection.query, controller.signal).then((data) => { if (!controller.signal.aborted) { setSummary(data); setLoading(false) } }).catch((failure: unknown) => { if (!controller.signal.aborted) { setError(message(failure)); setLoading(false) } })
    return () => controller.abort()
  }, [queryKey, invalid, retry])
  const offsetValue = Number(params.get('offset') ?? 0)
  const offset = Number.isInteger(offsetValue) && offsetValue >= 0 ? offsetValue : 0
  const { from, to, sector_id, node_id, responsible_id } = selection.query
  const detail = useTickets(offset, retry, { from, to, sector_id, node_id, responsible_id }, invalid)
  function period(value: string) {
    change({ period: value, ...(value === 'custom' ? { from: selection.from, to: selection.to } : { from: '', to: '' }) })
  }
  async function exportReport(format: 'pdf' | 'xlsx') {
    if (exporting || invalid) return
    setExporting(true); setExportError(null)
    try { await downloadReport(format, selection.query) } catch (failure) { setExportError(message(failure)) } finally { setExporting(false) }
  }
  function ranking(title: string, rows: ReportRanking[], field: string) {
    const reportView = field === 'sector_id' ? 'sector' : field === 'node_id' ? 'node' : field === 'responsible_id' ? 'responsible' : null
    return <RankingSection key={field} title={title} rows={rows} destination={(row) => view === 'general' && reportView ? `/reports?${new URLSearchParams({ view: reportView, period: 'custom', [field]: String(row.id), from: selection.from, to: selection.to })}` : ticketDrillDown(field, row.id, selection.from, selection.to, sector_id, node_id, responsible_id)} />
  }
  return <>
    <PageHeading title="Reportería" description="Incidencias por período operativo de Inicio. Una incidencia corresponde a un ticket." action={<div className="flex flex-wrap gap-2"><button className="button-secondary" type="button" onClick={() => setRetry(retry + 1)} disabled={loading}><RefreshCw size={14} />Actualizar</button><button className="button-secondary" type="button" disabled={loading || Boolean(invalid) || Boolean(error) || exporting || !summary} onClick={() => exportReport('pdf')}><Download size={14} />Exportar PDF</button><button className="button-secondary" type="button" disabled={loading || Boolean(invalid) || Boolean(error) || exporting || !summary} onClick={() => exportReport('xlsx')}><Download size={14} />Exportar Excel</button></div>} />
    <section className="filter-toolbar" aria-label="Filtros de reportería">
      <SectionHeading number="01" title="Período" />
      <div className="flex flex-wrap items-center gap-4">
        <div className="segmented-control" role="group" aria-label="Tipo de reporte">
          {['general', 'sector', 'node', 'responsible'].map((view) => <button key={view} type="button" className="segment-button" aria-pressed={view === (params.get('view') ?? 'general')} onClick={() => change({ view, sector_id: '', node_id: '', responsible_id: '' })}>{view === 'general' ? 'General' : view === 'node' ? 'Por nodo' : view === 'responsible' ? 'Por responsable' : 'Por sector'}</button>)}
        </div>
        <div className="segmented-control" role="group" aria-label="Período del reporte">
          {['1', '7', '15', '30', 'custom'].map((value) => <button key={value} type="button" className="segment-button" aria-label={value === 'custom' ? 'Personalizado' : `${value} ${value === '1' ? 'día' : 'días'}`} aria-pressed={selection.period === value} onClick={() => period(value)}>{value === 'custom' ? 'Personalizado' : `${value}D`}</button>)}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-end gap-3">
        {scopedView && <div className="min-w-64 flex-1"><FormField id="report-sector" label={dimension.label}><SearchableSelect id="report-sector" label={dimension.label} value={params.get(dimension.key) ?? ''} options={(view === 'node' ? nodes : view === 'responsible' ? responsibles : sectors).map((item) => ({ value: String(item.id), label: item.name }))} onChange={(value) => change({ [dimension.key]: value })} disabled={sectorLoading || Boolean(sectorError)} placeholder={`Selecciona un ${dimension.label.toLowerCase()}`} emptyMessage="No hay sectores." noMatchMessage="No se encontraron sectores." /></FormField></div>}
        {selection.period === 'custom' && <><FormField id="report-from" label="Desde"><input id="report-from" className="form-input" type="date" value={params.get('from') ?? selection.from} onChange={(event) => change({ period: 'custom', from: event.target.value })} /></FormField><FormField id="report-to" label="Hasta"><input id="report-to" className="form-input" type="date" value={params.get('to') ?? selection.to} onChange={(event) => change({ period: 'custom', to: event.target.value })} /></FormField></>}
        <p className="chip chip-neutral">{selection.from} — {selection.to} · {selection.query.timezone}</p>
      </div>
      {sectorError && scopedView && <p role="alert" className="text-sm text-red-800">{sectorError} <button type="button" className="underline" onClick={() => setRetry(retry + 1)}>Reintentar sectores</button></p>}
    </section>
    {exporting && <p role="status" className="mb-2 text-sm">Generando archivo...</p>}
    {exportError && <p role="alert" className="mb-3 text-sm text-red-800">{exportError}</p>}
    {invalid ? <p role={missingSector ? 'status' : 'alert'} className="panel p-4 text-sm">{invalid}</p> : loading ? <p role="status" className="panel p-5">Cargando reporte...</p> : error ? <div role="alert" className="panel p-4"><p>Error al cargar reporte: {error}</p><button className="button-secondary mt-2" type="button" onClick={() => setRetry(retry + 1)}>Reintentar</button></div> : summary && <>
      <div className="mb-2 flex justify-between text-xs text-slate-500"><h2 className="font-semibold text-slate-800">{summary.node ? `Reporte por Nodo — ${summary.node.name}` : summary.responsible ? `Reporte por Responsable — ${summary.responsible.name}` : summary.sector ? `Reporte por Sector — ${summary.sector.name}` : 'Reporte General'}</h2><span>Generado: {formatDate(summary.generated_at)}</span></div>
      <SectionHeading number="02" title="Resumen" />
      <MetricStrip items={[
        { label: 'Incidencias iniciadas', value: summary.kpis.started, tone: 'primary' },
        { label: 'Incidencias cerradas', value: summary.kpis.closed },
        { label: 'Duración promedio', value: summary.kpis.average_duration_seconds === null ? '—' : formatDuration(summary.kpis.average_duration_seconds) },
        { label: 'Duración acumulada', value: formatDuration(summary.kpis.total_duration_seconds) },
      ]} />
      <p className="mt-2 mb-3 max-w-5xl text-[11px] leading-4 text-muted">Iniciadas, evolución, rankings y detalle: Inicio en el período. Cerradas y duraciones: estado Cerrado y Fin en el período, incluso si comenzaron antes. Cerrados sin Fin no aportan duración.</p>
      {summary.kpis.started === 0 && <p role="status" className="mb-3 text-sm text-slate-500">No hay incidencias iniciadas en este período.</p>}
      <section className="report-section analytics-card"><SectionHeading number="03" title="Evolución de incidencias" /><TrendChart trend={summary.trend} granularity={summary.period.granularity} /></section>
      <section className="report-section"><SectionHeading number="04" title="Concentración" />
        <div className={`grid gap-x-8 gap-y-4 ${sectorView ? '' : 'xl:grid-cols-2'}`}>
          {!sectorView && ranking('Sectores con más incidencias', summary.sectors, 'sector_id')}
          {ranking('Clientes con más incidencias', summary.customers, 'customer_id')}
        </div>
      </section>
      <section className="report-section"><SectionHeading number="05" title="Circuitos y tipos" />
        <div className="grid gap-x-8 gap-y-4 xl:grid-cols-2">
          {ranking('Circuitos con más incidencias', summary.circuits, 'circuit_id')}
          {ranking('Tipos de incidencia', summary.incident_types, 'incident_type_id')}
        </div>
      </section>
      <section className="report-section grid gap-4 xl:grid-cols-2">
        {view !== 'node' && ranking('Nodos de distribución', summary.nodes ?? [], 'node_id')}
        {view !== 'responsible' && ranking('Responsables', summary.responsibles ?? [], 'responsible_id')}
        <p className="text-xs text-muted xl:col-span-2">Estos rankings incluyen solo tickets con Nodo o Responsable asignado. Los KPI conservan los tickets sin asignación.</p>
      </section>
      <section className="report-section analytics-card"><SectionHeading number="06" title="Iniciadas vs cerradas" /><ActivityChart rows={summary.activity ?? []} /></section>
      <section className="report-section grid gap-4 xl:grid-cols-2"><div className="analytics-card"><SectionHeading number="07" title="Distribución por hora" /><DistributionChart title="Distribución por hora" rows={summary.hours ?? []} /></div><div className="analytics-card"><SectionHeading number="08" title="Distribución por día" /><DistributionChart title="Distribución por día" rows={summary.weekdays ?? []} /></div></section>
      {!sectorView && <section className="report-section analytics-card"><SectionHeading number="09" title="Duración promedio por sector" /><DistributionChart title="Duración promedio por sector (minutos)" rows={(summary.sector_durations ?? []).map((row) => ({ label: row.label, count: row.average_duration_seconds / 60 }))} /></section>}
      <div className="report-section"><SectionHeading number="10" title="Detalle de tickets" /></div>
      {detail.loading || detail.error || detail.tickets.length === 0 ? <RequestState loading={detail.loading} error={detail.error} empty={detail.tickets.length === 0} onRetry={() => setRetry(retry + 1)} /> : <TicketTable tickets={detail.tickets} />}
      <div className="pagination-bar"><span className="text-xs text-slate-500">Página {Math.floor(offset / 50) + 1} · Las exportaciones incluyen todos los resultados.</span><div className="flex gap-2"><button className="button-secondary" disabled={offset === 0 || detail.loading} onClick={() => change({ offset: offset > 50 ? String(offset - 50) : '' }, false)}>Anterior</button><button className="button-secondary" disabled={detail.loading || Boolean(detail.error) || detail.tickets.length < 50} onClick={() => change({ offset: String(offset + 50) }, false)}>Siguiente</button></div></div>
    </>}
  </>
}
