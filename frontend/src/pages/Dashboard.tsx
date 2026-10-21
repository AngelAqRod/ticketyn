import { Can, usePermissions } from '../auth/permissions'
import { useState } from 'react'
import { Link } from 'react-router'
import { ArrowRight, RefreshCw, Tickets, Clock3, CircleCheck, Plus } from 'lucide-react'
import { useTickets } from '../hooks/useTickets'
import { useTicketStats } from '../hooks/useTicketStats'
import { PageHeading } from '../components/PageHeading'
import { RequestState } from '../components/RequestState'
import { SectionHeading } from '../components/SectionHeading'
import { TicketTable } from '../components/TicketTable'

export function Dashboard() {
  const { can } = usePermissions()
  if (!can('tickets.view')) {
    return (
      <>
        <PageHeading title="Dashboard" description="Resumen operativo" />
        <div className="panel noc-panel p-5 rounded-2xl bg-[#0b1426] border border-cyan-500/20 shadow-xl text-slate-300">
          No tienes permiso para consultar los datos de tickets.
        </div>
      </>
    )
  }
  return <DashboardContent />
}

function DashboardContent() {
  const [refresh, setRefresh] = useState(0)
  const { loading, tickets, error } = useTickets(0, refresh)
  const { loading: statsLoading, stats, error: statsError } = useTicketStats(refresh)

  return (
    <>
      <PageHeading
        title="Dashboard"
        description="Una vista global de tus incidencias y los tickets más recientes."
        telemetry={
          !statsLoading && !statsError && stats ? (
            <span className="heading-telemetry">
              <span>Activos:</span>
              <strong className="telemetry-value--cyan">{stats.open}</strong>
            </span>
          ) : undefined
        }
        action={
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="button-secondary rounded-full shadow-xs"
              disabled={loading || statsLoading}
              onClick={() => setRefresh(refresh + 1)}
            >
              <RefreshCw size={14} aria-hidden="true" />
              Actualizar
            </button>
            <Can permission="tickets.create">
              <Link
                className="button-primary button-primary--cyan rounded-full shadow-sm"
                to="/tickets/new"
              >
                <Plus size={15} aria-hidden="true" />
                Nuevo ticket
              </Link>
            </Can>
          </div>
        }
      />

      <section aria-label="Estadísticas globales de tickets" aria-busy={statsLoading}>
        <SectionHeading number="01" title="Panorama de incidencias" />

        <dl className="dashboard-stats-grid">
          {/* Card 1: Tickets totales */}
          <div className="stat-card stat-card--total">
            <div className="stat-card-header">
              <dt className="stat-card-label">Tickets totales</dt>
              <span className="icon-surface icon-surface--cyan" aria-hidden="true">
                <Tickets size={18} />
              </span>
            </div>
            <dd className="stat-card-value font-mono">
              {statsLoading || statsError ? '—' : (stats?.total ?? 0)}
            </dd>
            <p className="stat-card-caption">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_6px_#22d3ee]" aria-hidden="true" />
              <span>Población total registrada en NOC</span>
            </p>
          </div>

          {/* Card 2: Tickets abiertos */}
          <div className="stat-card stat-card--open">
            <div className="stat-card-header">
              <dt className="stat-card-label">Tickets abiertos</dt>
              <span className="icon-surface icon-surface--warning" aria-hidden="true">
                <Clock3 size={18} />
              </span>
            </div>
            <dd className="stat-card-value font-mono text-amber-400">
              {statsLoading || statsError ? '—' : (stats?.open ?? 0)}
            </dd>
            <p className="stat-card-caption">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 shadow-[0_0_6px_#fbbf24] animate-pulse" aria-hidden="true" />
              <span className="text-amber-200/90 font-medium">En atención activa inmediata</span>
            </p>
          </div>

          {/* Card 3: Tickets cerrados */}
          <div className="stat-card stat-card--closed">
            <div className="stat-card-header">
              <dt className="stat-card-label">Tickets cerrados</dt>
              <span className="icon-surface icon-surface--success" aria-hidden="true">
                <CircleCheck size={18} />
              </span>
            </div>
            <dd className="stat-card-value font-mono text-emerald-400">
              {statsLoading || statsError ? '—' : (stats?.closed ?? 0)}
            </dd>
            <p className="stat-card-caption">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_#34d399]" aria-hidden="true" />
              <span className="text-emerald-200/90 font-medium">Incidencias resueltas con éxito</span>
            </p>
          </div>
        </dl>

        {statsLoading && (
          <RequestState
            loading
            compact
            loadingText="Cargando estadísticas..."
            className="mt-2 workspace-caption"
          />
        )}
        {statsError && (
          <RequestState
            error={statsError}
            errorTitle="Error al cargar estadísticas"
            retryText="Reintentar estadísticas"
            onRetry={() => setRefresh(refresh + 1)}
            className="mt-4"
          />
        )}
      </section>

      <section className="mt-6" aria-labelledby="recent-heading">
        <SectionHeading
          number="02"
          title="Tickets recientes"
          id="recent-heading"
          action={
            <Link
              to="/tickets"
              className="button-secondary rounded-full inline-flex items-center gap-1.5 text-xs py-1 px-3 shadow-xs"
            >
              <span>Ver todos los tickets</span>
              <ArrowRight size={13} aria-hidden="true" />
            </Link>
          }
        />
        {loading || error || tickets.length === 0 ? (
          <RequestState
            loading={loading}
            error={error}
            empty={tickets.length === 0}
            onRetry={() => setRefresh(refresh + 1)}
          />
        ) : (
          <TicketTable tickets={tickets.slice(0, 5)} />
        )}
      </section>
    </>
  )
}
