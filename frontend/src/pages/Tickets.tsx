import { useState } from 'react'
import { Link, useLocation } from 'react-router'
import { ArrowLeft, ArrowRight, RefreshCw } from 'lucide-react'
import { useTickets } from '../hooks/useTickets'
import { PageHeading } from '../components/PageHeading'
import { RequestState } from '../components/RequestState'
import { TicketTable } from '../components/TicketTable'

export function Tickets() {
  const location = useLocation()
  const navigationState: unknown = location.state
  const createdReference = navigationState && typeof navigationState === 'object'
    && 'createdReference' in navigationState && typeof navigationState.createdReference === 'string'
    ? navigationState.createdReference : null
  const [offset, setOffset] = useState(0)
  const [refresh, setRefresh] = useState(0)
  const { loading, tickets, error } = useTickets(offset, refresh)
  return <>
    <PageHeading title="Tickets" description="Consulta las incidencias registradas, de la más reciente a la más antigua." action={<div className="flex gap-2"><button className="button-secondary" disabled={loading} onClick={() => setRefresh(refresh + 1)}><RefreshCw size={15} aria-hidden="true" />Actualizar</button><Link className="button-primary" to="/tickets/new">Nuevo ticket</Link></div>} />
    {createdReference && <p role="status" className="mb-5 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">Ticket {createdReference} creado correctamente.</p>}
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-500">
      <span>Todos los estados</span><span>Fechas en tu zona horaria local</span>
    </div>
    {loading || error || tickets.length === 0 ? <RequestState loading={loading} error={error} empty={tickets.length === 0} onRetry={() => setRefresh(refresh + 1)} /> : <TicketTable tickets={tickets} />}
    <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
      <p className="text-xs text-slate-500">Página {offset / 50 + 1}{!loading && !error && tickets.length > 0 ? ` · Registros ${offset + 1}–${offset + tickets.length}` : ''}</p>
      <div className="flex gap-2"><button className="button-secondary" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - 50))}><ArrowLeft size={15} aria-hidden="true" />Anterior</button>
        <button className="button-secondary" disabled={loading || Boolean(error) || tickets.length < 50} onClick={() => setOffset(offset + 50)}>Siguiente<ArrowRight size={15} aria-hidden="true" /></button></div>
    </div>
  </>
}
