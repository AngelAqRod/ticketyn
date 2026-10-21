import { operationalChoice } from '../lib/responsibles'
import { Can, usePermissions } from '../auth/permissions'
import { RelatedChanges } from '../components/RelatedChanges'
import { InternalTicketReportDownload } from '../components/InternalTicketReportDownload'
import { downloadInternalTickets } from '../api/ticketExports'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import {
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  FileSpreadsheet,
  FileText,
  Filter,
  Network,
  Plus,
  RefreshCw,
  Server,
  Tag,
  Users,
} from 'lucide-react'
import { getJson, patchJson, postJson } from '../api/client'
import {
  listSectors,
  listNodes,
  listDepartments,
  listResponsibles,
  listInternalIncidentTypes,
  listProviders,
} from '../api'
import type { NamedCatalog } from '../types/catalog'
import type { InternalTicket } from '../types/internalTicket'
import type { Ticket } from '../types/ticket'
import { PaginationBar } from '../components/PaginationBar'
import { PageHeading } from '../components/PageHeading'
import { FilterHeading } from '../components/FilterHeading'
import { FilterChips } from '../components/FilterChips'
import { FormField } from '../components/FormField'
import { SearchableSelect } from '../components/SearchableSelect'
import { PeriodShortcuts } from '../components/PeriodShortcuts'
import { RequestState } from '../components/RequestState'
import { FeedbackMessage } from '../components/FeedbackMessage'
import { StatusBadge } from '../components/StatusBadge'
import { TicketFollowUp } from '../components/TicketFollowUp'
import { TicketEscalations } from '../components/TicketEscalations'
import { useUrlFilters } from '../hooks/useUrlFilters'
import { reportPeriod } from '../lib/reportPeriod'
import { localDateTimeValue, localDateTimeToIso } from '../lib/datetime'
import { formatDate, formatDuration } from '../lib/format'

const root = '/api/internal-tickets'
const relationFields = [
  ['sector_id', 'Sector', true],
  ['node_id', 'Nodo', false],
  ['department_id', 'Departamento', true],
  ['responsible_id', 'Responsable', false],
  ['incident_type_id', 'Tipo de incidencia interna', true],
  ['provider_id', 'Atribuible a proveedor', false],
] as const

type Catalogs = Record<typeof relationFields[number][0], NamedCatalog[]>

function useCatalogs() {
  const [data, setData] = useState<Catalogs | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setError(null)
    Promise.all([
      listSectors(controller.signal, true),
      listNodes(controller.signal, true),
      listDepartments(controller.signal, true),
      listResponsibles(controller.signal, true),
      listInternalIncidentTypes(controller.signal, true),
      listProviders(controller.signal, true),
    ])
      .then((rows) => {
        if (!controller.signal.aborted) {
          setData(
            Object.fromEntries(
              relationFields.map(([key], i) => [key, rows[i]])
            ) as Catalogs
          )
        }
      })
      .catch((f) => {
        if (!controller.signal.aborted) {
          setError(
            f instanceof Error
              ? f.message
              : 'No se pudieron cargar los catálogos.'
          )
        }
      })
    return () => controller.abort()
  }, [retry])

  return { data, error, retry: () => setRetry(retry + 1) }
}

function useInternal(id: string | undefined) {
  const [item, setItem] = useState<InternalTicket | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    const c = new AbortController()
    setItem(null)
    setError(null)
    getJson<InternalTicket>(`${root}/${id}`, c.signal)
      .then((x) => {
        if (!c.signal.aborted) setItem(x)
      })
      .catch((f) => {
        if (!c.signal.aborted) {
          setError(f instanceof Error ? f.message : 'No se pudo cargar.')
        }
      })
    return () => c.abort()
  }, [id, retry])

  return { item, error, retry: () => setRetry(retry + 1) }
}

