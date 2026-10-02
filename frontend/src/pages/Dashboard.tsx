import { useState } from 'react'
import { Link } from 'react-router'
import { ArrowRight, RefreshCw } from 'lucide-react'
import { useTickets } from '../hooks/useTickets'
import { useTicketStats } from '../hooks/useTicketStats'
import { PageHeading } from '../components/PageHeading'
import { RequestState } from '../components/RequestState'
import { TicketTable } from '../components/TicketTable'

export function Dashboard() {
  const [refresh, setRefresh] = useState(0)
  const { loading, tickets, error } = useTickets(0, refresh)
  const { loading: statsLoading, stats, error: statsError } = useTicketStats(refresh)
  const cards = [
    { title: 'Tickets totales', count: stats?.total, style: 'text-slate-900' },
    { title: 'Tickets abiertos', count: stats?.open, style: 'text-amber-800' },
    { title: 'Tickets cerrados', count: stats?.closed, style: 'text-slate-600' },
  ]
  return <>
    <PageHeading title="Dashboard" description="Una vista global de tus incidencias y los tickets más recientes." action={<button className="button-secondary" disabled={loading || statsLoading} onClick={() => setRefresh(refresh + 1)}><RefreshCw size={15} aria-hidden="true" />Actualizar</button>} />
    <section aria-label="Estadísticas globales de tickets" aria-busy={statsLoading}>
      <div className="panel grid grid-cols-1 divide-y divide-slate-200 sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        {cards.map(({ title, count, style }) => <article key={title} className="flex items-center justify-between gap-4 px-4 py-3 sm:block">
          <h2 className="section-label">{title}</h2>
          <p className={`mt-0 font-mono text-2xl font-semibold tabular-nums sm:mt-1 ${style}`}>{statsLoading || statsError ? '—' : count}</p>
        </article>)}
      </div>
      {statsLoading && <p role="status" className="mt-2 text-sm text-slate-500">Cargando estadísticas...</p>}
      {statsError && <div role="alert" className="panel mt-4 p-4">
        <p className="font-medium text-slate-900">Error al cargar estadísticas</p>
        <p className="mt-1 text-sm text-slate-600">{statsError}</p>
        <button className="button-secondary mt-3" onClick={() => setRefresh(refresh + 1)}>Reintentar estadísticas</button>
      </div>}
    </section>
    <section className="mt-5" aria-labelledby="recent-heading">
      <div className="mb-2 flex items-center justify-between gap-3"><h2 id="recent-heading" className="text-sm font-semibold text-slate-900">Tickets recientes</h2><Link to="/tickets" className="inline-flex items-center gap-2 text-sm font-medium text-emerald-800 hover:underline">Ver tickets<ArrowRight size={15} aria-hidden="true" /></Link></div>
      {loading || error || tickets.length === 0 ? <RequestState loading={loading} error={error} empty={tickets.length === 0} onRetry={() => setRefresh(refresh + 1)} /> : <TicketTable tickets={tickets.slice(0, 5)} />}
    </section>
  </>
}
