import { operationalChoice } from '../lib/responsibles'
import { Can, usePermissions } from '../auth/permissions'
import { SearchableMultiSelect } from '../components/SearchableMultiSelect'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import {
  FileText,
  FileSpreadsheet,
  Plus,
  RefreshCw,
  Clock,
  Tag,
  Layers,
  MessageSquare,
  History,
  Calendar as CalendarIcon,
} from 'lucide-react'
import { getJson, postJson, patchJson, downloadFile } from '../api/client'
import { PageHeading } from '../components/PageHeading'
import { PaginationBar } from '../components/PaginationBar'
import { FormField } from '../components/FormField'
import { RequestState } from './../components/RequestState'
import { FeedbackMessage } from '../components/FeedbackMessage'
import {
  ChangeFilters,
  ChangeTable,
  ChangeEfficiency,
  ChangeTicketLinks,
  useChangeCatalogs,
  changeQuery,
  changeFilterKeys,
  changeStatuses,
} from '../components/ChangeShared'
import { useUrlFilters } from '../hooks/useUrlFilters'
import {
  ticketynDateTimeValue,
  ticketynDateTimeToIso,
  ticketynTimezone,
} from '../lib/datetime'
import { formatDate, formatDuration } from '../lib/format'
import type { Change, ChangeStatus, ChangeUpdate } from '../types/change'

const failure = (f: unknown) =>
  f instanceof Error ? f.message : 'No se pudo completar la solicitud.'

const auditLabels: Record<string, string> = {
  change_type_id: 'Tipo de cambio (referencia)',
  title: 'Título',
  description: 'Descripción',
  sector_id: 'Sector',
  node_id: 'Nodo',
  manager_id: 'Encargado (referencia)',
  manager_name: 'Encargado',
  department_id: 'Departamento (referencia)',
  department_name: 'Departamento',
  status: 'Estado',
  proposed_start: 'Inicio propuesto',
  proposed_end: 'Fin propuesto',
  actual_start: 'Inicio real',
  actual_end: 'Fin real',
  completion_type_id: 'Tipo de finalización (referencia)',
  completion_name: 'Tipo de finalización',
  efficiency_eligible: 'Elegibilidad histórica para eficiencia',
  final_notes: 'Notas finales',
  support: 'Personal de apoyo',
  internal_ticket_ids: 'Tickets internos (referencias)',
}

function auditText(value: unknown): string {
  if (value === null || value === undefined) return 'Sin registrar'
  if (typeof value === 'boolean') return value ? 'Sí' : 'No'
  if (Array.isArray(value))
    return value.length ? value.map(auditText).join(', ') : 'Sin asignaciones'
  if (typeof value === 'object' && 'name' in value) return String(value.name)
  if (typeof value === 'string' && value in changeStatuses)
    return changeStatuses[value as ChangeStatus]
  return String(value)
}

export function ChangeExportButtons({
  query,
  report = false,
  disabled = false,
}: {
  query: URLSearchParams
  report?: boolean
  disabled?: boolean
}) {
  const pending = useRef(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null)

  async function download(format: 'pdf' | 'xlsx') {
    if (pending.current || disabled) return
    pending.current = true
    setBusy(true)
    setError(null)
    try {
      const params = new URLSearchParams(query)
      params.delete('limit')
      params.delete('offset')
      params.set('timezone', ticketynTimezone)
      await downloadFile(
        `/api/${report ? 'change-reports' : 'changes'}/export/${format}?${params}`,
        `ticketyn-${report ? 'reporte-' : ''}cambios.${format}`
      )
    } catch (f) {
      setError(failure(f))
    } finally {
      pending.current = false
      setBusy(false)
    }
  }

  return (
    <Can permission={report ? 'reports.changes.export' : 'changes.export'}>
      <button
        className="button-secondary rounded-full shadow-xs"
        disabled={disabled || busy}
        onClick={() => void download('pdf')}
      >
        <FileText size={14} aria-hidden="true" />
        {busy ? 'Generando...' : 'Exportar PDF'}
      </button>
      <button
        className="button-secondary rounded-full shadow-xs"
        disabled={disabled || busy}
        onClick={() => void download('xlsx')}
      >
        <FileSpreadsheet size={14} aria-hidden="true" />
        Exportar Excel
      </button>
      {error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}
    </Can>
  )
}

