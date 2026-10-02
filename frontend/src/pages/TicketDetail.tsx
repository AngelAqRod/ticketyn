import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router'
import { getTicket, getTicketCatalogs } from '../api'
import type { Ticket } from '../types/ticket'
import { ApiError } from '../api/client'
import { formatDate, formatDuration } from '../lib/format'
import { StatusBadge } from '../components/StatusBadge'
import { TicketForm } from '../components/TicketForm'

export function TicketDetail({ edit = false }: { edit?: boolean }) {
  const { id } = useParams()
  const location = useLocation()
  const [ticket, setTicket] = useState<Ticket | null>(null)
  const [catalogs, setCatalogs] = useState<Awaited<ReturnType<typeof getTicketCatalogs>> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setTicket(null); setCatalogs(null); setError(null)
    async function load() {
      try {
        if (!id || !/^\d+$/.test(id) || Number(id) < 1) throw new ApiError('Ticket no encontrado.', 404)
        const current = await getTicket(Number(id), controller.signal)
        const names = edit ? null : await getTicketCatalogs(current, controller.signal)
        if (!controller.signal.aborted) { setTicket(current); setCatalogs(names) }
      } catch (failure) {
        if (!controller.signal.aborted) setError(failure instanceof ApiError && failure.status === 404 ? 'Ticket o catálogo relacionado no encontrado.' : failure instanceof Error ? failure.message : 'No se pudo cargar el ticket.')
      }
    }
    void load()
    return () => controller.abort()
  }, [id, edit, retry, location.key])
  if (error) return <div className="panel p-6"><p role="alert">{error}</p><button type="button" className="button-secondary mt-4" onClick={() => setRetry(retry + 1)}>Reintentar</button><Link className="ml-4 text-emerald-800 underline" to="/tickets">Volver a tickets</Link></div>
  if (!ticket) return <p role="status">Cargando ticket...</p>
  if (edit) return <TicketForm key={ticket.id} ticket={ticket} />
  if (!catalogs) return <p role="status">Cargando catálogos...</p>
  const state: unknown = location.state
  const saved = state && typeof state === 'object' && 'saved' in state && state.saved === true
  const fields = [
    ['Cliente', `${catalogs.customer.customer_code} — ${catalogs.customer.name}`],
    ['Circuito', `${catalogs.circuit.circuit_code} — ${catalogs.circuit.description}`],
    ['Sector', catalogs.sector.name], ['Departamento', catalogs.department.name],
    ['Tipo de incidencia', catalogs.incidentType.name],
    ['Inicio', formatDate(ticket.start_at)], ['Fin', formatDate(ticket.end_at)],
    ['Duración', formatDuration(ticket.duration_seconds)],
    ['Fecha de creación', formatDate(ticket.created_at)], ['Última actualización', formatDate(ticket.updated_at)],
  ]
  return <>
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div><div className="flex items-center gap-4"><h1 className="text-3xl font-semibold tracking-tight text-slate-900">{ticket.reference}</h1><StatusBadge status={ticket.status} /></div><h2 className="mt-3 text-xl font-medium text-slate-800">{ticket.title}</h2></div>
      <div className="flex gap-3"><Link to="/tickets" className="button-secondary">Volver a tickets</Link><Link to={`/tickets/${ticket.id}/edit`} className="button-primary">Editar ticket</Link></div>
    </div>
    {saved && <p role="status" className="mb-5 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-900">Cambios guardados correctamente.</p>}
    <div className="panel p-5 sm:p-7"><h3 className="mb-2 font-semibold">Descripción</h3><p className="whitespace-pre-wrap break-words text-sm text-slate-700">{ticket.description}</p>
      <dl className="mt-6 grid gap-x-8 gap-y-5 border-t border-slate-100 pt-6 sm:grid-cols-2">{fields.map(([label, value]) => <div key={label}><dt className="text-xs font-medium text-slate-500">{label}</dt><dd className="mt-1 break-words text-sm text-slate-900">{value}</dd></div>)}</dl>
    </div>
  </>
}
