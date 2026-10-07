import { RequestState } from '../components/RequestState'
import { FeedbackMessage } from '../components/FeedbackMessage'
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
  if (error) return <RequestState error={error} errorTitle="" onRetry={() => setRetry(retry + 1)}><Link className="ml-4 text-primary underline" to="/tickets">Volver a tickets</Link></RequestState>
  if (!ticket) return <RequestState loading compact loadingText="Cargando ticket..." />
  if (edit) return <TicketForm key={ticket.id} ticket={ticket} />
  if (!catalogs) return <RequestState loading compact loadingText="Cargando catálogos..." />
  const state: unknown = location.state
  const saved = state && typeof state === 'object' && 'saved' in state && state.saved === true
  const classification = [
    ['Cliente', `${catalogs.customer.customer_code} — ${catalogs.customer.name}`],
    ['Circuito', `${catalogs.circuit.circuit_code} — ${catalogs.circuit.description}`],
    ['Nodo de distribución', catalogs.node?.name ?? 'Sin asignar'], ['Responsable', catalogs.responsible?.name ?? 'Sin asignar'],
    ['Sector', catalogs.sector.name], ['Departamento', catalogs.department.name],
    ['Tipo de incidencia', catalogs.incidentType.name],
  ]
  const times = [
    ['Inicio', formatDate(ticket.start_at)], ['Fin', formatDate(ticket.end_at)],
    ['Duración', formatDuration(ticket.duration_seconds)],
  ]
  const metadata = [
    ['Fecha de creación', formatDate(ticket.created_at)], ['Última actualización', formatDate(ticket.updated_at)],
  ]
  return <>
    <div className="record-header">
      <div className="min-w-0 max-w-full [overflow-wrap:anywhere]"><p className="module-eyebrow">Operación <span aria-hidden="true">/ 02</span></p><div className="flex flex-wrap items-center gap-3"><h1 className="min-w-0 max-w-full font-mono text-3xl font-bold tracking-tight text-primary">{ticket.reference}</h1><StatusBadge status={ticket.status} /></div><h2 className="mt-2 text-lg font-semibold text-slate-800">{ticket.title}</h2></div>
      <div className="flex gap-2"><Link to="/tickets" className="button-secondary">Volver a tickets</Link><Link to={`/tickets/${ticket.id}/edit`} className="button-primary">Editar ticket</Link></div>
    </div>
    {saved && <FeedbackMessage variant="success" className="mb-3">Cambios guardados correctamente.</FeedbackMessage>}
    <div className="panel overflow-hidden">
      <section aria-labelledby="description-heading" className="record-description m-4">
        <h3 id="description-heading" className="section-label mb-2">Descripción</h3>
        <p className="whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">{ticket.description}</p>
      </section>
      <div className="grid lg:grid-cols-3">
        <section aria-labelledby="classification-heading" className="border-b border-slate-200 p-4 lg:col-span-2 lg:border-r lg:border-b-0">
          <h3 id="classification-heading" className="section-label mb-3">Cliente y clasificación</h3>
          <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">{classification.map(([label, value]) => <div key={label}><dt className="text-xs text-slate-500">{label}</dt><dd className="mt-1 break-words text-sm font-medium text-slate-900">{value}</dd></div>)}</dl>
        </section>
        <section aria-labelledby="times-heading" className="p-4">
          <h3 id="times-heading" className="section-label mb-3">Tiempos operativos</h3>
          <dl className="space-y-3">{times.map(([label, value]) => <div key={label}><dt className="text-xs text-slate-500">{label}</dt><dd className="mt-1 font-mono text-sm tabular-nums text-slate-900">{value}</dd></div>)}</dl>
        </section>
      </div>
      <section aria-labelledby="metadata-heading" className="border-t border-slate-200 bg-slate-50/50 p-4">
        <h3 id="metadata-heading" className="section-label mb-2">Metadatos</h3>
        <dl className="flex flex-wrap gap-x-8 gap-y-2">{metadata.map(([label, value]) => <div key={label} className="flex flex-wrap items-baseline gap-2"><dt className="text-xs text-slate-500">{label}</dt><dd className="text-xs tabular-nums text-slate-600">{value}</dd></div>)}</dl>
      </section>
    </div>
  </>
}
