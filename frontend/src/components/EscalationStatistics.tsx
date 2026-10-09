import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { ArrowUpRight, CircleCheck, Clock3, Tickets } from 'lucide-react'
import { escalationTickets } from '../api/escalations'
import type { Responsible } from '../types/catalog'
import type { EscalationSummary, EscalationTicket } from '../types/escalation'
import { reportParams } from '../api/reports'
import type { ReportQuery } from '../types/report'
import { formatDuration } from '../lib/format'
import { MetricStrip } from './MetricStrip'
import { FormField } from './FormField'
import { SearchableSelect } from './SearchableSelect'
import { RankingSection } from './RankingSection'
import { TrendChart, DistributionChart } from './ReportCharts'
import { RequestState } from './RequestState'

export function EscalationStatistics({ query, summary, people, loading: reportLoading = false, onRecipientChange }: {
  query: ReportQuery; summary: EscalationSummary | null; people: Responsible[]; loading?: boolean; onRecipientChange: (value: string) => void
}) {
  const recipient = query.recipient_id ? String(query.recipient_id) : ''
  const [tickets, setTickets] = useState<EscalationTicket[]>([])
  const [loading, setLoading] = useState(true), [error, setError] = useState<string | null>(null), [retry, setRetry] = useState(0)
  const [page, setPage] = useState({ query: '', offset: 0 })
  const queryKey = reportParams(query)
  const offset = page.query === queryKey ? page.offset : 0
  const setOffset = (value: number) => setPage({ query: queryKey, offset: value })
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null); setTickets([])
    const detail = new URLSearchParams(queryKey); detail.set('limit', '50'); detail.set('offset', String(offset))
    escalationTickets(detail, controller.signal).then((rows) => { if (!controller.signal.aborted) { setTickets(rows); setLoading(false) } }).catch((failure: unknown) => { if (!controller.signal.aborted) { setLoading(false); setError(failure instanceof Error ? failure.message : 'No se pudieron cargar los tickets relacionados.') } })
    return () => controller.abort()
  }, [queryKey, retry, offset])
  return <section className="report-section panel p-4 lg:p-5" aria-labelledby="escalation-statistics-heading">
    <div className="section-heading"><span className="icon-surface" aria-hidden="true"><ArrowUpRight size={16} /></span><h2 id="escalation-statistics-heading">Estadísticas de escalamientos</h2></div>
    <p className="mb-3 text-xs text-muted">Colaboración independiente de la asignación principal. Período: creación del escalamiento. Porcentaje: tickets únicos escalados / todos los tickets del contexto seleccionado.</p>
    <div className="my-3 grid gap-3 sm:grid-cols-3">
      <FormField id="stats-recipient" label="Escalamientos recibidos por"><SearchableSelect id="stats-recipient" label="Destinatario" value={recipient} onChange={onRecipientChange} options={people.map((person) => ({ value: String(person.id), label: person.name }))} placeholder="Todas las personas" emptyMessage="No hay responsables." noMatchMessage="Sin coincidencias." /></FormField>

    </div>
    <RequestState compact loading={reportLoading} onRetry={() => setRetry(retry + 1)} />
    {!summary && error && <RequestState compact error={error} onRetry={() => setRetry(retry + 1)} />}
    {summary && <>
      <MetricStrip variant="light" items={[
        { label: 'Tickets únicos escalados', value: summary.escalated_tickets, icon: <Tickets size={20} /> },
        { label: 'Eventos de escalamiento', value: summary.events, icon: <ArrowUpRight size={20} /> },
        { label: 'Escalamientos activos', value: summary.active, icon: <Clock3 size={20} /> },
        { label: 'Escalamientos finalizados', value: summary.finished, icon: <CircleCheck size={20} />, iconTone: 'success' },
        { label: 'Duración promedio de escalamientos', value: summary.average_duration_seconds === null ? '—' : formatDuration(summary.average_duration_seconds) },
        { label: 'Tickets con escalamiento', value: `${summary.escalated_percentage.toFixed(1)} %` },
      ]} />
      <div className="mt-4 grid gap-4 xl:grid-cols-2"><div className="analytics-card"><h3 className="section-label mb-3">Tickets con y sin escalamiento</h3><DistributionChart title="Tickets con y sin escalamiento" rows={[{ label: 'Con escalamiento', count: summary.escalated_tickets }, { label: 'Sin escalamiento', count: summary.total_tickets - summary.escalated_tickets }]} /></div><div className="analytics-card"><h3 className="section-label mb-3">Evolución de escalamientos</h3><TrendChart trend={summary.trend} granularity={summary.granularity} title="Evolución de escalamientos" countLabel="Escalamientos" /></div></div>
      <div className="mt-4"><RankingSection title="Escalamientos recibidos por persona" rows={summary.recipients} countLabel="Escalamientos" onSelect={(row) => onRecipientChange(String(row.id))} /></div>
      <h3 className="section-label mt-4 mb-2">Tickets relacionados · {recipient ? people.find((item) => String(item.id) === recipient)?.name : 'Todos los destinatarios'}</h3>
      <RequestState compact loading={loading} error={error} onRetry={() => setRetry(retry + 1)} empty={!tickets.length && !loading && !error} emptyTitle="Sin tickets relacionados" emptyDescription="No hay escalamientos en esta selección." />
      {tickets.length > 0 && <div className="table-surface overflow-x-auto"><table className="operation-table"><thead><tr><th scope="col">Referencia</th><th scope="col">Título</th><th scope="col">Estado</th></tr></thead><tbody>{tickets.map((ticket) => <tr key={ticket.id}><td><Link className="button-ghost" to={`/tickets/${ticket.id}`}>{ticket.reference}</Link></td><td>{ticket.title}</td><td>{ticket.status === 'OPEN' ? 'Abierto' : 'Cerrado'}</td></tr>)}</tbody></table></div>}
      <div className="pagination-bar"><span>Página {offset / 50 + 1}</span><div className="flex gap-2"><button type="button" className="button-secondary" aria-label="Página anterior de tickets escalados" disabled={offset === 0 || loading} onClick={() => setOffset(offset - 50)}>Anterior</button><button type="button" className="button-secondary" aria-label="Página siguiente de tickets escalados" disabled={tickets.length < 50 || loading} onClick={() => setOffset(offset + 50)}>Siguiente</button></div></div>
    </>}
  </section>
}
