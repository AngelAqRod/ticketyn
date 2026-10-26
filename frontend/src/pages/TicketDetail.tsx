import { Can } from '../auth/permissions'
import { RelatedInternalTicket } from '../components/RelatedInternalTicket'
import { CircuitLink } from '../components/CircuitLink'
import { Check, Clock, FileText, Pencil, Tag, Ticket as TicketIcon } from 'lucide-react'
import { TicketEscalations } from '../components/TicketEscalations'
import { RequestState } from '../components/RequestState'
import { FeedbackMessage } from '../components/FeedbackMessage'
import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router'
import { getTicket, getTicketCatalogs, type TicketDetailCatalogs } from '../api'
import type { Ticket } from '../types/ticket'
import { ApiError } from '../api/client'
import { formatDate, formatDuration } from '../lib/format'
import { StatusBadge } from '../components/StatusBadge'
import { TicketForm } from '../components/TicketForm'
import { TicketReportDownload } from '../components/TicketReportDownload'
import { TicketQuickClose } from '../components/TicketQuickClose'
import { TicketFollowUp } from '../components/TicketFollowUp'

export function TicketDetail({ edit = false }: { edit?: boolean }) {
  const { id } = useParams()
  const location = useLocation()
  const [ticket, setTicket] = useState<Ticket | null>(null)
  const [catalogs, setCatalogs] = useState<TicketDetailCatalogs | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)
  const [closedReference, setClosedReference] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    setTicket(null); setCatalogs(null); setError(null); setClosedReference(null)
    async function load() {
      try {
        if (!id || !/^\d+$/.test(id) || Number(id) < 1) throw new ApiError('Ticket no encontrado.', 404)
        const current = await getTicket(Number(id), controller.signal)
        const names = edit ? null : await getTicketCatalogs(current, controller.signal, true)
        if (!controller.signal.aborted) { setTicket(current); setCatalogs(names) }
      } catch (failure) {
        if (!controller.signal.aborted) setError(failure instanceof ApiError && failure.status === 404 ? 'Ticket o catálogo relacionado no encontrado.' : failure instanceof Error ? failure.message : 'No se pudo cargar el ticket.')
      }
    }
    void load()
    return () => controller.abort()
  }, [id, edit, retry, location.key])

  if (error) return <RequestState error={error} errorTitle="" onRetry={() => setRetry(retry + 1)}><Link className="ml-4 text-primary underline" to="/tickets">Volver a tickets</Link></RequestState>
  if (!ticket) return <RequestState loading compact className="workspace-caption" loadingText="Cargando ticket..." />
  if (edit) return <TicketForm key={ticket.id} ticket={ticket} />
  if (!catalogs) return <RequestState loading compact className="workspace-caption" loadingText="Cargando catálogos..." />

  const state: unknown = location.state
  const saved = Boolean(state && typeof state === 'object' && 'saved' in state && (state as { saved?: unknown }).saved === true)
  const durationText = formatDuration(ticket.duration_seconds, ticket.status)
  const circuit = catalogs.circuit ?? ticket.circuit

  return (
    <div className="space-y-4">
      {/* 1. CABECERA DEL REGISTRO (RECORD HEADER) */}
      <div className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4 min-w-0">
          <div className="h-12 w-12 shrink-0 rounded-xl bg-gradient-to-br from-sky-500 to-blue-600 flex items-center justify-center text-white shadow-lg shadow-sky-500/20" aria-hidden="true">
            <TicketIcon size={24} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[11px] font-mono text-sky-400 font-bold uppercase tracking-wider">
              <span>OPERACIÓN</span>
              <span className="text-slate-600">/</span>
              <span>TICKET DE CLIENTE</span>
            </div>
            <div className="flex flex-wrap items-center gap-3 mt-0.5">
              <h1 className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-white">{ticket.reference}</h1>
              <StatusBadge status={ticket.status} />
              {circuit?.circuit_code && (
                <span className="hidden sm:inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full text-[11px] font-mono bg-slate-900 border border-slate-700 text-slate-300">
                  <span className="text-slate-500">CID:</span> <strong className="text-sky-300">{circuit.circuit_code}</strong>
                </span>
              )}
            </div>
            <h2 className="mt-1.5 text-base sm:text-lg font-semibold text-slate-200 truncate">{ticket.title}</h2>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Can permission="tickets.export">
            <TicketReportDownload ticketId={ticket.id} />
          </Can>
          <Link to="/tickets" className="button-secondary rounded-full">
            Volver a tickets
          </Link>
          <div className="flex max-w-full flex-wrap items-center gap-2" role="group" aria-label="Acciones del ticket">
            <TicketQuickClose key={ticket.id} ticket={ticket} onClosed={closed => { setTicket(closed); setClosedReference(closed.reference) }} />
            <Can anyOf={["tickets.edit", "tickets.close", "tickets.link"]}>
              <Link to={`/tickets/${ticket.id}/edit`} className="button-primary rounded-full">
                <Pencil size={14} className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Editar ticket</span>
              </Link>
            </Can>
          </div>
        </div>
      </div>

      {closedReference === ticket.reference && <FeedbackMessage variant="success">Ticket cerrado correctamente.</FeedbackMessage>}
      {saved && <FeedbackMessage variant="success" className="mb-3">Cambios guardados correctamente.</FeedbackMessage>}

      {/* 2. PANELES DE LECTURA (DESCRIPCIÓN Y RESOLUCIÓN EN 2 COLUMNAS EN ESCRITORIO) */}
      <div className="grid gap-4 md:grid-cols-2">
        <section aria-labelledby="description-heading" className="p-4 sm:p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-2">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs" aria-hidden="true">
              <FileText size={13} />
            </span>
            <h3 id="description-heading" className="text-xs font-bold font-mono text-white uppercase tracking-wider">Descripción del incidente</h3>
          </div>
          <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-200 m-0">{ticket.description}</p>
        </section>

        <section aria-labelledby="ticket-resolution-heading" className="p-4 sm:p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-2">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs" aria-hidden="true">
              <Check size={13} />
            </span>
            <h3 id="ticket-resolution-heading" className="text-xs font-bold font-mono text-white uppercase tracking-wider">Resolución documentada</h3>
          </div>
          <p className={`whitespace-pre-wrap break-words text-sm leading-relaxed m-0 ${ticket.resolution ? 'text-slate-200' : 'text-slate-400 italic'}`}>
            {ticket.resolution || 'Sin resolución documentada todavía. El ticket se encuentra en atención activa.'}
          </p>
        </section>
      </div>

      {/* 3. FICHA TÉCNICA Y TIEMPOS OPERATIVOS (3 COLUMNAS ASIMÉTRICAS) */}
      <div className="grid gap-4 lg:grid-cols-3">
        {/* Clasificación y Entidades (2 cols) */}
        <section aria-labelledby="classification-heading" className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between border-b border-sky-500/15 pb-2.5">
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs" aria-hidden="true">
                <Tag size={13} />
              </span>
              <h3 id="classification-heading" className="text-xs font-bold font-mono text-white uppercase tracking-wider">Cliente y Clasificación Operativa</h3>
            </div>
            <span className="text-[11px] font-mono text-slate-500">Datos históricos inmutables</span>
          </div>

          <dl className="grid gap-x-6 gap-y-3.5 sm:grid-cols-2 text-xs">
            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Cliente</dt>
              <dd className="mt-1 text-sm font-semibold text-white flex items-center gap-2">
                <span>{catalogs.customer.customer_code} — {catalogs.customer.name}</span>
              </dd>
            </div>

            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Circuito</dt>
              <dd className="mt-1 text-sm font-semibold text-white flex items-center gap-2">
                {circuit ? <CircuitLink id={catalogs.circuit?.id === ticket.circuit_id ? ticket.circuit_id : null}>{circuit.circuit_code} — {circuit.description}</CircuitLink> : <span>Sin circuito asociado</span>}
              </dd>
            </div>

            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Nodo</dt>
              <dd className="mt-1 text-sm text-slate-200 font-medium">{catalogs.node?.name ?? 'Sin asignar'}</dd>
            </div>

            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Responsable</dt>
              <dd className="mt-1 text-sm text-slate-200 font-medium font-mono">{catalogs.responsible?.name ?? 'Sin asignar'}</dd>
            </div>

            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Sector</dt>
              <dd className="mt-1 text-sm text-slate-200">{catalogs.sector.name}</dd>
            </div>

            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Departamento</dt>
              <dd className="mt-1 text-sm text-slate-200">{catalogs.department.name}</dd>
            </div>

            <div className="sm:col-span-2">
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Tipo de incidencia</dt>
              <dd className="mt-1 text-sm text-slate-200 font-medium">{catalogs.incidentType.name}</dd>
            </div>
          </dl>
        </section>

        {/* Tiempos Operativos y Auditoría (1 col) */}
        <section aria-labelledby="times-heading" className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-4">
          <div className="flex items-center justify-between border-b border-sky-500/15 pb-2.5">
            <div className="flex items-center gap-2">
              <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs" aria-hidden="true">
                <Clock size={13} />
              </span>
              <h3 id="times-heading" className="text-xs font-bold font-mono text-white uppercase tracking-wider">Tiempos Operativos</h3>
            </div>
          </div>

          <dl className="space-y-3.5 text-xs">
            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Inicio</dt>
              <dd className="mt-1 font-mono text-sm text-slate-200 tabular-nums">{formatDate(ticket.start_at)}</dd>
            </div>

            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Fin</dt>
              <dd className="mt-1 font-mono text-sm text-slate-300 tabular-nums">{formatDate(ticket.end_at)}</dd>
            </div>

            {/* Duración destacada semánticamente */}
            <div className="p-3 rounded-xl bg-[#070d1a] border border-slate-800">
              <dt className="font-mono text-[10px] font-bold text-slate-400 uppercase tracking-wider">Duración</dt>
              <dd className={`mt-1 font-mono text-xl font-bold tracking-tight flex items-center gap-2 ${
                durationText === 'En curso' ? 'text-amber-400' :
                durationText === 'Sin fecha de fin' ? 'text-slate-400' :
                'text-sky-300'
              }`}>
                <span className={`w-2.5 h-2.5 rounded-full ${
                  durationText === 'En curso' ? 'bg-amber-400 animate-pulse' :
                  durationText === 'Sin fecha de fin' ? 'bg-slate-500' :
                  'bg-sky-400'
                }`} />
                <span>{durationText}</span>
              </dd>
              <p className="text-[10px] font-mono text-slate-500 mt-1">
                {durationText === 'En curso'
                  ? 'Ticket abierto sin fecha de fin registrada.'
                  : durationText === 'Sin fecha de fin'
                  ? 'Ticket cerrado sin fecha de fin registrada.'
                  : 'Tiempo total de atención documentado.'}
              </p>
            </div>
          </dl>

          {/* Metadatos de auditoría discretamente integrados */}
          <div className="pt-3 border-t border-slate-800/80 text-[11px] font-mono text-slate-500">
            <dl className="space-y-1">
              <div className="flex justify-between items-baseline">
                <dt className="text-slate-400">Fecha de creación</dt>
                <dd className="text-slate-300 tabular-nums">{formatDate(ticket.created_at)}</dd>
              </div>
              <div className="flex justify-between items-baseline">
                <dt className="text-slate-400">Última actualización</dt>
                <dd className="text-slate-300 tabular-nums">{formatDate(ticket.updated_at)}</dd>
              </div>
            </dl>
          </div>
        </section>
      </div>

      {/* 4. VÍNCULOS, ESCALAMIENTOS Y SEGUIMIENTO */}
      <div className="space-y-4">
        <RelatedInternalTicket id={ticket.internal_ticket_id} />
        <TicketEscalations ticketId={ticket.id} ticketStatus={ticket.status} onTicketStatusChange={() => setRetry(value => value + 1)} />
        <TicketFollowUp key={`${ticket.id}:${ticket.updated_at}`} ticketId={ticket.id} />
      </div>
    </div>
  )
}
