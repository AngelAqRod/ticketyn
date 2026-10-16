import { useSearchParams } from 'react-router'
import { ChangeReports } from './ChangeReports'
import { Link } from 'react-router'
import { InternalReportDetail } from '../components/InternalReportDetail'
import { PaginationBar } from '../components/PaginationBar'
import { PeriodShortcuts } from '../components/PeriodShortcuts'
import { EscalationStatistics } from '../components/EscalationStatistics'
import { FeedbackMessage } from '../components/FeedbackMessage'
import { useEffect, useMemo, useState } from 'react'
import { FileText, FileSpreadsheet, RefreshCw, SlidersHorizontal, Tickets, CircleCheck, Clock3, Timer } from 'lucide-react'
import { listSectors, listNodes, listResponsibles, listDepartments, listInternalIncidentTypes, listProviders } from '../api'
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
  const [scope] = useSearchParams()
  return scope.get('scope') === 'changes' ? <ChangeReports/> : <TicketReports/>
}
function TicketReports() {
  const { params, change } = useUrlFilters([...reportFilterKeys, 'scope', 'status', 'department_id', 'incident_type_id', 'provider_id'])
  const internal = params.get('scope') === 'internal'
  const [today] = useState(() => new Date())
  const filterKey = params.toString()
  const selection = useMemo(() => {
    try {
      const selection = reportPeriod(new URLSearchParams(filterKey), today)
      if (internal) {
        for (const key of ['sector_id','node_id','responsible_id','department_id','incident_type_id','provider_id'] as const) {
          const value = params.get(key)
          if (!value || (key === 'provider_id' && value === 'none')) continue
          if (!Number.isInteger(Number(value)) || Number(value) <= 0) throw new Error('Selección inválida.')
          selection.query[key] = Number(value)
        }
        if (params.get('provider_id') === 'none') selection.query.without_provider = true
        if (params.get('status')) selection.query.status = params.get('status')!
      }
      return { ...selection, error: null }
    }
    catch (error) {
      const fallback = reportPeriod(new URLSearchParams(), today)
      const custom = params.get('period') === 'custom' || params.has('from') || params.has('to')
      return { ...fallback, period: custom ? 'custom' : params.get('period') ?? '30', from: params.get('from') ?? '', to: params.get('to') ?? '', error: message(error) }
    }
  }, [filterKey, today, internal])
  const view = params.get('view') ?? 'general'
  const sectorView = view === 'sector'
  const dimension = view === 'node' ? { key: 'node_id', label: 'Nodo' } : view === 'responsible' ? { key: 'responsible_id', label: 'Responsable' } : { key: 'sector_id', label: 'Sector' }
  const scopedView = view !== 'general'
  const missingSector = scopedView && !params.get(dimension.key)
  const invalid = selection.error || (missingSector ? `Selecciona un ${dimension.label.toLowerCase()} para consultar el reporte.` : null)
  const queryKey = JSON.stringify([internal, selection.query])
  const [summary, setSummary] = useState<ReportSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const [nodes, setNodes] = useState<Sector[]>([])
  const [responsibles, setResponsibles] = useState<Sector[]>([])
  const [sectors, setSectors] = useState<Sector[]>([])
  const [sectorError, setSectorError] = useState<string | null>(null)
  const [sectorLoading, setSectorLoading] = useState(true)
  const [extraCatalogs, setExtraCatalogs] = useState<Sector[][]>([[],[],[]])
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    setSectorLoading(true); setSectorError(null)
    Promise.all([listSectors(controller.signal, true), listNodes(controller.signal, true), listResponsibles(controller.signal, true), ...(internal ? [listDepartments(controller.signal,true), listInternalIncidentTypes(controller.signal,true), listProviders(controller.signal,true)] : [])]).then(([rows, nodeRows, responsibleRows, ...extra]) => { if (!controller.signal.aborted) { setExtraCatalogs(extra); setSectors(rows); setNodes(nodeRows); setResponsibles(responsibleRows); setSectorLoading(false) } }).catch((failure: unknown) => { if (!controller.signal.aborted) { setSectorError(message(failure)); setSectorLoading(false) } })
    return () => controller.abort()
  }, [retry, internal])
  useEffect(() => {
    setExportError(null)
    if (invalid) { setSummary(null); setLoading(false); setError(null); return }
    const controller = new AbortController()
    setLoading(true); setSummary(null); setError(null)
    getReport(selection.query, controller.signal, internal).then((data) => { if (!controller.signal.aborted) { setSummary(data); setLoading(false) } }).catch((failure: unknown) => { if (!controller.signal.aborted) { setError(message(failure)); setLoading(false) } })
    return () => controller.abort()
  }, [queryKey, invalid, retry])
  const offsetValue = Number(params.get('offset') ?? 0)
  const offset = Number.isInteger(offsetValue) && offsetValue >= 0 ? offsetValue : 0
  const { from, to, sector_id, node_id, responsible_id } = selection.query
  const detail = useTickets(offset, retry, { from, to, sector_id, node_id, responsible_id }, internal ? 'Contexto interno' : invalid)
  function period(value: string) {
    change({ period: value, ...(value === 'custom' ? { from: selection.from, to: selection.to } : { from: '', to: '' }) })
  }
  async function exportReport(format: 'pdf' | 'xlsx') {
    if (exporting || invalid) return
    setExporting(true); setExportError(null)
    try { await downloadReport(format, selection.query, internal) } catch (failure) { setExportError(message(failure)) } finally { setExporting(false) }
  }
  function ranking(title: string, rows: ReportRanking[], field: string) {
    if (internal) return <RankingSection key={field} title={title} rows={rows} destination={(row) => { const next = new URLSearchParams(params); next.set(field, field === 'provider_id' && row.id === 0 ? 'none' : String(row.id)); next.delete('offset'); return `/reports?${next}` }} />
    const reportView = field === 'sector_id' ? 'sector' : field === 'node_id' ? 'node' : field === 'responsible_id' ? 'responsible' : null
    return <RankingSection key={field} title={title} rows={rows} destination={(row) => view === 'general' && reportView ? `/reports?${new URLSearchParams({ view: reportView, period: selection.period === 'all' ? 'all' : 'custom', [field]: String(row.id), ...(selection.period === 'all' ? {} : { from: selection.from, to: selection.to }) })}` : ticketDrillDown(field, row.id, selection.from, selection.to, sector_id, node_id, responsible_id)} />
  }
  return <>
    <nav className="segmented-control mb-4" aria-label="Ámbito de reportería"><Link className="segment-button" aria-current={!internal ? 'page' : undefined} to="/reports">Tickets</Link><Link className="segment-button" aria-current={internal ? 'page' : undefined} to="/reports?scope=internal">Tickets internos</Link><Link className="segment-button" to="/reports?scope=changes">Control de cambios</Link></nav>
    <PageHeading title={internal ? 'Reportería de tickets internos' : 'Reportería de tickets'} description="Incidencias por período operativo de Inicio. Una incidencia corresponde a un ticket." action={<div className="flex flex-wrap gap-2"><button className="button-secondary" type="button" onClick={() => setRetry(retry + 1)} disabled={loading}><RefreshCw size={14} aria-hidden="true" />Actualizar</button><button className="button-secondary" type="button" disabled={loading || Boolean(invalid) || Boolean(error) || exporting || !summary} onClick={() => exportReport('pdf')}><FileText size={14} aria-hidden="true" />Exportar PDF</button><button className="button-secondary" type="button" disabled={loading || Boolean(invalid) || Boolean(error) || exporting || !summary} onClick={() => exportReport('xlsx')}><FileSpreadsheet size={14} aria-hidden="true" />Exportar Excel</button></div>} />
    <section className="filter-toolbar" aria-label="Filtros de reportería">
      <SectionHeading number="01" title="Período" icon={<SlidersHorizontal size={15} />} />
      <div className="flex flex-wrap items-center gap-4">
        <div className="segmented-control" role="group" aria-label="Tipo de reporte">
          {['general', 'sector', 'node', 'responsible'].map((view) => <button key={view} type="button" className="segment-button" aria-pressed={view === (params.get('view') ?? 'general')} onClick={() => change({ view, sector_id: '', node_id: '', responsible_id: '' })}>{view === 'general' ? 'General' : view === 'node' ? 'Por nodo' : view === 'responsible' ? 'Por responsable' : 'Por sector'}</button>)}
        </div>
        <PeriodShortcuts includeAll label="Período del reporte" value={selection.period} onChange={period} />
      </div>
      <div className="mt-2 flex flex-wrap items-end gap-3">
        {scopedView && <div className="min-w-0 w-full basis-full flex-1 sm:min-w-64 sm:w-auto sm:basis-0"><FormField id="report-sector" label={dimension.label}><SearchableSelect id="report-sector" label={dimension.label} value={params.get(dimension.key) ?? ''} options={(view === 'node' ? nodes : view === 'responsible' ? responsibles : sectors).map((item) => ({ value: String(item.id), label: item.name }))} onChange={(value) => change({ [dimension.key]: value })} disabled={sectorLoading || Boolean(sectorError)} placeholder={`Selecciona un ${dimension.label.toLowerCase()}`} emptyMessage="No hay sectores." noMatchMessage="No se encontraron sectores." /></FormField></div>}
        {selection.period === 'custom' && <><FormField id="report-from" label="Desde"><input id="report-from" className="form-input" type="date" value={params.get('from') ?? selection.from} onChange={(event) => change({ period: 'custom', from: event.target.value })} /></FormField><FormField id="report-to" label="Hasta"><input id="report-to" className="form-input" type="date" value={params.get('to') ?? selection.to} onChange={(event) => change({ period: 'custom', to: event.target.value })} /></FormField></>}
        {internal && <><FormField id="internal-report-status" label="Estado"><select id="internal-report-status" className="form-input" value={params.get('status') ?? ''} onChange={e=>change({status:e.target.value})}><option value="">Todos</option><option value="OPEN">Abierto</option><option value="CLOSED">Cerrado</option></select></FormField>{[['sector_id','Sector',sectors],['node_id','Nodo',nodes],['responsible_id','Responsable',responsibles],['department_id','Departamento',extraCatalogs[0] ?? []],['incident_type_id','Tipo de incidencia interna',extraCatalogs[1] ?? []],['provider_id','Atribuible a proveedor',extraCatalogs[2] ?? []]].map(([field,label,rows])=>{const key=String(field); if(scopedView && key===dimension.key)return null; return <FormField key={key} id={`internal-report-${key}`} label={String(label)}><select id={`internal-report-${key}`} className="form-input" value={params.get(key) ?? ''} onChange={e=>change({[key]:e.target.value})}><option value="">Todos</option>{key==='provider_id'&&<option value="none">Ninguno</option>}{(rows as Sector[]).map(row=><option key={row.id} value={row.id}>{row.name}{row.active?'':' (Inactivo)'}</option>)}</select></FormField>})}</>}
        <p className="chip chip-neutral">{selection.from} — {selection.to} · {selection.query.timezone}</p>
      </div>
      {sectorError && scopedView && <RequestState compact error={sectorError} errorTitle="" retryText="Reintentar sectores" onRetry={() => setRetry(retry + 1)} />}
    </section>
    {exporting && <RequestState loading compact loadingText="Generando archivo..." className="mb-2 workspace-caption" />}
    {exportError && <FeedbackMessage variant="error" className="mb-3">{exportError}</FeedbackMessage>}
    {invalid ? <p role={missingSector ? 'status' : 'alert'} className="panel p-4 text-sm">{invalid}</p> : loading ? <RequestState loading loadingText="Cargando reporte..." /> : error ? <RequestState error={`Error al cargar reporte: ${error}`} errorTitle="" onRetry={() => setRetry(retry + 1)} /> : summary && <>
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-xs workspace-caption"><h2 className="font-semibold text-slate-800">{summary.node ? `Reporte por Nodo — ${summary.node.name}` : summary.responsible ? `Reporte por Responsable — ${summary.responsible.name}` : summary.sector ? `Reporte por Sector — ${summary.sector.name}` : 'Reporte General'}</h2><span>Generado: {formatDate(summary.generated_at)}</span></div>
      <SectionHeading number="02" title="Resumen" />
      <MetricStrip variant="light" layout={internal ? 'internal-summary' : undefined} items={[
        { label: 'Incidencias iniciadas', value: summary.kpis.started, icon: <Tickets size={20} /> },
        { label: 'Incidencias cerradas', value: summary.kpis.closed, icon: <CircleCheck size={20} />, iconTone: 'success' },
        { color: 'ice', label: 'Duración promedio', value: summary.kpis.average_duration_seconds === null ? '—' : formatDuration(summary.kpis.average_duration_seconds), icon: <Clock3 size={20} /> },
        { color: 'indigo', label: 'Duración acumulada', value: formatDuration(summary.kpis.total_duration_seconds), icon: <Timer size={20} /> },
        ...(internal ? [
        {color:'amber' as const,label:'Tickets de clientes vinculados',value:summary.related_tickets ?? 0},
        {color:'cyan' as const,label:'Incidencias con tickets vinculados',value:summary.with_related ?? 0},
        ] : []),
      ]} />
      {internal && <p className="mt-2 text-xs workspace-caption">Los vínculos corresponden a incidencias internas iniciadas en el período, independientemente de la fecha de los tickets vinculados. No representan afectaciones confirmadas.</p>}
      <p className="mt-2 mb-3 max-w-5xl text-[11px] leading-4 workspace-caption">Iniciadas, evolución, rankings y detalle: Inicio en el período. Cerradas y duraciones: estado Cerrado y Fin en el período, incluso si comenzaron antes. Cerrados sin Fin no aportan duración.</p>
      {summary.kpis.started === 0 && <RequestState compact empty emptyTitle="No hay incidencias iniciadas en este período." emptyDescription="" className="mb-3" />}
      <section className="report-section analytics-card chart-card"><SectionHeading number="03" title="Evolución de incidencias" /><TrendChart trend={summary.trend} granularity={summary.period.granularity} /></section>
      <section className="report-section"><SectionHeading number="04" title="Concentración" />
        <div className={`grid gap-x-8 gap-y-4 ${sectorView ? '' : 'xl:grid-cols-2'}`}>
          {!sectorView && ranking('Sectores con más incidencias', summary.sectors, 'sector_id')}
          {internal ? ranking('Incidencias internas por proveedor', summary.providers ?? [], 'provider_id') : ranking('Clientes con más incidencias', summary.customers, 'customer_id')}
        </div>
      </section>
      <section className="report-section"><SectionHeading number="05" title={internal ? "Clasificación interna" : "Circuitos y tipos"} />
        <div className="grid gap-x-8 gap-y-4 xl:grid-cols-2">
          {!internal && ranking('Circuitos con más incidencias', summary.circuits, 'circuit_id')}
          {ranking(internal ? 'Tipos de incidencia interna' : 'Tipos de incidencia', summary.incident_types, 'incident_type_id')}
        </div>
      </section>
      <section className="report-section grid gap-4 xl:grid-cols-2">
        {view !== 'node' && ranking('Nodos de distribución', summary.nodes ?? [], 'node_id')}
        {view !== 'responsible' && ranking('Responsables', summary.responsibles ?? [], 'responsible_id')}
        <p className="text-xs workspace-caption xl:col-span-2">Estos rankings incluyen solo tickets con Nodo o Responsable asignado. Los KPI conservan los tickets sin asignación.</p>
      </section>
      <section className="report-section"><SectionHeading number="06" title="Departamentos" />
        <div className="grid gap-4 xl:grid-cols-2">
          {ranking('Tickets por departamento', summary.departments ?? [], 'department_id')}
          <div className="analytics-card chart-card"><h3 className="mb-3 text-sm font-semibold">Tiempo de resolución por departamento</h3><DistributionChart title="Tiempo de resolución por departamento (minutos)" rows={(summary.department_durations ?? []).map((row) => ({ label: row.label, count: row.average_duration_seconds / 60 }))} /></div>
        </div>
      </section>
      <section className="report-section analytics-card chart-card"><SectionHeading number="07" title="Iniciadas vs cerradas" /><ActivityChart rows={summary.activity ?? []} /></section>
      <section className="report-section grid gap-4 xl:grid-cols-2"><div className="analytics-card chart-card"><SectionHeading number="08" title="Distribución por hora" /><DistributionChart title="Distribución por hora" rows={summary.hours ?? []} /></div><div className="analytics-card chart-card"><SectionHeading number="09" title="Distribución por día" /><DistributionChart title="Distribución por día" rows={summary.weekdays ?? []} /></div></section>
      {!sectorView && <section className="report-section analytics-card chart-card"><SectionHeading number="10" title="Duración promedio por sector" /><DistributionChart title="Duración promedio por sector (minutos)" rows={(summary.sector_durations ?? []).map((row) => ({ label: row.label, count: row.average_duration_seconds / 60 }))} /></section>}
      <div className="report-section"><SectionHeading number="11" title="Detalle de tickets" /></div>
      {internal ? <InternalReportDetail query={selection.query} offset={offset} retry={retry} onPage={value=>change({offset:String(value)},false)}/> : <>
      {detail.loading || detail.error || detail.tickets.length === 0 ? <RequestState loading={detail.loading} error={detail.error} empty={detail.tickets.length === 0} onRetry={() => setRetry(retry + 1)} /> : <TicketTable tickets={detail.tickets} />}
      <PaginationBar page={Math.floor(offset / 50) + 1} info={<span className="text-xs">Página {Math.floor(offset / 50) + 1} · Las exportaciones incluyen todos los resultados.</span>} previousDisabled={offset === 0 || detail.loading} nextDisabled={detail.loading || Boolean(detail.error) || detail.tickets.length < 50} onPrevious={() => change({ offset: offset > 50 ? String(offset - 50) : '' }, false)} onNext={() => change({ offset: String(offset + 50) }, false)} />
      </>}
    </>}
    {!internal && !invalid && <EscalationStatistics query={selection.query} summary={summary?.escalations ?? null} people={responsibles} loading={loading} onRecipientChange={(value) => change({ recipient_id: value })} />}
  </>
}
