import { ageBucket } from '../lib/ticketAge'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import {
  AlertTriangle,
  Clock,
  ExternalLink,
  Inbox,
  RefreshCw,
  Search,
  ShieldAlert,
} from 'lucide-react'
import { getMyTickets, getMyTicketsSummary } from '../api/myTickets'
import type {
  MyTicketItem,
  MyTicketsSummaryResponse,
  MyTicketView,
  MyTicketScope,
} from '../types/myTickets'
import { PageHeading, type HeadingStat } from '../components/PageHeading'
import { PaginationBar } from '../components/PaginationBar'
import { RequestState } from '../components/RequestState'
import { StatusBadge } from '../components/StatusBadge'
import { formatDate, formatTableDate } from '../lib/format'
import '../styles/myTickets.css'

const LIMIT = 20

export function MyTickets() {
  const [searchParams, setSearchParams] = useSearchParams()

  const params = useParams<{ tab?: string }>()
  const rawParam = params.tab || searchParams.get('view') || searchParams.get('tab')
  const normalizedParam = rawParam === 'verify' ? 'to_verify' : rawParam
  const currentView: MyTicketView =
    normalizedParam && ['assigned', 'participated', 'escalations', 'to_verify'].includes(normalizedParam)
      ? (normalizedParam as MyTicketView)
      : 'assigned'

  const currentScope = (searchParams.get('scope') as MyTicketScope) || 'ALL'
  const currentSearch = searchParams.get('search') || ''
  const currentOffset = Math.max(0, parseInt(searchParams.get('offset') || '0', 10) || 0)

  // Status filters
  const currentOpenOnly = searchParams.get('open_only')
  const currentEscStatus = searchParams.get('escalation_status')

  // Summary state
  const [summary, setSummary] = useState<MyTicketsSummaryResponse | null>(null)
  const [summaryFailed, setSummaryFailed] = useState(false)

  // Tickets list state
  const [items, setItems] = useState<MyTicketItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [manualRefresh, setManualRefresh] = useState(0)

  // Local search input
  const [searchInput, setSearchInput] = useState(currentSearch)

  // Helper to update search params
  const updateParams = useCallback(
    (updates: Record<string, string | null>) => {
      setSearchParams(prev => {
        const next = new URLSearchParams(prev)
        for (const [key, val] of Object.entries(updates)) {
          if (val === null || val === '') {
            next.delete(key)
          } else {
            next.set(key, val)
          }
        }
        return next
      })
    },
    [setSearchParams]
  )

  const changeView = (view: MyTicketView) => {
    updateParams({
      view,
      offset: null,
      search: null,
      open_only: view === 'assigned' ? 'true' : null,
      escalation_status: view === 'escalations' ? 'ACTIVE' : null,
    })
    setSearchInput('')
  }

  // Fetch summary
  const loadSummary = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await getMyTicketsSummary(signal)
      setSummary(data)
      setSummaryFailed(false)
    } catch {
      if (signal?.aborted) return
      // No bloquea la vista; el resumen pasa a «No disponible» en lugar de conservar cifras obsoletas.
      setSummary(null)
      setSummaryFailed(true)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    loadSummary(controller.signal)
    return () => controller.abort()
  }, [loadSummary, manualRefresh])

  // Fetch view data
  const loadViewData = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true)
      setError(null)
      try {
        let openOnlyParam: boolean | null = null
        if (currentOpenOnly === 'true') openOnlyParam = true
        else if (currentOpenOnly === 'false') openOnlyParam = false

        let escStatusParam: 'ACTIVE' | 'FINISHED' | null = null
        if (currentEscStatus === 'ACTIVE' || currentEscStatus === 'FINISHED') {
          escStatusParam = currentEscStatus
        }

        const data = await getMyTickets(
          {
            view: currentView,
            scope: currentScope,
            open_only: openOnlyParam,
            escalation_status: escStatusParam,
            search: currentSearch,
            limit: LIMIT,
            offset: currentOffset,
          },
          signal
        )
        if (signal?.aborted) return
        setItems(data.items)
        setTotal(data.total)
      } catch (err: unknown) {
        if (signal?.aborted) return
        setError(err instanceof Error ? err.message : 'Error al cargar los tickets.')
      } finally {
        if (!signal?.aborted) {
          setLoading(false)
        }
      }
    },
    [currentView, currentScope, currentOpenOnly, currentEscStatus, currentSearch, currentOffset]
  )

  // Primary data loading effect
  useEffect(() => {
    const controller = new AbortController()
    loadViewData(controller.signal)
    return () => controller.abort()
  }, [loadViewData, manualRefresh])

  // 60-second polling for 'to_verify' view
  useEffect(() => {
    if (currentView !== 'to_verify') return

    let timer: ReturnType<typeof setTimeout> | undefined
    let inFlight = false
    let queued = false
    let controller: AbortController | undefined
    let disposed = false

    const visible = () => document.visibilityState !== 'hidden'
    const clearTimer = () => {
      if (timer) clearTimeout(timer)
      timer = undefined
    }

    async function poll() {
      if (disposed || !visible()) return
      clearTimer()
      if (inFlight) {
        queued = true
        return
      }
      inFlight = true
      queued = false
      controller = new AbortController()
      try {
        await Promise.all([
          loadViewData(controller.signal),
          loadSummary(controller.signal),
        ])
      } finally {
        inFlight = false
        if (!disposed && visible()) {
          if (queued) {
            void poll()
          } else {
            timer = setTimeout(() => void poll(), 60_000)
          }
        }
      }
    }

    function onVisibility() {
      clearTimer()
      queued = false
      if (visible()) {
        void poll()
      }
    }

    document.addEventListener('visibilitychange', onVisibility)
    timer = setTimeout(() => void poll(), 60_000)

    return () => {
      disposed = true
      clearTimer()
      controller?.abort()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [currentView, loadViewData, loadSummary])

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    updateParams({ search: searchInput.trim() || null, offset: null })
  }

  const currentPage = Math.floor(currentOffset / LIMIT) + 1
  const totalPages = Math.ceil(total / LIMIT) || 1

  const summaryValue = (value: number | undefined) => ({
    value: summary ? (value ?? null) : null,
    loading: !summary && !summaryFailed,
  })
  const summaryStats: HeadingStat[] = [
    { label: 'Asignados a mí', tone: 'open', ...summaryValue(summary?.assigned_count) },
    { label: 'He participado', tone: 'muted', ...summaryValue(summary?.participated_count) },
    { label: 'Mis escalamientos', tone: 'accent', ...summaryValue(summary?.escalations_count) },
    { label: 'Por verificar', tone: summary && summary.to_verify_count > 0 ? 'open' : 'muted', ...summaryValue(summary?.to_verify_count) },
  ]

  return (
    <div className="my-tickets-container">
      <PageHeading
        title="Mis tickets"
        description="Espacio personal de trabajo en el NOC: tickets asignados, participaciones, escalamientos y verificaciones operativas."
        theme="blue"
        badge="PERSONAL"
        telemetry={
          !loading && !error ? (
            <span className="heading-telemetry">
              <span>Registros:</span>
              <strong className="telemetry-value--blue">{total}</strong>
            </span>
          ) : undefined
        }
        statsLabel="Resumen de mis tickets"
        stats={summaryStats}
        action={
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="button-secondary rounded-full shadow-xs"
              disabled={loading}
              onClick={() => {
                setManualRefresh(r => r + 1)
              }}
              title="Actualizar datos"
            >
              <RefreshCw size={14} aria-hidden="true" className={loading ? 'animate-spin' : ''} />
              Actualizar
            </button>
          </div>
        }
      />

      {/* Tabs & Controls */}
      <div className="my-tickets-controls-bar">
        {/* NOC Tabs */}
        <nav className="noc-tabs" aria-label="Vistas de mis tickets" role="tablist">
          <div className="noc-tabs-options">
            <button
              type="button"
              role="tab"
              aria-selected={currentView === 'assigned'}
              aria-pressed={currentView === 'assigned'}
              className="segment-button"
              onClick={() => changeView('assigned')}
            >
              Asignados a mí
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={currentView === 'participated'}
              aria-pressed={currentView === 'participated'}
              className="segment-button"
              onClick={() => changeView('participated')}
            >
              He participado
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={currentView === 'escalations'}
              aria-pressed={currentView === 'escalations'}
              className="segment-button"
              onClick={() => changeView('escalations')}
            >
              Mis escalamientos
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={currentView === 'to_verify'}
              aria-pressed={currentView === 'to_verify'}
              className="segment-button"
              onClick={() => changeView('to_verify')}
            >
              Por verificar
              {summary && summary.to_verify_count > 0 ? (
                <span className="ml-1.5 px-1.5 py-0.2 rounded-full text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/40">
                  {summary.to_verify_count}
                </span>
              ) : null}
            </button>
          </div>
        </nav>

        {/* Filters and search */}
        <div className="my-tickets-filter-group">
          {/* Scope filter */}
          <div className="inline-flex rounded-full bg-[#070d1a] border border-[#1e2c4a] p-0.5 text-xs font-mono">
            <button
              type="button"
              className={`px-2.5 py-1 rounded-full transition-colors ${
                currentScope === 'ALL'
                  ? 'bg-blue-600 text-white font-bold'
                  : 'text-slate-400 hover:text-white'
              }`}
              onClick={() => updateParams({ scope: null, offset: null })}
            >
              Todos
            </button>
            <button
              type="button"
              className={`px-2.5 py-1 rounded-full transition-colors ${
                currentScope === 'CUSTOMER'
                  ? 'bg-blue-600 text-white font-bold'
                  : 'text-slate-400 hover:text-white'
              }`}
              onClick={() => updateParams({ scope: 'CUSTOMER', offset: null })}
            >
              Clientes
            </button>
            <button
              type="button"
              className={`px-2.5 py-1 rounded-full transition-colors ${
                currentScope === 'INTERNAL'
                  ? 'bg-purple-600 text-white font-bold'
                  : 'text-slate-400 hover:text-white'
              }`}
              onClick={() => updateParams({ scope: 'INTERNAL', offset: null })}
            >
              Internos
            </button>
          </div>

          {/* Tab-specific status toggle */}
          {currentView === 'assigned' && (
            <div className="inline-flex rounded-full bg-[#070d1a] border border-[#1e2c4a] p-0.5 text-xs font-mono">
              <button
                type="button"
                className={`px-2.5 py-1 rounded-full transition-colors ${
                  currentOpenOnly !== 'false'
                    ? 'bg-slate-700 text-white font-bold'
                    : 'text-slate-400 hover:text-white'
                }`}
                onClick={() => updateParams({ open_only: 'true', offset: null })}
              >
                Abiertos
              </button>
              <button
                type="button"
                className={`px-2.5 py-1 rounded-full transition-colors ${
                  currentOpenOnly === 'false'
                    ? 'bg-slate-700 text-white font-bold'
                    : 'text-slate-400 hover:text-white'
                }`}
                onClick={() => updateParams({ open_only: 'false', offset: null })}
              >
                Cerrados
              </button>
            </div>
          )}

          {currentView === 'participated' && (
            <div className="inline-flex rounded-full bg-[#070d1a] border border-[#1e2c4a] p-0.5 text-xs font-mono">
              <button
                type="button"
                className={`px-2.5 py-1 rounded-full transition-colors ${
                  currentOpenOnly === null
                    ? 'bg-slate-700 text-white font-bold'
                    : 'text-slate-400 hover:text-white'
                }`}
                onClick={() => updateParams({ open_only: null, offset: null })}
              >
                Todos
              </button>
              <button
                type="button"
                className={`px-2.5 py-1 rounded-full transition-colors ${
                  currentOpenOnly === 'true'
                    ? 'bg-slate-700 text-white font-bold'
                    : 'text-slate-400 hover:text-white'
                }`}
                onClick={() => updateParams({ open_only: 'true', offset: null })}
              >
                Abiertos
              </button>
              <button
                type="button"
                className={`px-2.5 py-1 rounded-full transition-colors ${
                  currentOpenOnly === 'false'
                    ? 'bg-slate-700 text-white font-bold'
                    : 'text-slate-400 hover:text-white'
                }`}
                onClick={() => updateParams({ open_only: 'false', offset: null })}
              >
                Cerrados
              </button>
            </div>
          )}

          {currentView === 'escalations' && (
            <div className="inline-flex rounded-full bg-[#070d1a] border border-[#1e2c4a] p-0.5 text-xs font-mono">
              <button
                type="button"
                className={`px-2.5 py-1 rounded-full transition-colors ${
                  currentEscStatus === 'ACTIVE'
                    ? 'bg-amber-600 text-white font-bold'
                    : 'text-slate-400 hover:text-white'
                }`}
                onClick={() => updateParams({ escalation_status: 'ACTIVE', offset: null })}
              >
                Activos
              </button>
              <button
                type="button"
                className={`px-2.5 py-1 rounded-full transition-colors ${
                  currentEscStatus === 'FINISHED'
                    ? 'bg-slate-700 text-white font-bold'
                    : 'text-slate-400 hover:text-white'
                }`}
                onClick={() => updateParams({ escalation_status: 'FINISHED', offset: null })}
              >
                Finalizados
              </button>
              <button
                type="button"
                className={`px-2.5 py-1 rounded-full transition-colors ${
                  currentEscStatus === null
                    ? 'bg-slate-700 text-white font-bold'
                    : 'text-slate-400 hover:text-white'
                }`}
                onClick={() => updateParams({ escalation_status: null, offset: null })}
              >
                Todos
              </button>
            </div>
          )}

          {/* Search box */}
          <form onSubmit={handleSearchSubmit} className="relative flex items-center">
            <input
              type="text"
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              placeholder="Buscar tickets..."
              className="w-44 sm:w-56 pl-8 pr-3 py-1 text-xs rounded-full bg-[#070d1a] border border-[#1e2c4a] text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
            <Search
              size={13}
              className="absolute left-2.5 text-slate-400 pointer-events-none"
              aria-hidden="true"
            />
          </form>
        </div>
      </div>

      {/* Main Content Area */}
      {loading && !items.length ? (
        <RequestState loading compact loadingText="Cargando tickets personales..." />
      ) : error ? (
        <div className="panel p-6 text-center text-red-400 border border-red-900/50">
          <p className="font-medium">{error}</p>
          <button
            type="button"
            className="button-secondary mt-3 rounded-full"
            onClick={() => setManualRefresh(r => r + 1)}
          >
            Reintentar
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="panel p-12 text-center text-slate-400 border border-[#1e2c4a]">
          <Inbox size={40} className="mx-auto mb-3 text-slate-600" aria-hidden="true" />
          <h2 className="text-base font-semibold text-slate-200">
            {currentView === 'assigned' && 'No tienes tickets asignados actualmente.'}
            {currentView === 'participated' && 'No has participado en tickets recientemente.'}
            {currentView === 'escalations' && 'No tienes escalamientos asignados actualmente.'}
            {currentView === 'to_verify' && 'No hay tickets pendientes de verificación por escalamiento.'}
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            {currentSearch
              ? 'Prueba modificando los criterios de búsqueda o filtros seleccionados.'
              : currentView === 'escalations'
              ? 'Los escalamientos donde figures como responsable asignado aparecerán aquí.'
              : currentView === 'to_verify'
              ? 'Los tickets con recomendaciones de escalamiento dirigidas a tu puesto aparecerán aquí.'
              : 'Las incidencias asignadas o en las que participes aparecerán aquí en tiempo real.'}
          </p>
        </div>
      ) : (
        <div className="panel table-surface overflow-hidden">
          <div className="overflow-x-auto">
            <table className="operation-table w-full min-w-[980px]">
              <caption className="table-title">
                {currentView === 'assigned' && 'Tickets asignados a mí'}
                {currentView === 'participated' && 'Tickets con mi participación operativa'}
                {currentView === 'escalations' && 'Escalamientos asignados a mí'}
                {currentView === 'to_verify' && 'Tickets con recomendación de escalamiento a verificar'}
              </caption>
              <thead>
                <tr>
                  {currentView === 'assigned' && (
                    <>
                      <th scope="col">Ticket</th>
                      <th scope="col">Tipo</th>
                      <th scope="col">Estado</th>
                      <th scope="col">Cliente / Contexto</th>
                      <th scope="col">Sector / Nodo</th>
                      <th scope="col">Apertura</th>
                      <th scope="col">Alerta</th>
                      <th scope="col" className="text-center">Acción</th>
                    </>
                  )}
                  {currentView === 'participated' && (
                    <>
                      <th scope="col">Ticket</th>
                      <th scope="col">Tipo</th>
                      <th scope="col">Estado</th>
                      <th scope="col">Responsable actual</th>
                      <th scope="col">Cliente / Contexto</th>
                      <th scope="col">Sector / Nodo</th>
                      <th scope="col">Apertura</th>
                      <th scope="col" className="text-center">Acción</th>
                    </>
                  )}
                  {currentView === 'escalations' && (
                    <>
                      <th scope="col">Ticket</th>
                      <th scope="col">Tipo</th>
                      <th scope="col">Solicitante</th>
                      <th scope="col">Puesto destino</th>
                      <th scope="col">Motivo escalamiento</th>
                      <th scope="col">Estado esc.</th>
                      <th scope="col">Responsable del ticket</th>
                      <th scope="col">Fecha escalamiento</th>
                      <th scope="col" className="text-center">Acción</th>
                    </>
                  )}
                  {currentView === 'to_verify' && (
                    <>
                      <th scope="col">Ticket</th>
                      <th scope="col">Tipo</th>
                      <th scope="col">Puesto objetivo</th>
                      <th scope="col">Responsable actual</th>
                      <th scope="col">Transcurrido</th>
                      <th scope="col">Excedido</th>
                      <th scope="col">Alerta operativa</th>
                      <th scope="col" className="text-center">Acción</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {items.map(ticket => {
                  const isCustomer = ticket.ticket_type === 'CUSTOMER'
                  const detailUrl = isCustomer
                    ? `/tickets/${ticket.id}`
                    : `/internal-tickets/${ticket.id}`
                  const isOpen = ticket.status === 'OPEN'

                  return (
                    <tr
                      key={`${ticket.ticket_type}-${ticket.id}-${ticket.escalation_id ?? ''}`}
                      className={isOpen ? 'ticket-state-open' : 'ticket-state-closed'}
                      data-age={isOpen ? ageBucket(ticket.start_at) ?? undefined : undefined}
                    >
                      {/* Referencia / Título */}
                      <th scope="row" className="max-w-64 text-primary whitespace-nowrap">
                        <Link
                          to={detailUrl}
                          className="record-code hover:underline underline-offset-4"
                        >
                          {ticket.reference}
                        </Link>
                        <span
                          className="mt-0.5 block max-w-56 truncate text-xs font-normal text-slate-400 font-sans"
                          title={ticket.title}
                        >
                          {ticket.title}
                        </span>
                      </th>

                      {/* Tipo de ticket */}
                      <td className="w-24 whitespace-nowrap">
                        <span
                          className={`my-tickets-type-badge ${
                            isCustomer
                              ? 'my-tickets-type-badge--customer'
                              : 'my-tickets-type-badge--internal'
                          }`}
                        >
                          {isCustomer ? 'Cliente' : 'Interno'}
                        </span>
                      </td>

                      {/* Asignados a mí view */}
                      {currentView === 'assigned' && (
                        <>
                          <td className="w-24 whitespace-nowrap">
                            <StatusBadge status={ticket.status} />
                          </td>
                          <td className="max-w-44 text-xs text-slate-300">
                            {isCustomer && ticket.customer_name ? (
                              <>
                                <span className="customer-code-badge font-mono text-[11px]">
                                  {ticket.customer_code}
                                </span>
                                <span className="block truncate text-slate-200 mt-0.5">
                                  {ticket.customer_name}
                                </span>
                              </>
                            ) : (
                              <span className="text-purple-300 font-mono">
                                {ticket.department_name || 'NOC'}
                              </span>
                            )}
                          </td>
                          <td className="max-w-32 text-xs text-slate-400">
                            <span className="block truncate">{ticket.sector_name || '—'}</span>
                            <span className="block truncate text-[11px] text-slate-500">
                              {ticket.node_name || ''}
                            </span>
                          </td>
                          <td className="w-28 whitespace-nowrap text-xs font-mono tabular-nums text-slate-400">
                            <time dateTime={ticket.start_at} title={formatDate(ticket.start_at)}>
                              {formatTableDate(ticket.start_at)}
                            </time>
                          </td>
                          <td className="w-40 whitespace-nowrap">
                            {ticket.has_recommendation ? (
                              <span className="my-tickets-rec-badge">
                                <AlertTriangle size={12} aria-hidden="true" />
                                Recom. activa
                              </span>
                            ) : (
                              <span className="text-slate-600 text-xs font-mono">—</span>
                            )}
                          </td>
                        </>
                      )}

                      {/* He participado view */}
                      {currentView === 'participated' && (
                        <>
                          <td className="w-24 whitespace-nowrap">
                            <StatusBadge status={ticket.status} />
                          </td>
                          <td className="max-w-36 text-xs">
                            <span className={`font-mono font-medium block truncate ${ticket.responsible_name ? 'text-slate-200' : 'italic text-slate-400'}`}>
                              {ticket.responsible_name || 'Sin asignar'}
                            </span>
                            <span className="text-[10px] text-slate-500 block">
                              Responsable actual
                            </span>
                          </td>
                          <td className="max-w-44 text-xs text-slate-300">
                            {isCustomer && ticket.customer_name ? (
                              <span className="block truncate">{ticket.customer_name}</span>
                            ) : (
                              <span className="text-purple-300">{ticket.department_name || 'NOC'}</span>
                            )}
                          </td>
                          <td className="max-w-32 text-xs text-slate-400">
                            <span className="block truncate">{ticket.sector_name || '—'}</span>
                          </td>
                          <td className="w-28 whitespace-nowrap text-xs font-mono tabular-nums text-slate-400">
                            <time dateTime={ticket.start_at} title={formatDate(ticket.start_at)}>
                              {formatTableDate(ticket.start_at)}
                            </time>
                          </td>
                        </>
                      )}

                      {/* Mis escalamientos view */}
                      {currentView === 'escalations' && (
                        <>
                          <td className="max-w-28 text-xs text-slate-400">
                            <span className="block truncate">{ticket.escalation_requester_name || 'Sin solicitante'}</span>
                          </td>
                          <td className="max-w-36 text-xs text-amber-300 font-mono font-medium">
                            {ticket.escalation_position_name || 'Puesto asignado'}
                          </td>
                          <td className="max-w-44 text-xs text-slate-300">
                            <span className="block truncate" title={ticket.escalation_reason || ''}>
                              {ticket.escalation_reason || '—'}
                            </span>
                          </td>
                          <td className="w-24 whitespace-nowrap">
                            <span
                              className={`px-2 py-0.5 text-[11px] font-mono font-bold rounded-full border ${
                                ticket.escalation_status === 'ACTIVE'
                                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                                  : 'bg-slate-700/30 text-slate-400 border-slate-600/40'
                              }`}
                            >
                              {ticket.escalation_status === 'ACTIVE' ? 'Activo' : 'Finalizado'}
                            </span>
                          </td>
                          <td className="max-w-36 text-xs">
                            <span className="font-mono text-slate-200 block truncate">
                              {ticket.responsible_name || 'Sin asignar'}
                            </span>
                            <span className="text-[10px] text-slate-500 block">
                              Responsable del ticket
                            </span>
                          </td>
                          <td className="w-28 whitespace-nowrap text-xs font-mono tabular-nums text-slate-400">
                            {ticket.escalation_started_at ? (
                              <time
                                dateTime={ticket.escalation_started_at}
                                title={formatDate(ticket.escalation_started_at)}
                              >
                                {formatTableDate(ticket.escalation_started_at)}
                              </time>
                            ) : (
                              '—'
                            )}
                          </td>
                        </>
                      )}

                      {/* Por verificar view */}
                      {currentView === 'to_verify' && (
                        <>
                          <td className="max-w-36 text-xs font-mono font-bold text-amber-300">
                            {ticket.recommendation_target_position_name || 'Mi puesto'}
                          </td>
                          <td className="max-w-36 text-xs">
                            <span className="font-mono text-slate-200 block truncate">
                              {ticket.responsible_name || 'Sin asignar'}
                            </span>
                            <span className="text-[10px] text-slate-500 block">
                              Responsable actual
                            </span>
                          </td>
                          <td className="w-28 whitespace-nowrap text-xs font-mono tabular-nums text-slate-300">
                            <span className="flex items-center gap-1">
                              <Clock size={12} className="text-slate-400" aria-hidden="true" />
                              {ticket.recommendation_elapsed_minutes ?? 0} min
                            </span>
                          </td>
                          <td className="w-28 whitespace-nowrap">
                            <span className="my-tickets-overdue-badge">
                              +{ticket.recommendation_overdue_minutes ?? 0} min
                            </span>
                          </td>
                          <td className="max-w-44 text-xs text-amber-300 font-mono">
                            <span className="flex items-center gap-1.5 font-medium">
                              <ShieldAlert size={13} className="text-amber-400 shrink-0" aria-hidden="true" />
                              Escalamiento requerido
                            </span>
                          </td>
                        </>
                      )}

                      {/* Acción */}
                      <td className="w-20 text-center whitespace-nowrap">
                        <Link
                          to={detailUrl}
                          className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-mono font-medium text-blue-400 hover:text-white hover:bg-blue-600/30 border border-blue-900/60 transition-colors shadow-xs"
                        >
                          <span>{currentView === 'to_verify' ? 'Atender' : 'Ver'}</span>
                          <ExternalLink size={11} aria-hidden="true" />
                        </Link>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {total > LIMIT && (
            <div className="p-3 border-t border-[#1e2c4a]">
              <PaginationBar
                page={currentPage}
                info={`Mostrando ${currentOffset + 1}–${Math.min(
                  currentOffset + LIMIT,
                  total
                )} de ${total}`}
                previousDisabled={currentOffset === 0}
                nextDisabled={currentOffset + LIMIT >= total}
                onPrevious={() =>
                  updateParams({
                    offset: String(Math.max(0, currentOffset - LIMIT)),
                  })
                }
                onNext={() =>
                  updateParams({
                    offset: String(currentOffset + LIMIT),
                  })
                }
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
