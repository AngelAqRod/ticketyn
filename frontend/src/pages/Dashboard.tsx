import { useState } from 'react'
import { Link } from 'react-router'
import { ArrowRight, Ticket, CircleDot, CircleCheck, RefreshCw } from 'lucide-react'
import { useTickets } from '../hooks/useTickets'
import { PageHeading } from '../components/PageHeading'
import { RequestState } from '../components/RequestState'
import { TicketTable } from '../components/TicketTable'

export function Dashboard() {
  const [refresh, setRefresh] = useState(0)
  const { loading, tickets, error } = useTickets(0, refresh)
  const cards = [
    { title: 'Tickets totales', count: tickets.length, icon: Ticket, style: 'bg-slate-100 text-slate-600' },
    { title: 'Tickets abiertos', count: tickets.filter((ticket) => ticket.status === 'OPEN').length, icon: CircleDot, style: 'bg-amber-50 text-amber-700' },
    { title: 'Tickets cerrados', count: tickets.filter((ticket) => ticket.status === 'CLOSED').length, icon: CircleCheck, style: 'bg-emerald-50 text-emerald-700' },
  ]
  return <>
    <PageHeading title="Dashboard" description="Una vista rápida de tus incidencias más recientes." action={<button className="button-secondary" disabled={loading} onClick={() => setRefresh(refresh + 1)}><RefreshCw size={15} aria-hidden="true" />Actualizar</button>} />
    <section aria-label="Resumen de la página cargada">
      <div className="grid gap-5 sm:grid-cols-3">
        {cards.map(({ title, count, icon: Icon, style }) => <article key={title} className="panel p-6">
          <div className="flex items-center justify-between gap-3"><h2 className="text-sm font-medium text-slate-600">{title}</h2><span className={`rounded-lg p-2 ${style}`}><Icon size={18} aria-hidden="true" /></span></div>
          <p className="mt-4 text-3xl font-semibold tracking-tight text-slate-900">{loading || error ? '—' : count}</p>
          <p className="mt-2 text-xs text-slate-500">En la página cargada</p>
        </article>)}
      </div>
      <p className="mt-4 text-xs leading-5 text-slate-500">Este resumen corresponde a la primera página de hasta 50 tickets. No representa un conteo global.</p>
    </section>
    <section className="mt-10" aria-labelledby="recent-heading">
      <div className="mb-4 flex items-center justify-between gap-3"><h2 id="recent-heading" className="font-semibold text-slate-900">Tickets recientes</h2><Link to="/tickets" className="inline-flex items-center gap-2 text-sm font-medium text-emerald-800 hover:underline">Ver tickets<ArrowRight size={15} aria-hidden="true" /></Link></div>
      {loading || error || tickets.length === 0 ? <RequestState loading={loading} error={error} empty={tickets.length === 0} onRetry={() => setRefresh(refresh + 1)} /> : <TicketTable tickets={tickets.slice(0, 5)} />}
    </section>
  </>
}