export function Changes() {
  const { params, change, clear } = useUrlFilters(changeFilterKeys),
    catalog = useChangeCatalogs()
  const [data, setData] = useState<{ total: number; items: Change[] } | null>(
      null
    ),
    [loading, setLoading] = useState(true),
    [error, setError] = useState<string | null>(null),
    [retry, setRetry] = useState(0)
  const view =
    params.get('view') ?? localStorage.getItem('ticketyn-change-view') ?? 'list'
  let query = new URLSearchParams(),
    invalid: string | null = null
  try {
    query = changeQuery(params)
  } catch (f) {
    invalid = failure(f)
  }
  const offset = Math.max(0, Number(params.get('offset')) || 0),
    key = query.toString()

  useEffect(() => {
    if (view !== 'list' || invalid) return
    const c = new AbortController()
    setLoading(true)
    setError(null)
    getJson<{ total: number; items: Change[] }>(
      `/api/changes?${key}&limit=50&offset=${offset}`,
      c.signal
    )
      .then((rows) => {
        if (!c.signal.aborted) {
          setData(rows)
          setLoading(false)
        }
      })
      .catch((f) => {
        if (!c.signal.aborted) {
          setError(failure(f))
          setLoading(false)
        }
      })
    return () => c.abort()
  }, [key, offset, retry, view, invalid])

  function setView(value: string) {
    localStorage.setItem('ticketyn-change-view', value)
    change({ view: value })
  }

  return (
    <>
      <PageHeading
        title="Control de cambios"
        description="Planificación, ejecución y bitácora operativa del NOC."
        telemetry={
          !loading && !error && data && (
            <span className="heading-telemetry">
              <span>Total:</span>
              <strong className="telemetry-value--amber">{data.total}</strong>
            </span>
          )
        }
        action={
          <div className="flex flex-wrap items-center gap-2">
            <ChangeExportButtons query={query} disabled={Boolean(invalid)} />
            <Can permission="changes.create">
              <Link
                className="button-primary button-primary--amber rounded-full shadow-sm"
                to="/changes/new"
              >
                <Plus size={15} aria-hidden="true" />
                Nuevo cambio
              </Link>
            </Can>
          </div>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="segmented-control segmented-control--soft segmented-control--amber">
          <button
            className="segment-button"
            aria-pressed={view === 'list'}
            onClick={() => setView('list')}
          >
            Listado
          </button>
          <button
            className="segment-button"
            aria-pressed={view === 'calendar'}
            onClick={() => setView('calendar')}
          >
            Calendario
          </button>
        </div>
        <button
          className="button-secondary rounded-full shadow-xs"
          onClick={() => setRetry(retry + 1)}
          disabled={loading && view === 'list'}
        >
          <RefreshCw size={14} aria-hidden="true" />
          Actualizar
        </button>
      </div>

      <ChangeFilters
        params={params}
        change={change}
        clear={clear}
        catalogs={catalog.catalogs}
      />
      <RequestState
        compact
        error={catalog.error}
        onRetry={catalog.retry}
      />

      {invalid ? (
        <FeedbackMessage variant="error">{invalid}</FeedbackMessage>
      ) : view === 'calendar' ? (
        <ChangeCalendar
          params={params}
          change={change}
          query={query}
          retry={retry}
        />
      ) : (
        <>
          <RequestState
            loading={loading}
            error={error}
            empty={!loading && !error && data?.total === 0}
            emptyTitle="Sin cambios registrados"
            onRetry={() => setRetry(retry + 1)}
          />
          {!loading && !error && data && data.items.length > 0 && (
            <ChangeTable rows={data.items} />
          )}
          <PaginationBar
            page={Math.floor(offset / 50) + 1}
            info={
              <span className="text-xs font-mono text-muted">
                {data?.total ?? 0} cambios · Página{' '}
                {Math.floor(offset / 50) + 1}
              </span>
            }
            previousDisabled={loading || offset === 0}
            nextDisabled={loading || !data || offset + 50 >= data.total}
            onPrevious={() =>
              change({ offset: String(Math.max(0, offset - 50)) }, false)
            }
            onNext={() => change({ offset: String(offset + 50) }, false)}
          />
        </>
      )}
    </>
  )
}

function calendarDate(value: Date) {
  return value.toISOString().slice(0, 10)
}

function ChangeCalendar({
  params,
  change,
  query,
  retry,
}: {
  params: URLSearchParams
  change: (v: Record<string, string>) => void
  query: URLSearchParams
  retry: number
}) {
  const day =
      params.get('day') ?? ticketynDateTimeValue(new Date()).slice(0, 10),
    mode = params.get('calendar') ?? 'month',
    anchor = new Date(day + 'T12:00:00Z')
  const begin = new Date(anchor)
  if (mode === 'month') begin.setUTCDate(1)
  else if (mode === 'week')
    begin.setUTCDate(begin.getUTCDate() - ((begin.getUTCDay() + 6) % 7))
  const end = new Date(begin)
  if (mode === 'month') end.setUTCMonth(end.getUTCMonth() + 1)
  else end.setUTCDate(end.getUTCDate() + (mode === 'week' ? 7 : 1))
  const first = calendarDate(begin),
    last = calendarDate(end),
    key = query.toString()
  const [items, setItems] = useState<Change[]>([]),
    [loading, setLoading] = useState(true),
    [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const c = new AbortController()
    setLoading(true)
    setError(null)
    async function load() {
      const q = new URLSearchParams(key),
        start = ticketynDateTimeToIso(first + 'T00:00'),
        finish = ticketynDateTimeToIso(last + 'T00:00')
      q.set(
        'from',
        q.get('from') && new Date(q.get('from')!) > new Date(start)
          ? q.get('from')!
          : start
      )
      q.set(
        'to',
        q.get('to') && new Date(q.get('to')!) < new Date(finish)
          ? q.get('to')!
          : finish
      )
      if (new Date(q.get('from')!) >= new Date(q.get('to')!)) {
        setItems([])
        setLoading(false)
        return
      }
      const rows: Change[] = []
      for (let offset = 0; ; offset += 200) {
        q.set('limit', '200')
        q.set('offset', String(offset))
        const page = await getJson<{ total: number; items: Change[] }>(
          `/api/changes?${q}`,
          c.signal
        )
        rows.push(...page.items)
        if (rows.length >= page.total || page.items.length === 0) break
      }
      if (!c.signal.aborted) {
        setItems(rows)
        setLoading(false)
      }
    }
    void load().catch((f) => {
      if (!c.signal.aborted) {
        setError(failure(f))
        setLoading(false)
      }
    })
    return () => c.abort()
  }, [first, last, key, retry])

  function move(direction: number) {
    const value = new Date(anchor)
    if (mode === 'month') {
      value.setUTCDate(1)
      value.setUTCMonth(value.getUTCMonth() + direction)
    } else
      value.setUTCDate(
        value.getUTCDate() + direction * (mode === 'week' ? 7 : 1)
      )
    change({ day: calendarDate(value) })
  }

  const days = []
  for (
    const d = new Date(begin);
    d < end;
    d.setUTCDate(d.getUTCDate() + 1)
  )
    days.push(calendarDate(d))
  const padding = mode === 'month' ? (begin.getUTCDay() + 6) % 7 : 0
  const weekdays = [
    'Lunes',
    'Martes',
    'Miércoles',
    'Jueves',
    'Viernes',
    'Sábado',
    'Domingo',
  ]
  const weekday = (date: string) =>
    weekdays[(new Date(date + 'T12:00:00Z').getUTCDay() + 6) % 7]
  const today = ticketynDateTimeValue(new Date()).slice(0, 10)

  return (
    <section className="p-5 rounded-2xl bg-[#0b1426] border border-amber-500/20 shadow-xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-amber-500/15 pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <button
            className="button-secondary rounded-full w-8 h-8 p-0 flex items-center justify-center font-bold text-slate-300 hover:text-white"
            onClick={() => move(-1)}
            aria-label="Período anterior"
          >
            ‹
          </button>
          <FormField id="calendar-date" label="Fecha del calendario">
            <input
              className="form-input rounded-full text-xs font-mono bg-[#070d1a] border-slate-700 text-slate-200"
              id="calendar-date"
              type="date"
              value={day}
              onChange={(e) => {
                if (e.target.value) change({ day: e.target.value })
              }}
            />
          </FormField>
          <button
            className="button-secondary rounded-full w-8 h-8 p-0 flex items-center justify-center font-bold text-slate-300 hover:text-white"
            onClick={() => move(1)}
            aria-label="Período siguiente"
          >
            ›
          </button>
        </div>
        <div className="segmented-control segmented-control--soft segmented-control--amber">
          {[
            ['month', 'Mes'],
            ['week', 'Semana'],
            ['day', 'Día'],
          ].map(([value, label]) => (
            <button
              className="segment-button"
              key={value}
              aria-pressed={mode === value}
              onClick={() => change({ calendar: value })}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <p className="text-xs text-slate-400 font-mono flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 inline-block" />
        <span>Ubicación por Inicio propuesto · {ticketynTimezone}. La ventana propuesta se conserva aunque cambie la ejecución real.</span>
      </p>
      <RequestState loading={loading} error={error} />
      {!loading && !error && (
        <div
          className={
            'change-calendar ' +
            (mode === 'day' ? 'change-calendar-day' : '')
          }
          aria-label="Calendario de cambios"
        >
          <div
            className="change-calendar-weekdays"
            aria-label="Días de la semana"
          >
            {(mode === 'day' ? [weekday(day)] : weekdays).map((name) => (
              <span key={name}>{name}</span>
            ))}
          </div>
          {Array.from({ length: padding }, (_, i) => (
            <div
              className="change-calendar-placeholder"
              key={'empty' + i}
              aria-hidden="true"
            />
          ))}
          {days.map((date) => (
            <section key={date} className="change-calendar-cell">
              <div className="change-calendar-date-heading">
                <Can
                  permission="changes.create"
                  fallback={
                    <span
                      className="change-calendar-date text-xs font-semibold"
                      aria-current={date === today ? 'date' : undefined}
                    >
                      {date.slice(8)} / {date.slice(5, 7)}
                    </span>
                  }
                >
                  <Link
                    className="change-calendar-date text-xs font-semibold"
                    aria-label={weekday(date) + ', ' + date}
                    aria-current={date === today ? 'date' : undefined}
                    to={`/changes/new?date=${date}`}
                  >
                    {date.slice(8)} / {date.slice(5, 7)}
                  </Link>
                </Can>
                <span
                  className="change-calendar-mobile-weekday"
                  aria-hidden="true"
                >
                  {weekday(date)}
                </span>
              </div>
              <div className="mt-2 space-y-1.5">
                {items
                  .filter(
                    (row) =>
                      ticketynDateTimeValue(new Date(row.proposed_start)).slice(
                        0,
                        10
                      ) === date
                  )
                  .map((row) => (
                    <Link
                      key={row.id}
                      className={
                        'change-calendar-event change-status-' + row.status
                      }
                      to={`/changes/${row.id}`}
                    >
                      <span className="font-mono text-[10px] text-slate-300">
                        {ticketynDateTimeValue(
                          new Date(row.proposed_start)
                        ).slice(11, 16)}{' '}
                        —{' '}
                        {ticketynDateTimeValue(
                          new Date(row.proposed_end)
                        ).replace('T', ' ')}
                      </span>
                      <strong className="font-mono text-xs">
                        {row.reference}
                      </strong>
                      <span className="truncate">{row.title}</span>
                      <span className="font-mono text-[10px] opacity-90">
                        {changeStatuses[row.status]}
                      </span>
                    </Link>
                  ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </section>
  )
}

export function ChangeForm() {
  const access = usePermissions()
  const { id } = useParams(),
    navigate = useNavigate(),
    location = useLocation(),
    catalog = useChangeCatalogs()
  const [original, setOriginal] = useState<Change | null>(null),
    [loading, setLoading] = useState(Boolean(id)),
    [error, setError] = useState<string | null>(null),
    [saving, setSaving] = useState(false)
  const [draft, setDraft] = useState({
    title: '',
    description: '',
    change_type_id: '',
    sector_id: '',
    node_id: '',
    manager_id: '',
    support_ids: [] as number[],
    status: 'SCHEDULED' as ChangeStatus,
    proposed_start:
      (new URLSearchParams(location.search).get('date') ??
        ticketynDateTimeValue(new Date()).slice(0, 10)) + 'T08:00',
    proposed_end:
      (new URLSearchParams(location.search).get('date') ??
        ticketynDateTimeValue(new Date()).slice(0, 10)) + 'T09:00',
    actual_start: '',
    actual_end: '',
    completion_type_id: '',
    final_notes: '',
  })
  const editedDates = useRef(new Set<string>())
  const [links, setLinks] = useState<Change['internal_tickets']>([]),
    sending = useRef(false)

  useEffect(() => {
    if (!id) return
    const c = new AbortController()
    getJson<Change>(`/api/changes/${id}`, c.signal)
      .then((row) => {
        if (c.signal.aborted) return
        editedDates.current.clear()
        setOriginal(row)
        setLinks(row.internal_tickets)
        setDraft({
          title: row.title,
          description: row.description,
          change_type_id: row.change_type_id ? String(row.change_type_id) : '',
          sector_id: String(row.sector_id),
          node_id: row.node_id ? String(row.node_id) : '',
          manager_id: String(row.manager_id),
          support_ids: row.support.map((p) => p.id),
          status: row.status,
          proposed_start: ticketynDateTimeValue(new Date(row.proposed_start)),
          proposed_end: ticketynDateTimeValue(new Date(row.proposed_end)),
          actual_start: row.actual_start
            ? ticketynDateTimeValue(new Date(row.actual_start))
            : '',
          actual_end: row.actual_end
            ? ticketynDateTimeValue(new Date(row.actual_end))
            : '',
          completion_type_id: row.completion_type_id
            ? String(row.completion_type_id)
            : '',
          final_notes: row.final_notes ?? '',
        })
        setLoading(false)
      })
      .catch((f) => {
        if (!c.signal.aborted) {
          setError(failure(f))
          setLoading(false)
        }
      })
    return () => c.abort()
  }, [id])

  // Keep exact historical instants unless the user explicitly edits that field.
  function dateValue(
    key: 'proposed_start' | 'proposed_end' | 'actual_start' | 'actual_end'
  ) {
    if (original && !editedDates.current.has(key)) return original[key]
    return draft[key] ? ticketynDateTimeToIso(draft[key]) : null
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (sending.current) return
    sending.current = true
    setSaving(true)
    setError(null)
    try {
      const values = {
        ...draft,
        change_type_id: Number(draft.change_type_id),
        sector_id: Number(draft.sector_id),
        node_id: draft.node_id ? Number(draft.node_id) : null,
        manager_id: Number(draft.manager_id),
        completion_type_id: draft.completion_type_id
          ? Number(draft.completion_type_id)
          : null,
        proposed_start: dateValue('proposed_start'),
        proposed_end: dateValue('proposed_end'),
        actual_start: dateValue('actual_start'),
        actual_end: dateValue('actual_end'),
        final_notes: draft.final_notes || null,
        internal_ticket_ids: links.map((row) => row.id),
      }
      const row = await (id
        ? patchJson<Change>(`/api/changes/${id}`, values)
        : postJson<Change>('/api/changes', values))
      navigate(`/changes/${row.id}`)
    } catch (f) {
      setError(failure(f))
    } finally {
      sending.current = false
      setSaving(false)
    }
  }

  const c = catalog.catalogs,
    manager = c?.people.find((p) => String(p.id) === draft.manager_id)
  if (id && !original && !loading && error)
    return <RequestState error={error} />
  if (loading || !c)
    return (
      <RequestState
        loading={loading || !catalog.error}
        error={error ?? catalog.error}
        onRetry={catalog.retry}
      />
    )

  return (
    <>
      <PageHeading
        title={id ? 'Editar cambio' : 'Nuevo cambio'}
        description="Fechas y estados manuales. Los cambios históricos pueden registrarse directamente como Finalizados."
      />
      <form
        className="p-6 space-y-6 rounded-2xl bg-[#0b1426] border border-amber-500/20 shadow-xl"
        onSubmit={(e) => void submit(e)}
      >
        <fieldset disabled={saving} className="space-y-6">
          <section>
            <div className="flex items-center gap-2 border-b border-amber-500/15 pb-2.5 mb-4">
              <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs" aria-hidden="true">
                <Tag size={13} />
              </span>
              <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">Información general</h2>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField id="change-title" label="Título" required>
                <input
                  id="change-title"
                  readOnly={!access.can('changes.edit') && Boolean(id)}
                  className="form-input"
                  required
                  maxLength={500}
                  value={draft.title}
                  onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                />
              </FormField>
              <FormField id="form-change-status" label="Estado" required>
                <select
                  disabled={!access.can('changes.execute')}
                  id="form-change-status"
                  className="form-input"
                  value={draft.status}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      status: e.target.value as ChangeStatus,
                    })
                  }
                >
                  {Object.entries(changeStatuses).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </FormField>

              {(
                [
                  ['change_type_id', 'Tipo de cambio', c.changeTypes, true],
                  ['sector_id', 'Sector', c.sectors, true],
                  ['node_id', 'Nodo', c.nodes, false],
                  ['manager_id', 'Encargado de ejecución', c.people, true],
                  [
                    'completion_type_id',
                    'Tipo de finalización',
                    c.types,
                    draft.status === 'FINISHED',
                  ],
                ] as const
              ).map(([key, label, rows, required]) => (
                <FormField key={key} id={'form-' + key} label={label} required={required}>
                  <select
                    disabled={
                      key === 'completion_type_id'
                        ? !access.can('changes.execute')
                        : Boolean(id) && !access.can('changes.edit')
                    }
                    id={'form-' + key}
                    className="form-input"
                    value={draft[key]}
                    required={required}
                    onChange={(e) =>
                      setDraft({
                        ...draft,
                        [key]: e.target.value,
                        ...(key === 'manager_id'
                          ? {
                              support_ids: draft.support_ids.filter(
                                (pid) => String(pid) !== e.target.value
                              ),
                            }
                          : {}),
                      })
                    }
                  >
                    <option value="">Sin asignar</option>
                    {rows
                      .filter(
                        (p) =>
                          (key !== 'manager_id' ||
                            operationalChoice(
                              p,
                              original ? [original.manager_id] : []
                            )) &&
                          (p.active || String(p.id) === draft[key])
                      )
                      .map((p) => (
                        <option
                          key={p.id}
                          value={p.id}
                          disabled={!p.active && String(p.id) !== draft[key]}
                        >
                          {p.name}
                          {p.active ? '' : ' (Inactivo)'}
                        </option>
                      ))}
                  </select>
                </FormField>
              ))}

              <FormField id="change-department" label="Departamento">
                <input
                  id="change-department"
                  readOnly
                  className="form-input"
                  value={
                    original && String(original.manager_id) === draft.manager_id
                      ? original.department_name
                      : manager?.department?.name ??
                        'El encargado debe tener departamento asignado'
                  }
                />
              </FormField>

              <FormField
                id="change-support"
                label="Personal de apoyo"
                describedBy="change-support-help"
              >
                <SearchableMultiSelect
                  id="change-support"
                  label="Personal de apoyo"
                  value={draft.support_ids.map(String)}
                  disabled={saving || (Boolean(id) && !access.can('changes.edit'))}
                  placeholder="Sin personal de apoyo"
                  options={c.people
                    .filter(
                      (p) =>
                        String(p.id) !== draft.manager_id &&
                        operationalChoice(
                          p,
                          original?.support.map((s) => s.id) ?? []
                        ) &&
                        (p.active || draft.support_ids.includes(p.id))
                    )
                    .map((p) => ({
                      value: String(p.id),
                      label: p.name,
                      disabled: !p.active,
                    }))}
                  onChange={(values) =>
                    setDraft({ ...draft, support_ids: values.map(Number) })
                  }
                />
                <p id="change-support-help" className="mt-1 text-xs text-muted font-mono">
                  Opcional. Busca y agrega personas; usa la X para quitarlas.
                </p>
              </FormField>

              <div className="sm:col-span-2">
                <FormField id="change-description" label="Descripción" required>
                  <textarea
                    id="change-description"
                    readOnly={!access.can('changes.edit') && Boolean(id)}
                    className="form-input min-h-28"
                    required
                    maxLength={50000}
                    value={draft.description}
                    onChange={(e) =>
                      setDraft({ ...draft, description: e.target.value })
                    }
                  />
                </FormField>
              </div>
            </div>
          </section>

          <section>
            <div className="flex items-center gap-2 border-b border-amber-500/15 pb-2.5 mb-4">
              <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs" aria-hidden="true">
                <Clock size={13} />
              </span>
              <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">Planificación y ejecución real</h2>
            </div>
            <p className="mb-3 text-xs text-muted font-mono">
              Fechas en {ticketynTimezone}. La creación del registro es independiente de
              estas fechas.
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              {(
                [
                  ['proposed_start', 'Inicio propuesto', true],
                  ['proposed_end', 'Fin propuesto', true],
                  ['actual_start', 'Inicio real', draft.status !== 'SCHEDULED'],
                  ['actual_end', 'Fin real', draft.status === 'FINISHED'],
                ] as const
              ).map(([key, label, required]) => (
                <FormField
                  key={key}
                  id={'form-' + key}
                  label={label}
                  required={required}
                >
                  <input
                    id={'form-' + key}
                    type="datetime-local"
                    disabled={
                      key === 'actual_start' || key === 'actual_end'
                        ? !access.can('changes.execute')
                        : Boolean(id) && !access.can('changes.edit')
                    }
                    step="60"
                    className="form-input"
                    required={required}
                    value={draft[key]}
                    onChange={(e) => {
                      editedDates.current.add(key)
                      setDraft({
                        ...draft,
                        [key]: e.target.value.slice(0, 16),
                      })
                    }}
                  />
                </FormField>
              ))}
            </div>
          </section>

          <FormField
            id="change-final-notes"
            label="Notas finales"
            required={draft.status === 'FINISHED'}
          >
            <textarea
              id="change-final-notes"
              className="form-input min-h-24"
              required={draft.status === 'FINISHED'}
              maxLength={50000}
              value={draft.final_notes}
              onChange={(e) =>
                setDraft({ ...draft, final_notes: e.target.value })
              }
            />
          </FormField>

          <section>
            <div className="flex items-center gap-2 border-b border-amber-500/15 pb-2.5 mb-3">
              <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs" aria-hidden="true">
                <Layers size={13} />
              </span>
              <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">Tickets internos relacionados</h2>
            </div>
            <ChangeTicketLinks
              items={links}
              onChange={setLinks}
              disabled={saving}
            />
          </section>
        </fieldset>

        {error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}

        <div className="flex flex-wrap justify-end gap-3 pt-2">
          <Link
            className="button-secondary rounded-full shadow-xs"
            to={id ? `/changes/${id}` : '/changes'}
          >
            Cancelar
          </Link>
          <button
            className="button-primary button-primary--amber rounded-full shadow-sm"
            disabled={saving}
          >
            {saving ? 'Guardando...' : 'Guardar cambio'}
          </button>
        </div>
      </form>
    </>
  )
}

export function ChangeDetail() {
  const { id } = useParams(),
    catalog = useChangeCatalogs(),
    [item, setItem] = useState<Change | null>(null),
    [error, setError] = useState<string | null>(null),
    [retry, setRetry] = useState(0)
  const [updates, setUpdates] = useState<{
      total: number
      items: ChangeUpdate[]
    } | null>(null),
    [offset, setOffset] = useState(0),
    [busy, setBusy] = useState(false),
    pending = useRef(false)
  const [open, setOpen] = useState(false),
    [update, setUpdate] = useState({
      content: '',
      responsible_id: '',
      occurred_at: ticketynDateTimeValue(new Date()),
    }),
    [audit, setAudit] = useState<
      {
        id: number
        occurred_at: string
        changes: Record<string, { before: unknown; after: unknown }>
      }[]
    >([]),
    [auditOffset, setAuditOffset] = useState(0)

  useEffect(() => {
    const c = new AbortController()
    Promise.all([
      getJson<Change>(`/api/changes/${id}`, c.signal),
      getJson<{ total: number; items: ChangeUpdate[] }>(
        `/api/changes/${id}/updates?limit=50&offset=${offset}`,
        c.signal
      ),
    ])
      .then(([row, history]) => {
        if (!c.signal.aborted) {
          setItem(row)
          setUpdates(history)
          setError(null)
        }
      })
      .catch((f) => {
        if (!c.signal.aborted) setError(failure(f))
      })
    return () => c.abort()
  }, [id, retry, offset])

  async function execute(work: () => Promise<unknown>) {
    if (pending.current) return
    pending.current = true
    setBusy(true)
    setError(null)
    try {
      await work()
      setRetry(retry + 1)
    } catch (f) {
      setError(failure(f))
    } finally {
      pending.current = false
      setBusy(false)
    }
  }

  if (!item)
    return (
      <RequestState
        loading={!error}
        error={error}
        onRetry={() => setRetry(retry + 1)}
      />
    )
  const row = item

  return (
    <>
      <PageHeading
        title={row.reference}
        description={row.title}
        badge={
          <span
            className={
              'change-status rounded-full px-2.5 py-0.5 font-mono text-xs change-status-' +
              row.status
            }
          >
            {changeStatuses[row.status]}
          </span>
        }
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Can permission="changes.export">
              <button
                className="button-secondary rounded-full shadow-xs"
                disabled={busy}
                onClick={() =>
                  void execute(() =>
                    downloadFile(
                      `/api/changes/${id}/reports/pdf?${new URLSearchParams({
                        timezone: ticketynTimezone,
                      })}`,
                      `Cambio_${row.reference}.pdf`
                    )
                  )
                }
              >
                <FileText size={14} aria-hidden="true" />
                Exportar PDF
              </button>
            </Can>
            <Link className="button-secondary rounded-full shadow-xs" to="/changes">
              Volver a cambios
            </Link>
            <Can anyOf={['changes.edit', 'changes.execute', 'changes.link']}>
              <Link
                className="button-primary button-primary--amber rounded-full shadow-sm"
                to={`/changes/${id}/edit`}
              >
                Editar cambio
              </Link>
            </Can>
          </div>
        }
      />

      {error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}

      <div className="grid gap-5 lg:grid-cols-2">
        {/* Columna 1: Información general */}
        <section
          aria-labelledby="change-info-heading"
          className="p-5 rounded-2xl bg-[#0b1426] border border-amber-500/20 shadow-xl space-y-4"
        >
          <div className="flex items-center justify-between border-b border-amber-500/15 pb-2.5">
            <div className="flex items-center gap-2">
              <span
                className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs"
                aria-hidden="true"
              >
                <Tag size={13} />
              </span>
              <h2
                id="change-info-heading"
                className="text-xs font-bold font-mono text-white uppercase tracking-wider"
              >
                Información general
              </h2>
            </div>
          </div>

          <dl className="grid gap-x-6 gap-y-3.5 sm:grid-cols-2 text-xs">
            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Tipo de cambio
              </dt>
              <dd className="mt-1 text-sm font-semibold text-white">
                {row.change_type?.name ?? 'Sin clasificar'}
              </dd>
            </div>
            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Estado
              </dt>
              <dd className="mt-1 text-sm font-semibold text-white">
                {changeStatuses[row.status]}
              </dd>
            </div>
            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Sector
              </dt>
              <dd className="mt-1 text-sm text-slate-200">
                {row.sector.name}
              </dd>
            </div>
            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Nodo
              </dt>
              <dd className="mt-1 text-sm text-slate-200 font-medium">
                {row.node?.name ?? 'Sin asignar'}
              </dd>
            </div>
            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Encargado
              </dt>
              <dd className="mt-1 text-sm text-slate-200 font-medium font-mono">
                {row.manager_name}
              </dd>
            </div>
            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Departamento
              </dt>
              <dd className="mt-1 text-sm text-slate-200">
                {row.department_name}
              </dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Personal de apoyo
              </dt>
              <dd className="mt-1 text-sm text-slate-200 font-medium">
                {row.support.map((p) => p.name).join(', ') || 'Sin apoyo'}
              </dd>
            </div>
          </dl>

          {/* Bloque Descripción */}
          <div className="p-3.5 rounded-xl bg-[#070d1a] border border-slate-800">
            <div className="flex items-center gap-1.5 mb-1.5">
              <FileText size={12} className="text-amber-400/80" aria-hidden="true" />
              <h3 className="text-[11px] font-mono text-slate-400 uppercase tracking-wider font-semibold">
                Descripción
              </h3>
            </div>
            <p className="whitespace-pre-wrap [overflow-wrap:anywhere] text-sm text-slate-200 leading-relaxed">
              {row.description}
            </p>
          </div>

          {/* Metadatos discretos de auditoría */}
          <div className="pt-3 border-t border-slate-800/80 text-[11px] font-mono text-slate-500">
            <dl className="space-y-1">
              <div className="flex justify-between items-baseline">
                <dt className="text-slate-400">Fecha de creación</dt>
                <dd className="text-slate-300 tabular-nums">{formatDate(row.created_at)}</dd>
              </div>
              <div className="flex justify-between items-baseline">
                <dt className="text-slate-400">Última actualización</dt>
                <dd className="text-slate-300 tabular-nums">{formatDate(row.updated_at)}</dd>
              </div>
            </dl>
          </div>
        </section>

        {/* Columna 2: Planificación y ejecución */}
        <section
          aria-labelledby="change-planning-heading"
          className="p-5 rounded-2xl bg-[#0b1426] border border-amber-500/20 shadow-xl space-y-4"
        >
          <div className="flex items-center justify-between border-b border-amber-500/15 pb-2.5">
            <div className="flex items-center gap-2">
              <span
                className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs"
                aria-hidden="true"
              >
                <Clock size={13} />
              </span>
              <h2
                id="change-planning-heading"
                className="text-xs font-bold font-mono text-white uppercase tracking-wider"
              >
                Planificación y ejecución
              </h2>
            </div>
          </div>

          <dl className="grid gap-x-6 gap-y-3.5 sm:grid-cols-2 text-xs">
            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Inicio propuesto
              </dt>
              <dd className="mt-1 font-mono text-sm text-slate-200 tabular-nums">
                {formatDate(row.proposed_start)}
              </dd>
            </div>
            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Fin propuesto
              </dt>
              <dd className="mt-1 font-mono text-sm text-slate-200 tabular-nums">
                {formatDate(row.proposed_end)}
              </dd>
            </div>
            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Inicio real
              </dt>
              <dd className="mt-1 font-mono text-sm text-slate-300 tabular-nums">
                {row.actual_start ? formatDate(row.actual_start) : 'Sin registrar'}
              </dd>
            </div>
            <div>
              <dt className="font-mono text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Fin real
              </dt>
              <dd className="mt-1 font-mono text-sm text-slate-300 tabular-nums">
                {row.actual_end ? formatDate(row.actual_end) : 'Sin registrar'}
              </dd>
            </div>
          </dl>

          {/* Bloque de duraciones operativas */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="p-3 rounded-xl bg-[#070d1a] border border-slate-800">
              <dt className="font-mono text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                Duración planificada
              </dt>
              <dd className="mt-1 font-mono text-lg font-bold text-amber-300 tracking-tight">
                {formatDuration(row.planned_seconds)}
              </dd>
            </div>
            <div className="p-3 rounded-xl bg-[#070d1a] border border-slate-800">
              <dt className="font-mono text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                Duración real
              </dt>
              <dd className="mt-1 font-mono text-lg font-bold text-slate-200 tracking-tight">
                {row.actual_seconds !== null ? formatDuration(row.actual_seconds) : 'Sin registrar'}
              </dd>
            </div>
          </div>

          {/* Bloque de Resultados y Eficiencia */}
          <div className="p-3.5 rounded-xl bg-[#070d1a] border border-slate-800 space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-[11px] font-mono text-slate-400 uppercase tracking-wider font-semibold">
                Resultados
              </h3>
              <span className="text-xs font-semibold text-slate-200">
                {row.completion_name ?? 'Sin tipo de finalización'}
              </span>
            </div>
            <ChangeEfficiency item={row} />
            {row.saved_seconds !== null && (
              <p className="text-xs font-mono text-slate-300">
                Tiempo ahorrado: <strong className="text-emerald-400">{formatDuration(row.saved_seconds)}</strong> · Tiempo excedido:{' '}
                <strong className="text-amber-400">{formatDuration(row.exceeded_seconds)}</strong>
              </p>
            )}
            <div className="border-t border-slate-800 pt-2.5 mt-2">
              <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block mb-1">
                Notas finales
              </span>
              <p className="whitespace-pre-wrap [overflow-wrap:anywhere] text-sm text-slate-300 leading-relaxed">
                {row.final_notes ?? 'Sin notas finales.'}
              </p>
            </div>
          </div>
        </section>
      </div>

      <section className="p-5 rounded-2xl bg-[#0b1426] border border-amber-500/20 shadow-xl mt-5 space-y-3">
        <div className="flex items-center gap-2 border-b border-amber-500/15 pb-2.5">
          <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs" aria-hidden="true">
            <Layers size={13} />
          </span>
          <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
            Tickets internos relacionados
          </h2>
        </div>
        <ChangeTicketLinks
          items={row.internal_tickets}
          disabled={busy}
          onChange={(items) =>
            void execute(() =>
              patchJson(`/api/changes/${id}`, {
                internal_ticket_ids: items.map((x) => x.id),
              })
            )
          }
        />
      </section>

      <section className="p-5 rounded-2xl bg-[#0b1426] border border-amber-500/20 shadow-xl mt-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-amber-500/15 pb-2.5">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs" aria-hidden="true">
              <MessageSquare size={13} />
            </span>
            <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
              Seguimiento
            </h2>
          </div>
          <Can permission="changes.followup">
            <button
              className="button-primary button-primary--amber rounded-full shadow-sm text-xs"
              onClick={() => setOpen(!open)}
            >
              Nueva intervención
            </button>
          </Can>
        </div>

        {open && (
          <Can permission="changes.followup">
            <form
              className="p-4 rounded-xl bg-[#070d1a] border border-amber-500/20 space-y-4"
              onSubmit={(e) => {
                e.preventDefault()
                void execute(async () => {
                  await postJson(`/api/changes/${id}/updates`, {
                    ...update,
                    responsible_id: Number(update.responsible_id),
                    occurred_at: ticketynDateTimeToIso(update.occurred_at),
                  })
                  setOpen(false)
                  setUpdate({ ...update, content: '' })
                })
              }}
            >
              <div className="grid gap-3 sm:grid-cols-2">
                <FormField id="update-person" label="Responsable" required>
                  <select
                    id="update-person"
                    className="form-input"
                    required
                    value={update.responsible_id}
                    onChange={(e) =>
                      setUpdate({ ...update, responsible_id: e.target.value })
                    }
                  >
                    <option value="">Selecciona responsable</option>
                    {catalog.catalogs?.people
                      .filter((p) => operationalChoice(p))
                      .map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                  </select>
                </FormField>
                <FormField id="update-time" label="Fecha y hora" required>
                  <input
                    id="update-time"
                    type="datetime-local"
                    step="1"
                    required
                    className="form-input font-mono"
                    value={update.occurred_at}
                    onChange={(e) =>
                      setUpdate({ ...update, occurred_at: e.target.value })
                    }
                  />
                </FormField>
              </div>
              <FormField
                id="update-content"
                label="Descripción de la actividad"
                required
              >
                <textarea
                  id="update-content"
                  className="form-input min-h-24"
                  required
                  value={update.content}
                  onChange={(e) =>
                    setUpdate({ ...update, content: e.target.value })
                  }
                />
              </FormField>
              <div className="flex gap-2">
                <button
                  className="button-primary button-primary--amber rounded-full shadow-sm"
                  disabled={busy}
                >
                  Guardar intervención
                </button>
                <button
                  type="button"
                  className="button-secondary rounded-full"
                  onClick={() => setOpen(false)}
                >
                  Cancelar
                </button>
              </div>
            </form>
          </Can>
        )}

        <RequestState
          compact
          error={catalog.error}
          onRetry={catalog.retry}
        />

        {updates?.items.length === 0 ? (
          <p className="text-sm text-slate-400">Sin intervenciones registradas.</p>
        ) : (
          <ol className="space-y-4">
            {updates?.items.map((entry) => (
              <li
                key={entry.id}
                className="border-l-2 border-amber-500/60 pl-3.5 py-1"
              >
                <p className="text-xs font-mono text-slate-400">
                  {formatDate(entry.occurred_at)} ·{' '}
                  <span className="text-slate-200 font-semibold">
                    {entry.responsible_name}
                  </span>
                </p>
                <p className="mt-1 whitespace-pre-wrap [overflow-wrap:anywhere] text-sm text-slate-100 leading-relaxed">
                  {entry.content}
                </p>
              </li>
            ))}
          </ol>
        )}

        <PaginationBar
          page={Math.floor(offset / 50) + 1}
          info={
            <span className="text-xs font-mono text-slate-400">
              {updates?.total ?? 0} intervenciones
            </span>
          }
          previousDisabled={offset === 0}
          nextDisabled={!updates || offset + 50 >= updates.total}
          onPrevious={() => setOffset(Math.max(0, offset - 50))}
          onNext={() => setOffset(offset + 50)}
        />
      </section>

      <section className="p-5 rounded-2xl bg-[#0b1426] border border-amber-500/20 shadow-xl mt-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-amber-500/15 pb-2.5">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs" aria-hidden="true">
              <History size={13} />
            </span>
            <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
              Historial de correcciones
            </h2>
          </div>
          <button
            className="button-secondary rounded-full text-xs shadow-xs"
            disabled={busy}
            onClick={() =>
              void execute(async () => {
                setAudit(
                  await getJson(
                    `/api/changes/${id}/audit?limit=50&offset=${auditOffset}`
                  )
                )
              })
            }
          >
            Consultar historial
          </button>
        </div>
        {audit.map((entry) => (
          <details className="p-3.5 rounded-xl bg-[#070d1a] border border-slate-800" key={entry.id}>
            <summary className="font-mono text-xs font-semibold text-slate-300 cursor-pointer">
              {formatDate(entry.occurred_at)}
            </summary>
            <ul className="mt-2 space-y-1.5 text-xs text-slate-300 pl-3 border-l border-slate-700">
              {Object.entries(entry.changes).map(([key, value]) => (
                <li key={key}>
                  <strong className="text-slate-200">
                    {auditLabels[key] ?? 'Actualización'}
                  </strong>
                  : {auditText(value.before)} → {auditText(value.after)}
                </li>
              ))}
            </ul>
          </details>
        ))}
        <div className="flex gap-2">
          <button
            className="button-secondary rounded-full"
            disabled={auditOffset === 0}
            onClick={() => {
              setAuditOffset(Math.max(0, auditOffset - 50))
              setAudit([])
            }}
          >
            Historial anterior
          </button>
          <button
            className="button-secondary rounded-full"
            disabled={audit.length < 50}
            onClick={() => {
              setAuditOffset(auditOffset + 50)
              setAudit([])
            }}
          >
            Más historial
          </button>
        </div>
      </section>
    </>
  )
}
