import { Can, usePermissions } from '../auth/permissions'
import { useState } from 'react'
import { Link } from 'react-router'
import { ArrowRight, RefreshCw, Tickets, Clock3, CircleCheck, Plus } from 'lucide-react'
import { useTickets } from '../hooks/useTickets'
import { useTicketStats } from '../hooks/useTicketStats'
import { useOpenOverview } from '../hooks/useOpenOverview'
import { defaultHiddenColumns } from '../lib/ticketColumns'
import { ageBuckets, ticketsUrl } from '../lib/ticketAge'
import type { TicketQuery } from '../types/ticket'
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

const oldestOpen: TicketQuery = { status: 'OPEN', order: 'start_at_asc', limit: 5 }

function DashboardContent() {
  const [refresh, setRefresh] = useState(0)
  // El backend aplica filtro, orden y límite: no se carga ni se ordena nada en React.
  const { loading, tickets, error } = useTickets(0, refresh, oldestOpen)
  const { loading: overviewLoading, overview, error: overviewError } = useOpenOverview(refresh)
  const maxBucket = overview ? Math.max(...Object.values(overview.buckets)) : 0
  const maxSector = overview ? Math.max(1, ...overview.sectors.map((sector) => sector.count)) : 1
  const { loading: statsLoading, stats, error: statsError } = useTicketStats(refresh)

  return (
    <>
      <PageHeading
        title="Dashboard"
        description="Una vista global de tus incidencias y del trabajo abierto pendiente."
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
              <span className="text-emerald-200/90 font-medium">Ya no cuentan en el flujo</span>
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

      <section className="mt-6" aria-labelledby="age-heading" aria-busy={overviewLoading}>
        <SectionHeading number="02" title="Abiertos por antigüedad" id="age-heading" />
        {overviewError ? (
          <RequestState error={overviewError} errorTitle="Error al cargar la antigüedad" retryText="Reintentar" onRetry={() => setRefresh(refresh + 1)} />
        ) : (
          <>
            <div className="age-grid">
              {ageBuckets.map(({ key, label }) => {
                const count = overview?.buckets[key]
                return (
                  <Link key={key} className="age-card" data-age={key} to={ticketsUrl({ status: 'OPEN', age_bucket: key })}>
                    <span className="age-card-label">{label}</span>
                    <span className="age-card-value font-mono">{count ?? '—'}</span>
                    <span className="age-card-bar" aria-hidden="true"><span style={{ width: `${count && maxBucket ? (count / maxBucket) * 100 : 0}%` }} /></span>
                    <span className="age-card-caption">{count === undefined ? 'Cargando…' : `${count === 1 ? 'ticket abierto' : 'tickets abiertos'}${overview!.open ? ` · ${Math.round((count / overview!.open) * 100)} % de los abiertos` : ''}`}</span>
                  </Link>
                )
              })}
              <Link className="age-card age-card--unassigned" to={ticketsUrl({ status: 'OPEN', unassigned: 'true' })}>
                <span className="age-card-label">Sin responsable</span>
                <span className="age-card-value font-mono">{overview?.unassigned ?? '—'}</span>
                <span className="age-card-caption">Abiertos sin asignar, de cualquier antigüedad. No se suma a los tramos.</span>
              </Link>
            </div>
            {overview && overview.future_start > 0 && (
              <p className="mt-2 text-xs workspace-caption">
                {overview.future_start} {overview.future_start === 1 ? 'ticket abierto tiene' : 'tickets abiertos tienen'} fecha de inicio futura y no se clasifican por antigüedad.
              </p>
            )}
          </>
        )}
      </section>

      <section className="mt-6" aria-labelledby="oldest-heading">
        <SectionHeading
          number="03"
          title="Abiertos más antiguos"
          id="oldest-heading"
          action={
            <Link
              to={ticketsUrl({ status: 'OPEN' })}
              className="button-secondary rounded-full inline-flex items-center gap-1.5 text-xs py-1 px-3 shadow-xs"
            >
              <span>Ver todos los abiertos</span>
              <ArrowRight size={13} aria-hidden="true" />
            </Link>
          }
        />
        {loading || error || tickets.length === 0 ? (
          <RequestState
            loading={loading}
            error={error}
            empty={tickets.length === 0}
            emptyTitle="Sin tickets abiertos" emptyDescription="No hay tickets abiertos en este momento."
            onRetry={() => setRefresh(refresh + 1)}
          />
        ) : (
          <TicketTable tickets={tickets} hidden={defaultHiddenColumns} />
        )}
      </section>

      <section className="mt-6" aria-labelledby="sectors-heading">
        <SectionHeading number="04" title="Abiertos por sector" id="sectors-heading" />
        {overviewError || overviewLoading || !overview || overview.sectors.length === 0 ? (
          <RequestState loading={overviewLoading} error={overviewError} errorTitle="Error al cargar los sectores" empty={!overviewError && !overviewLoading} emptyTitle="Sin tickets abiertos" emptyDescription="No hay tickets abiertos en este momento." onRetry={() => setRefresh(refresh + 1)} />
        ) : (
          <div className="panel sector-panel">
            <ul className="sector-list">
              {overview.sectors.map(({ id, name, count }) => (
                <li key={id} className="sector-row">
                  <Link className="sector-name" to={ticketsUrl({ status: 'OPEN', sector_id: String(id) })}>{name}</Link>
                  <span className="sector-bar" aria-hidden="true"><span style={{ width: `${(count / maxSector) * 100}%` }} /></span>
                  <span className="sector-count font-mono">{count}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-xs workspace-caption">Un sector con varios abiertos a la vez puede indicar un evento común.</p>
          </div>
        )}
      </section>

      <p className="mt-6 text-xs workspace-caption">
        El detalle histórico está en{' '}
        <Can anyOf={['tickets', 'internal_tickets', 'changes'].flatMap((key) => [`reports.${key}.view`, `reports.${key}.export`])} fallback="Reportería">
          <Link className="underline underline-offset-2 hover:text-white" to="/reports">Reportería</Link>
        </Can>
        .
      </p>
    </>
  )
}
