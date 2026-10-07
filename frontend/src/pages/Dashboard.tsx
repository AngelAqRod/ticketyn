import { useState } from 'react'
import { Link } from 'react-router'
import { ArrowRight, RefreshCw, Tickets, Clock3, CircleCheck } from 'lucide-react'
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
    { title: 'Tickets totales', count: stats?.total, icon: <Tickets size={16} /> },
    { title: 'Tickets abiertos', count: stats?.open, icon: <Clock3 size={16} />, iconTone: 'warning' as const },
    { title: 'Tickets cerrados', count: stats?.closed, icon: <CircleCheck size={16} />, iconTone: 'success' as const },
  ]
  return <>
    <PageHeading title="Dashboard" description="Una vista global de tus incidencias y los tickets más recientes." action={<button className="button-secondary" disabled={loading || statsLoading} onClick={() => setRefresh(refresh + 1)}><RefreshCw size={15} aria-hidden="true" />Actualizar</button>} />
    <section aria-label="Estadísticas globales de tickets" aria-busy={statsLoading}>
      <SectionHeading number="01" title="Panorama de incidencias" />
      <MetricStrip variant="light" items={cards.map(({ title, count, icon, iconTone }) => ({ label: title, value: statsLoading || statsError ? '—' : count, icon, iconTone }))} />
      {statsLoading && <RequestState loading compact loadingText="Cargando estadísticas..." className="mt-2" />}
      {statsError && <RequestState error={statsError} errorTitle="Error al cargar estadísticas" retryText="Reintentar estadísticas" onRetry={() => setRefresh(refresh + 1)} className="mt-4" />}
    </section>
    <section className="mt-5" aria-labelledby="recent-heading">
      <SectionHeading number="02" title="Tickets recientes" id="recent-heading" action={<Link to="/tickets" className="inline-flex items-center gap-2 text-xs font-semibold text-primary hover:underline">Ver tickets<ArrowRight size={15} aria-hidden="true" /></Link>} />
      {loading || error || tickets.length === 0 ? <RequestState loading={loading} error={error} empty={tickets.length === 0} onRetry={() => setRefresh(refresh + 1)} /> : <TicketTable tickets={tickets.slice(0, 5)} />}
    </section>
  </>
}
