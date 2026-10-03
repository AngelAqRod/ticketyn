import { useState } from 'react'
import { Link } from 'react-router'
import { ArrowRight, RefreshCw } from 'lucide-react'
import { useTickets } from '../hooks/useTickets'
import { useTicketStats } from '../hooks/useTicketStats'
import { PageHeading } from '../components/PageHeading'
import { RequestState } from '../components/RequestState'
import { MetricStrip } from '../components/MetricStrip'
import { SectionHeading } from '../components/SectionHeading'
import { TicketTable } from '../components/TicketTable'

export function Dashboard() {
  const [refresh, setRefresh] = useState(0)
  const { loading, tickets, error } = useTickets(0, refresh)
  const { loading: statsLoading, stats, error: statsError } = useTicketStats(refresh)
  const cards = [
    { title: 'Tickets totales', count: stats?.total },
    { title: 'Tickets abiertos', count: stats?.open },
    { title: 'Tickets cerrados', count: stats?.closed },
  ]
  return <>
    <PageHeading title="Dashboard" description="Una vista global de tus incidencias y los tickets más recientes." action={<button className="button-secondary" disabled={loading || statsLoading} onClick={() => setRefresh(refresh + 1)}><RefreshCw size={15} aria-hidden="true" />Actualizar</button>} />
    <section aria-label="Estadísticas globales de tickets" aria-busy={statsLoading}>
      <SectionHeading number="01" title="Panorama de incidencias" />
      <MetricStrip items={cards.map(({ title, count }, index) => ({ label: title, value: statsLoading || statsError ? '—' : count, tone: index === 1 ? 'primary' : index === 2 ? 'muted' : undefined }))} />
      {statsLoading && <p role="status" className="mt-2 text-sm text-slate-500">Cargando estadísticas...</p>}
      {statsError && <div role="alert" className="panel mt-4 p-4">
        <p className="font-medium text-slate-900">Error al cargar estadísticas</p>
        <p className="mt-1 text-sm text-slate-600">{statsError}</p>
        <button className="button-secondary mt-3" onClick={() => setRefresh(refresh + 1)}>Reintentar estadísticas</button>
      </div>}
    </section>
    <section className="mt-5" aria-labelledby="recent-heading">
      <SectionHeading number="02" title="Tickets recientes" id="recent-heading" action={<Link to="/tickets" className="inline-flex items-center gap-2 text-xs font-semibold text-primary hover:underline">Ver tickets<ArrowRight size={15} aria-hidden="true" /></Link>} />
      {loading || error || tickets.length === 0 ? <RequestState loading={loading} error={error} empty={tickets.length === 0} onRetry={() => setRefresh(refresh + 1)} /> : <TicketTable tickets={tickets.slice(0, 5)} />}
    </section>
  </>
}