/** VISTA 1: LISTADO DE TICKETS INTERNOS */
export function InternalTickets() {
  const keys = [
    'search',
    'status',
    'sector_id',
    'node_id',
    'department_id',
    'responsible_id',
    'incident_type_id',
    'provider_id',
    'period',
    'from',
    'to',
  ]
  const { params, change, clear } = useUrlFilters(keys)
  const catalogs = useCatalogs()
  const [rows, setRows] = useState<InternalTicket[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  const [search, setSearch] = useState(params.get('search') ?? '')

  // Colapso persistente del panel de filtros
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return sessionStorage.getItem('internal_tickets_filters_collapsed') === 'true'
    } catch {
      return false
    }
  })

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev
      try {
        sessionStorage.setItem('internal_tickets_filters_collapsed', String(next))
      } catch {
        // Ignorar fallas de sessionStorage
      }
      return next
    })
  }

  useEffect(() => setSearch(params.get('search') ?? ''), [params])
  const offset = Math.max(0, Number(params.get('offset')) || 0)
  let query = new URLSearchParams({ limit: '50', offset: String(offset) })
  let filterError: string | null = null

  try {
    const period = reportPeriod(
      new URLSearchParams({
        period: params.get('period') ?? 'all',
        from: params.get('from') ?? '',
        to: params.get('to') ?? '',
      })
    ).query
    if (period.from) query.set('from', period.from)
    if (period.to) query.set('to', period.to)
    for (const key of keys.slice(0, 8)) {
      if (params.get(key)) query.set(key, params.get(key)!)
    }
    if (params.get('provider_id') === 'none') {
      query.delete('provider_id')
      query.set('without_provider', 'true')
    }
  } catch (f) {
    filterError = f instanceof Error ? f.message : 'Rango inválido'
  }

  const queryKey = query.toString()
  const exportingRef = useRef(false)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  async function exportTickets(format: 'pdf' | 'xlsx') {
    if (exportingRef.current || filterError) return
    exportingRef.current = true
    setExporting(true)
    setExportError(null)
    try {
      await downloadInternalTickets(format, new URLSearchParams(queryKey))
    } catch (f) {
      setExportError(
        f instanceof Error ? f.message : 'No se pudo exportar el listado.'
      )
    } finally {
      exportingRef.current = false
      setExporting(false)
    }
  }

  useEffect(() => {
    const c = new AbortController()
    setLoading(true)
    setError(null)
    if (filterError) {
      setLoading(false)
      setError(filterError)
      return
    }
    getJson<InternalTicket[]>(`${root}?${queryKey}`, c.signal)
      .then((x) => {
        if (!c.signal.aborted) {
          setRows(x)
          setLoading(false)
        }
      })
      .catch((f) => {
        if (!c.signal.aborted) {
          setError(f instanceof Error ? f.message : 'No se pudo cargar.')
          setLoading(false)
        }
      })
    return () => c.abort()
  }, [queryKey, refresh, filterError])

  // Cálculo de filtros activos para los chips del panel colapsado
  const activeChips: { label: string; value: string; onRemove: () => void }[] = []
  if (params.get('search')) {
    activeChips.push({
      label: 'Búsqueda',
      value: `"${params.get('search')}"`,
      onRemove: () => {
        setSearch('')
        change({ search: '' })
      },
    })
  }
  if (params.get('status')) {
    activeChips.push({
      label: 'Estado',
      value: params.get('status') === 'OPEN' ? 'Abierto' : 'Cerrado',
      onRemove: () => change({ status: '' }),
    })
  }
  if (params.get('period') && params.get('period') !== 'all') {
    const p = params.get('period')
    const pNames: Record<string, string> = {
      today: 'Hoy',
      yesterday: 'Ayer',
      current_month: 'Mes actual',
      previous_month: 'Mes anterior',
      custom: `${params.get('from') || '—'} a ${params.get('to') || '—'}`,
    }
    activeChips.push({
      label: 'Período',
      value: pNames[p!] || p!,
      onRemove: () => change({ period: 'all', from: '', to: '' }),
    })
  }
  for (const [key, label] of relationFields) {
    const val = params.get(key)
    if (val) {
      const match = val === 'none' ? 'Ninguno' : catalogs.data?.[key]?.find((item) => String(item.id) === val)?.name ?? val
      activeChips.push({
        label,
        value: match,
        onRemove: () => change({ [key]: '' }),
      })
    }
  }

  const activeCount = activeChips.length

  return (
    <div className="space-y-5">
      {/* RECORD HEADER: TICKETS INTERNOS HOMOGENEIZADO */}
      <PageHeading
        title="Tickets internos"
        description="Incidencias de infraestructura y operación del NOC, sin cliente ni circuito."
        telemetry={
          !loading && !error && (
            <span className="heading-telemetry">
              <span>Total:</span>
              <strong className="telemetry-value--purple">{rows.length}</strong>
            </span>
          )
        }
        action={
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="button-secondary rounded-full shadow-xs"
              onClick={() => setRefresh(refresh + 1)}
              disabled={loading}
            >
              <RefreshCw size={14} aria-hidden="true" />
              Actualizar
            </button>
            <Can permission="internal_tickets.export">
              <button
                type="button"
                className="button-secondary rounded-full shadow-xs"
                disabled={exporting || Boolean(filterError)}
                onClick={() => void exportTickets('pdf')}
              >
                <FileText size={14} aria-hidden="true" />
                Exportar PDF
              </button>
            </Can>
            <Can permission="internal_tickets.export">
              <button
                type="button"
                className="button-secondary rounded-full shadow-xs"
                disabled={exporting || Boolean(filterError)}
                onClick={() => void exportTickets('xlsx')}
              >
                <FileSpreadsheet size={14} aria-hidden="true" />
                Exportar Excel
              </button>
            </Can>
            <Can permission="internal_tickets.create">
              <Link
                className="button-primary button-primary--purple rounded-full shadow-sm"
                to="/internal-tickets/new"
              >
                <Plus size={15} aria-hidden="true" />
                Nuevo ticket interno
              </Link>
            </Can>
          </div>
        }
      />

      {exporting && (
        <RequestState
          loading
          compact
          loadingText="Generando archivo..."
          className="mb-3 workspace-caption"
        />
      )}
      {exportError && (
        <FeedbackMessage variant="error" className="mb-3">
          {exportError}
        </FeedbackMessage>
      )}

      {/* PANEL DE FILTROS EXPANDIBLE / CONTRAÍBLE (HOMOGENEIZADO) */}
      <section
        className="filter-toolbar filter-toolbar--purple"
        aria-label="Filtros de tickets internos"
      >
        {/* ENCABEZADO DEL PANEL DE FILTROS */}
        <div
          className={`filter-toolbar-header ${
            collapsed ? 'filter-toolbar-header--collapsed' : ''
          } ${activeCount > 0 ? 'filter-toolbar-header--has-chips' : ''}`}
        >
          <div className="flex flex-wrap items-center gap-2.5">
            <FilterHeading title="Filtros de tickets internos" theme="purple" />
            <span
              className={`filter-count-badge filter-count-badge--purple ${
                activeCount > 0 ? 'filter-count-badge--active' : ''
              }`}
              aria-label={`${activeCount} ${
                activeCount === 1 ? 'filtro activo' : 'filtros activos'
              }`}
            >
              <span className="filter-count-dot" aria-hidden="true" />
              <span>
                {activeCount}{' '}
                {activeCount === 1 ? 'filtro activo' : 'filtros activos'}
              </span>
            </span>
          </div>

          <div className="flex items-center gap-2">
            {activeCount > 0 && (
              <button
                type="button"
                className="button-ghost text-xs text-purple-400 hover:text-purple-300 font-mono py-1 px-2.5 rounded-full"
                onClick={clear}
              >
                Limpiar todo
              </button>
            )}
            <button
              type="button"
              className="filter-toggle-button button-secondary rounded-full"
              onClick={toggleCollapsed}
              aria-expanded={!collapsed}
              aria-controls="internal-tickets-filter-body"
              aria-label={
                !collapsed
                  ? 'Contraer filtros de tickets internos'
                  : 'Expandir filtros de tickets internos'
              }
              title={!collapsed ? 'Contraer filtros' : 'Expandir filtros'}
            >
              <span>{!collapsed ? 'Contraer' : 'Expandir'}</span>
              <ChevronDown
                size={14}
                className={`transition-transform duration-200 ${
                  !collapsed ? 'rotate-180' : ''
                }`}
                aria-hidden="true"
              />
            </button>
          </div>
        </div>

        {/* CHIPS ACTIVOS (SIEMPRE VISIBLES CUANDO HAY FILTROS APLICADOS) */}
        <FilterChips items={activeChips} theme="purple" />

        {/* CUERPO DEL PANEL DE FILTROS */}
        <div
          id="internal-tickets-filter-body"
          className={`p-4 space-y-4 ${collapsed ? 'hidden' : 'block'}`}
        >
          {/* BUSCADOR */}
          <form
            className="flex flex-wrap items-end gap-2.5"
            onSubmit={(e) => {
              e.preventDefault()
              change({ search })
            }}
          >
            <div className="flex-1 min-w-[240px]">
              <FormField id="internal-search" label="Buscar">
                <input
                  id="internal-search"
                  className="form-input"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Correlativo, título o descripción"
                />
              </FormField>
            </div>
            <button type="submit" className="button-secondary rounded-full shrink-0">
              Buscar
            </button>
          </form>

          {/* PERÍODOS RÁPIDOS */}
          <PeriodShortcuts
            includeAll
            label="Período"
            value={params.get('period') ?? 'all'}
            onChange={(period) => change({ period, from: '', to: '' })}
          />

          {/* SELECTORES DE FILTRADO */}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <FormField id="internal-status" label="Estado">
              <select
                id="internal-status"
                className="form-input"
                value={params.get('status') ?? ''}
                onChange={(e) => change({ status: e.target.value })}
              >
                <option value="">Todos</option>
                <option value="OPEN">Abierto</option>
                <option value="CLOSED">Cerrado</option>
              </select>
            </FormField>

            {relationFields.map(([key, label]) => (
              <FormField key={key} id={`filter-${key}`} label={label}>
                <select
                  id={`filter-${key}`}
                  className="form-input"
                  value={params.get(key) ?? ''}
                  onChange={(e) => change({ [key]: e.target.value })}
                >
                  <option value="">Todos</option>
                  {key === 'provider_id' && <option value="none">Ninguno</option>}
                  {catalogs.data?.[key]?.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.name}
                      {row.active ? '' : ' (Inactivo)'}
                    </option>
                  ))}
                </select>
              </FormField>
            ))}

            {params.get('period') === 'custom' &&
              (['from', 'to'] as const).map((key) => (
                <FormField
                  key={key}
                  id={`internal-${key}`}
                  label={key === 'from' ? 'Desde' : 'Hasta'}
                >
                  <input
                    id={`internal-${key}`}
                    type="date"
                    className="form-input"
                    value={params.get(key) ?? ''}
                    onChange={(e) => change({ [key]: e.target.value })}
                  />
                </FormField>
              ))}
          </div>

          <RequestState compact error={catalogs.error} onRetry={catalogs.retry} />

          <div className="flex justify-end pt-1">
            <button type="button" className="button-secondary rounded-full text-xs" onClick={clear}>
              Limpiar filtros
            </button>
          </div>
        </div>
      </section>

      {/* BARRA SECUNDARIA DE ESTADO Y ZONA HORARIA */}
      <div className="mb-2 flex flex-wrap items-center justify-between gap-3 text-xs workspace-caption">
        <span>
          {params.get('status') === 'OPEN'
            ? 'Abiertos'
            : params.get('status') === 'CLOSED'
            ? 'Cerrados'
            : 'Todos los estados'}
        </span>
        <span>Fechas en tu zona horaria local</span>
      </div>

      {/* TABLA O ESTADO DE CARGA */}
      {loading || error || !rows.length ? (
        <RequestState
          loading={loading}
          error={error}
          empty={!rows.length}
          emptyTitle="Sin tickets internos"
          onRetry={() => setRefresh(refresh + 1)}
        />
      ) : (
        <InternalTable rows={rows} />
      )}

      {/* PAGINACIÓN */}
      <PaginationBar
        page={Math.floor(offset / 50) + 1}
        info={<span className="text-xs">Página {Math.floor(offset / 50) + 1}</span>}
        previousDisabled={loading || !offset}
        nextDisabled={loading || Boolean(error) || rows.length < 50}
        onPrevious={() => change({ offset: String(Math.max(0, offset - 50)) }, false)}
        onNext={() => change({ offset: String(offset + 50) }, false)}
      />
    </div>
  )
}

/** TABLA DE TICKETS INTERNOS (NOC ROUNDED) */
function InternalTable({ rows }: { rows: InternalTicket[] }) {
  return (
    <div className="table-surface table-surface--purple overflow-x-auto rounded-2xl border bg-[#0b1426] shadow-xl">
      <table className="operation-table" aria-label="Tickets internos">
        <caption className="table-title">Tickets internos</caption>
        <thead>
          <tr>
            {[
              'Correlativo',
              'Incidencia',
              'Estado',
              'Sector',
              'Nodo',
              'Departamento',
              'Responsable',
              'Tipo de incidencia interna',
              'Atribuible a proveedor',
              'Inicio',
              'Duración',
              'Tickets relacionados',
              'Acciones',
            ].map((x) => (
              <th key={x}>{x}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((t) => (
            <tr
              key={t.id}
              className={t.status === 'OPEN' ? 'ticket-state-open' : 'ticket-state-closed'}
            >
              <th scope="row">
                <Link
                  to={`/internal-tickets/${t.id}`}
                  className="font-mono text-sm font-bold text-purple-400 hover:text-purple-300"
                >
                  {t.reference}
                </Link>
              </th>
              <td>
                <span className="font-semibold text-slate-100">{t.title}</span>
              </td>
              <td>
                <StatusBadge status={t.status} />
              </td>
              <td>{t.sector.name}</td>
              <td>{t.node?.name ?? 'Sin asignar'}</td>
              <td>{t.department.name}</td>
              <td>{t.responsible?.name ?? 'Sin asignar'}</td>
              <td>{t.incident_type.name}</td>
              <td>{t.provider?.name ?? 'Ninguno'}</td>
              <td className="font-mono text-xs">{formatDate(t.start_at)}</td>
              <td className="font-mono text-xs">{formatDuration(t.duration_seconds, t.status)}</td>
              <td className="font-mono text-center">
                <span className="inline-flex px-2 py-0.5 rounded-full text-xs bg-slate-900 border border-slate-700 text-slate-300">
                  {t.related_count}
                </span>
              </td>
              <td>
                <Can anyOf={['internal_tickets.edit', 'internal_tickets.close']}>
                  <Link
                    className="button-secondary table-action rounded-full"
                    to={`/internal-tickets/${t.id}/edit`}
                  >
                    Editar
                  </Link>
                </Can>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** VISTA 3: EDITOR (NUEVO O EXISTENTE) */
export function InternalTicketEditor({ edit = false }: { edit?: boolean }) {
  const { id } = useParams()
  return edit ? <ExistingEditor key={id} id={id} /> : <InternalForm />
}

function ExistingEditor({ id }: { id: string | undefined }) {
  const result = useInternal(id)
  return result.item ? (
    <InternalForm key={result.item.id} ticket={result.item} />
  ) : (
    <RequestState
      loading={!result.error}
      error={result.error}
      onRetry={result.retry}
    />
  )
}

/** FORMULARIO DE TICKET INTERNO (BLOQUE E STYLE — 3 COLUMNAS ASIMÉTRICAS) */
function InternalForm({ ticket }: { ticket?: InternalTicket }) {
  const access = usePermissions()
  const mayClose = access.can('internal_tickets.close')
  const editable = !ticket || access.can('internal_tickets.edit')
  const navigate = useNavigate()
  const catalogs = useCatalogs()
  const sending = useRef(false)

  const [values, setValues] = useState(() => ({
    title: ticket?.title ?? '',
    description: ticket?.description ?? '',
    resolution: ticket?.resolution ?? '',
    sector_id: ticket ? String(ticket.sector_id) : '',
    node_id: ticket?.node_id ? String(ticket.node_id) : '',
    department_id: ticket ? String(ticket.department_id) : '',
    responsible_id: ticket?.responsible_id ? String(ticket.responsible_id) : '',
    incident_type_id: ticket ? String(ticket.incident_type_id) : '',
    provider_id: ticket?.provider_id ? String(ticket.provider_id) : '',
    status: ticket?.status ?? 'OPEN',
    start_at: localDateTimeValue(ticket ? new Date(ticket.start_at) : undefined),
    end_at: ticket?.end_at ? localDateTimeValue(new Date(ticket.end_at)) : '',
  }))

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function change(key: keyof typeof values, value: string) {
    setValues((v) => ({ ...v, [key]: value }))
  }

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (sending.current) return
    setError(null)
    try {
      if (
        !values.title.trim() ||
        !values.description.trim() ||
        !values.sector_id ||
        !values.department_id ||
        !values.incident_type_id ||
        !values.start_at
      ) {
        throw Error('Completa los campos obligatorios antes de guardar.')
      }
      const start =
        values.start_at === (ticket && localDateTimeValue(new Date(ticket.start_at)))
          ? ticket!.start_at
          : localDateTimeToIso(values.start_at)
      const end = values.end_at
        ? values.end_at === (ticket?.end_at && localDateTimeValue(new Date(ticket.end_at)))
          ? ticket!.end_at
          : localDateTimeToIso(values.end_at)
        : null
      if (end && new Date(end) < new Date(start)) {
        throw Error('Fin debe ser igual o posterior a Inicio.')
      }
      const payload = {
        ...values,
        title: values.title.trim(),
        description: values.description.trim(),
        resolution: values.resolution.trim() ? values.resolution : null,
        start_at: start,
        end_at: end,
        ...Object.fromEntries(
          relationFields.map(([key]) => [
            key,
            values[key] ? Number(values[key]) : null,
          ])
        ),
      }
      sending.current = true
      setSaving(true)
      const saved = ticket
        ? await patchJson<InternalTicket>(`${root}/${ticket.id}`, payload)
        : await postJson<InternalTicket>(root, payload)
      navigate(`/internal-tickets/${saved.id}`)
    } catch (f) {
      setError(f instanceof Error ? f.message : 'No se pudo guardar.')
    } finally {
      sending.current = false
      setSaving(false)
    }
  }

  return (
    <div className="space-y-5">
      {/* RECORD HEADER: NUEVO / EDITAR TICKET INTERNO */}
      <div className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4 min-w-0">
          <div
            className="h-12 w-12 shrink-0 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white shadow-lg shadow-indigo-500/20"
            aria-hidden="true"
          >
            <Server size={24} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[11px] font-mono text-indigo-400 font-bold uppercase tracking-wider">
              <span>OPERACIÓN</span>
              <span className="text-slate-600">/</span>
              <span>{ticket ? 'EDICIÓN DE TICKET INTERNO' : 'NUEVO TICKET INTERNO'}</span>
            </div>
            <div className="flex flex-wrap items-center gap-3 mt-0.5">
              <h1 className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-white">
                {ticket ? `Editar ${ticket.reference}` : 'Nuevo ticket interno'}
              </h1>
              {ticket ? (
                <StatusBadge status={values.status as 'OPEN' | 'CLOSED'} />
              ) : (
                <span className="inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full text-[11px] font-mono bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 font-bold">
                  NUEVO REGISTRO INTERNO
                </span>
              )}
            </div>
            {ticket ? (
              <p className="mt-1 text-sm font-semibold text-slate-300 truncate">
                {ticket.title}
              </p>
            ) : (
              <p className="mt-1 text-xs text-slate-400">
                Gestión operativa de infraestructura, sin cliente ni circuito.
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="button-secondary rounded-full"
            onClick={() =>
              navigate(ticket ? `/internal-tickets/${ticket.id}` : '/internal-tickets')
            }
          >
            {ticket ? 'Volver al detalle' : 'Volver a tickets internos'}
          </button>
        </div>
      </div>

      <RequestState
        compact
        loading={!catalogs.data && !catalogs.error}
        error={catalogs.error}
        onRetry={catalogs.retry}
      />

      <form
        className="ticket-noc-form"
        aria-label={ticket ? 'Editar ticket interno' : 'Crear ticket interno'}
        onSubmit={submit}
        noValidate
      >
        <fieldset
          className="space-y-5 min-w-0"
          disabled={saving || !catalogs.data || Boolean(catalogs.error)}
        >
          <legend className="sr-only">Datos del ticket interno</legend>

          <div className="grid gap-5 lg:grid-cols-3">
            {/* COLUMNA PRINCIPAL (2 COLS) */}
            <div className="lg:col-span-2 space-y-5">
              {/* TARJETA: INCIDENCIA */}
              <section className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-sky-500/15">
                  <div className="flex items-center gap-2">
                    <span
                      className="flex h-6 w-6 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs"
                      aria-hidden="true"
                    >
                      <FileText size={13} />
                    </span>
                    <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
                      Incidencia
                    </h2>
                  </div>
                  <span className="text-[11px] font-mono text-slate-500">Datos primarios</span>
                </div>

                <FormField id="internal-title" label="Título" required>
                  <input
                    readOnly={!editable}
                    id="internal-title"
                    className="form-input"
                    value={values.title}
                    onChange={(e) => change('title', e.target.value)}
                    placeholder="Ej. Caída de energía en nodo norte"
                  />
                </FormField>

                <FormField id="internal-description" label="Descripción" required>
                  <textarea
                    readOnly={!editable}
                    id="internal-description"
                    rows={4}
                    className="form-input resize-y"
                    value={values.description}
                    onChange={(e) => change('description', e.target.value)}
                    placeholder="Detalle técnico de la infraestructura afectada..."
                  />
                </FormField>
              </section>

              {/* TARJETA: CLASIFICACIÓN DE INFRAESTRUCTURA */}
              <section className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-sky-500/15">
                  <div className="flex items-center gap-2">
                    <span
                      className="flex h-6 w-6 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs"
                      aria-hidden="true"
                    >
                      <Tag size={13} />
                    </span>
                    <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
                      Clasificación
                    </h2>
                  </div>
                  <span className="text-[11px] font-mono text-slate-500">
                    Infraestructura NOC
                  </span>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  {relationFields.map(([key, label, required]) => (
                    <FormField key={key} id={`internal-${key}`} label={label} required={required}>
                      <SearchableSelect
                        disabled={!editable}
                        id={`internal-${key}`}
                        label={label}
                        required={required}
                        value={values[key]}
                        onChange={(v) => change(key, v)}
                        options={(catalogs.data?.[key] ?? [])
                          .filter(
                            (x) =>
                              (key !== 'responsible_id' ||
                                operationalChoice(
                                  x,
                                  ticket?.responsible_id ? [ticket.responsible_id] : []
                                )) &&
                              (x.active || String(x.id) === values[key])
                          )
                          .map((x) => ({
                            value: String(x.id),
                            label: x.name,
                            disabled: !x.active,
                          }))}
                        placeholder={
                          key === 'provider_id'
                            ? 'Ninguno'
                            : required
                            ? 'Selecciona una opción'
                            : 'Sin asignar'
                        }
                        emptyMessage="No hay registros activos."
                        noMatchMessage="Sin coincidencias."
                      />
                    </FormField>
                  ))}

                  <FormField id="internal-state" label="Estado" required>
                    <select
                      id="internal-state"
                      disabled={!mayClose}
                      className="form-input"
                      value={values.status}
                      onChange={(e) => change('status', e.target.value)}
                    >
                      <option value="OPEN">Abierto</option>
                      <option value="CLOSED">Cerrado</option>
                    </select>
                  </FormField>
                </div>
              </section>

              {/* TARJETA: RESOLUCIÓN DOCUMENTADA */}
              <section className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-3">
                <div className="flex items-center justify-between pb-3 border-b border-sky-500/15">
                  <div className="flex items-center gap-2">
                    <span
                      className="flex h-6 w-6 items-center justify-center rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs"
                      aria-hidden="true"
                    >
                      <Check size={13} />
                    </span>
                    <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
                      Resolución documentada
                    </h2>
                  </div>
                  <span className="text-[11px] font-mono text-emerald-400/80">
                    Cierre operativo
                  </span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed m-0">
                  Opcional. Explica cómo se resolvió la incidencia interna. Los cambios quedan
                  registrados en el seguimiento.
                </p>
                <FormField id="internal-resolution" label="Resolución interna">
                  <textarea
                    id="internal-resolution"
                    className="form-input resize-y"
                    rows={3}
                    maxLength={10000}
                    value={values.resolution}
                    onChange={(e) => change('resolution', e.target.value)}
                    placeholder="Descripción técnica de la solución aplicada..."
                  />
                </FormField>
              </section>
            </div>

            {/* COLUMNA LATERAL (1 COL) */}
            <div className="lg:col-span-1 space-y-5">
              {/* TARJETA: TIEMPOS OPERATIVOS */}
              <section className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-4">
                <div className="flex items-center justify-between pb-3 border-b border-sky-500/15">
                  <div className="flex items-center gap-2">
                    <span
                      className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs"
                      aria-hidden="true"
                    >
                      <Clock size={13} />
                    </span>
                    <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
                      Tiempos operativos
                    </h2>
                  </div>
                  <span className="text-[11px] font-mono text-amber-400/80">Cronología</span>
                </div>

                {ticket && mayClose && (
                  <button
                    type="button"
                    className="button-secondary rounded-full w-full py-1.5 text-xs flex items-center justify-center gap-1.5 border-amber-500/30 text-amber-300 hover:bg-amber-500/15 transition-colors mb-3"
                    onClick={() =>
                      setValues((v) => ({
                        ...v,
                        status: 'CLOSED',
                        end_at: localDateTimeValue(),
                      }))
                    }
                  >
                    <Clock size={13} aria-hidden="true" />
                    Finalizar ahora
                  </button>
                )}

                <div className="space-y-3">
                  {(['start_at', 'end_at'] as const).map((key) => (
                    <FormField
                      key={key}
                      id={`internal-${key}`}
                      label={key === 'start_at' ? 'Inicio' : 'Fin'}
                      required={key === 'start_at'}
                    >
                      <div className="flex gap-2">
                        <input
                          disabled={key === 'start_at' && !editable}
                          id={`internal-${key}`}
                          type="datetime-local"
                          step="60"
                          className="form-input min-w-0"
                          value={values[key]}
                          onChange={(e) => change(key, e.target.value)}
                        />
                        <button
                          type="button"
                          className="button-secondary rounded-full px-3 text-xs"
                          disabled={key === 'start_at' && !editable}
                          onClick={() => change(key, localDateTimeValue())}
                        >
                          Ahora
                        </button>
                      </div>
                    </FormField>
                  ))}
                </div>
              </section>

              {/* TARJETA: ACCIONES Y GUARDADO */}
              <div className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-4 sticky top-20">
                <div className="flex items-center justify-between pb-3 border-b border-sky-500/15">
                  <span className="text-xs font-bold font-mono text-white uppercase tracking-wider">
                    Acciones
                  </span>
                  <span className="text-[11px] font-mono text-slate-500">
                    {ticket ? 'Edición' : 'Creación'}
                  </span>
                </div>

                <p className="text-xs text-slate-400 leading-relaxed m-0">
                  {ticket
                    ? 'Actualiza los datos de infraestructura del ticket interno.'
                    : 'Registra la incidencia interna en el sistema del NOC.'}
                </p>

                {error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}

                <div className="pt-2 space-y-2.5">
                  <button
                    type="submit"
                    className="button-primary w-full py-2.5 text-sm font-semibold rounded-full shadow-lg shadow-sky-500/25"
                    disabled={saving || !catalogs.data || Boolean(catalogs.error)}
                  >
                    {saving
                      ? 'Guardando...'
                      : ticket
                      ? 'Guardar cambios'
                      : 'Guardar'}
                  </button>
                  <button
                    type="button"
                    className="button-secondary w-full py-2 text-xs rounded-full"
                    disabled={saving}
                    onClick={() =>
                      navigate(ticket ? `/internal-tickets/${ticket.id}` : '/internal-tickets')
                    }
                  >
                    Cancelar
                  </button>
                </div>
              </div>
            </div>
          </div>
        </fieldset>
      </form>
    </div>
  )
}

/** VISTA 2: DETALLE DE TICKET INTERNO */
export function InternalTicketDetail() {
  const { id } = useParams()
  const result = useInternal(id)
  if (!result.item) {
    return (
      <RequestState
        loading={!result.error}
        error={result.error}
        onRetry={result.retry}
      />
    )
  }
  return <InternalDetail key={result.item.id} ticket={result.item} />
}

function InternalDetail({ ticket: t }: { ticket: InternalTicket }) {
  const [related, setRelated] = useState<{ total: number; items: Ticket[] } | null>(null)
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0)

  useEffect(() => {
    const c = new AbortController()
    setRelated(null)
    setError(null)
    getJson<{ total: number; items: Ticket[] }>(
      `${root}/${t.id}/related?limit=50&offset=${offset}`,
      c.signal
    )
      .then((x) => {
        if (!c.signal.aborted) setRelated(x)
      })
      .catch((f) => {
        if (!c.signal.aborted) {
          setError(
            f instanceof Error
              ? f.message
              : 'No se pudieron cargar las relaciones.'
          )
        }
      })
    return () => c.abort()
  }, [t.id, offset, retry])

  return (
    <div className="space-y-6">
      {/* RECORD HEADER: DETALLE DE TICKET INTERNO */}
      <div className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4 min-w-0">
          <div
            className="h-12 w-12 shrink-0 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white shadow-lg shadow-indigo-500/20"
            aria-hidden="true"
          >
            <Server size={24} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-[11px] font-mono text-indigo-400 font-bold uppercase tracking-wider">
              <span>OPERACIÓN</span>
              <span className="text-slate-600">/</span>
              <span>DETALLE DE TICKET INTERNO</span>
            </div>
            <div className="flex flex-wrap items-center gap-3 mt-0.5">
              <h1 className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-white">
                {t.reference}
              </h1>
              <StatusBadge status={t.status} />
              {t.node && (
                <span className="inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full text-[11px] font-mono bg-slate-900 border border-slate-700 text-slate-300">
                  <span className="text-slate-500">Nodo:</span>{' '}
                  <strong className="text-indigo-300">{t.node.name}</strong>
                </span>
              )}
            </div>
            <p className="mt-1 text-sm font-semibold text-slate-300 truncate">
              {t.title}
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Can permission="internal_tickets.export">
            <InternalTicketReportDownload id={t.id} reference={t.reference} />
          </Can>
          <Link className="button-secondary rounded-full" to="/internal-tickets">
            Volver a tickets internos
          </Link>
          <Can anyOf={['internal_tickets.edit', 'internal_tickets.close']}>
            <Link
              className="button-primary rounded-full shadow-lg shadow-sky-500/25"
              to={`/internal-tickets/${t.id}/edit`}
            >
              Editar ticket interno
            </Link>
          </Can>
        </div>
      </div>

      {/* 2 COLUMNAS EN ESCRITORIO: DESCRIPCIÓN Y RESOLUCIÓN */}
      <div className="grid gap-5 md:grid-cols-2">
        {/* TARJETA 1: DESCRIPCIÓN */}
        <section className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-3">
          <div className="flex items-center justify-between pb-3 border-b border-sky-500/15">
            <div className="flex items-center gap-2">
              <span
                className="flex h-6 w-6 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs"
                aria-hidden="true"
              >
                <FileText size={13} />
              </span>
              <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
                Descripción
              </h2>
            </div>
            <span className="text-[11px] font-mono text-slate-500">Datos primarios</span>
          </div>
          <p className="whitespace-pre-wrap [overflow-wrap:anywhere] text-sm text-slate-200 leading-relaxed m-0">
            {t.description}
          </p>
        </section>

        {/* TARJETA 2: RESOLUCIÓN DOCUMENTADA */}
        <section className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-3">
          <div className="flex items-center justify-between pb-3 border-b border-sky-500/15">
            <div className="flex items-center gap-2">
              <span
                className="flex h-6 w-6 items-center justify-center rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs"
                aria-hidden="true"
              >
                <Check size={13} />
              </span>
              <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
                Resolución documentada
              </h2>
            </div>
            <span className="text-[11px] font-mono text-emerald-400/80">
              Cierre operativo
            </span>
          </div>
          <p className="whitespace-pre-wrap [overflow-wrap:anywhere] text-sm text-slate-300 leading-relaxed m-0">
            {t.resolution ?? 'Sin resolución documentada.'}
          </p>
        </section>
      </div>

      {/* CLASIFICACIÓN Y TIEMPOS OPERATIVOS (GRILLA ASIMÉTRICA NOC) */}
      <div className="grid gap-5 lg:grid-cols-3">
        {/* COLUMNA 1 & 2: FICHA DE CLASIFICACIÓN (2 COLS) */}
        <section className="lg:col-span-2 p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-sky-500/15">
            <div className="flex items-center gap-2">
              <span
                className="flex h-6 w-6 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs"
                aria-hidden="true"
              >
                <Tag size={13} />
              </span>
              <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
                Clasificación de infraestructura
              </h2>
            </div>
            <span className="text-[11px] font-mono text-slate-500">Topología NOC</span>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 text-xs">
            <div className="p-3 rounded-xl bg-[#070d1a] border border-slate-800 space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 font-bold">
                Sector
              </span>
              <p className="text-sm font-semibold text-white">{t.sector.name}</p>
            </div>

            <div className="p-3 rounded-xl bg-[#070d1a] border border-slate-800 space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 font-bold">
                Nodo
              </span>
              <p className="text-sm font-semibold text-white">
                {t.node?.name ?? 'Sin asignar'}
              </p>
            </div>

            <div className="p-3 rounded-xl bg-[#070d1a] border border-slate-800 space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 font-bold">
                Departamento
              </span>
              <p className="text-sm font-semibold text-white">{t.department.name}</p>
            </div>

            <div className="p-3 rounded-xl bg-[#070d1a] border border-slate-800 space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 font-bold">
                Responsable
              </span>
              <p className="text-sm font-semibold text-white">
                {t.responsible?.name ?? 'Sin asignar'}
              </p>
            </div>

            <div className="p-3 rounded-xl bg-[#070d1a] border border-slate-800 space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 font-bold">
                Tipo de incidencia interna
              </span>
              <p className="text-sm font-semibold text-white">{t.incident_type.name}</p>
            </div>

            <div className="p-3 rounded-xl bg-[#070d1a] border border-slate-800 space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 font-bold">
                Atribuible a proveedor
              </span>
              <p className="text-sm font-semibold text-white">
                {t.provider?.name ?? 'Ninguno'}
              </p>
            </div>
          </div>
        </section>

        {/* COLUMNA 3: TIEMPOS OPERATIVOS & DURACIÓN (1 COL) */}
        <section className="lg:col-span-1 p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-sky-500/15">
            <div className="flex items-center gap-2">
              <span
                className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs"
                aria-hidden="true"
              >
                <Clock size={13} />
              </span>
              <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
                Tiempos operativos
              </h2>
            </div>
            <span className="text-[11px] font-mono text-amber-400/80">Cronología</span>
          </div>

          <dl className="space-y-3">
            {/* CALLOUT PROTAGÓNICO DE DURACIÓN OPERATIVA */}
            <div className="p-3.5 rounded-xl bg-[#070d1a] border border-sky-500/30">
              <dt className="text-[11px] font-mono uppercase tracking-wider text-sky-400 font-bold">
                Duración
              </dt>
              <dd className="text-xl font-mono font-bold text-white mt-1">
                {formatDuration(t.duration_seconds, t.status)}
              </dd>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="p-2.5 rounded-xl bg-[#070d1a] border border-slate-800 space-y-0.5">
                <dt className="text-[10px] font-mono uppercase tracking-wider text-slate-400 font-bold">
                  Inicio
                </dt>
                <dd className="font-mono text-slate-200">{formatDate(t.start_at)}</dd>
              </div>

              <div className="p-2.5 rounded-xl bg-[#070d1a] border border-slate-800 space-y-0.5">
                <dt className="text-[10px] font-mono uppercase tracking-wider text-slate-400 font-bold">
                  Fin
                </dt>
                <dd className="font-mono text-slate-200">{formatDate(t.end_at)}</dd>
              </div>
            </div>

            <div className="pt-2 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400 font-mono">
              <div>
                <dt className="inline text-slate-500">Creado: </dt>
                <dd className="inline text-slate-300">{formatDate(t.created_at)}</dd>
              </div>
              <div>
                <dt className="inline text-slate-500">Actualizado: </dt>
                <dd className="inline text-slate-300">{formatDate(t.updated_at)}</dd>
              </div>
            </div>
          </dl>
        </section>
      </div>

      {/* CAMBIOS RELACIONADOS */}
      <Can permission="changes.view">
        <RelatedChanges internalTicketId={t.id} />
      </Can>

      {/* ESCALAMIENTOS */}
      <TicketEscalations ticketId={t.id} internal />

      {/* SEGUIMIENTO E INTERVENCIONES */}
      <TicketFollowUp ticketId={t.id} internal />

      {/* TICKETS DE CLIENTES RELACIONADOS */}
      <section className="p-5 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-sky-500/15">
          <div className="flex items-center gap-2">
            <span
              className="flex h-6 w-6 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs"
              aria-hidden="true"
            >
              <Users size={13} />
            </span>
            <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
              Tickets de clientes relacionados{related ? ` (${related.total})` : ''}
            </h2>
          </div>
          <span className="text-[11px] font-mono text-slate-500">Impacto a clientes</span>
        </div>

        <RequestState
          compact
          loading={!related && !error}
          error={error}
          empty={related?.items.length === 0}
          emptyTitle="Sin tickets relacionados"
          onRetry={() => setRetry(retry + 1)}
        />

        {related && related.items.length > 0 && (
          <div className="table-surface overflow-x-auto rounded-xl border border-sky-500/20">
            <table className="operation-table">
              <thead>
                <tr>
                  {['Correlativo', 'Cliente', 'Incidencia', 'Estado'].map((x) => (
                    <th key={x}>{x}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {related.items.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <Can permission="tickets.view" fallback={row.reference}>
                        <Link
                          to={`/tickets/${row.id}`}
                          className="font-mono text-xs font-bold text-sky-400 hover:text-sky-300"
                        >
                          {row.reference}
                        </Link>
                      </Can>
                    </td>
                    <td className="text-xs">
                      {row.customer?.customer_code} — {row.customer?.name}
                    </td>
                    <td className="text-xs text-slate-200">{row.title}</td>
                    <td>
                      <StatusBadge status={row.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <PaginationBar
          page={Math.floor(offset / 50) + 1}
          info={<span className="text-xs">Página {Math.floor(offset / 50) + 1}</span>}
          previousDisabled={!related || offset === 0}
          nextDisabled={!related || offset + 50 >= related.total}
          onPrevious={() => setOffset(Math.max(0, offset - 50))}
          onNext={() => setOffset(offset + 50)}
        />
      </section>
    </div>
  )
}
