import { Can, usePermissions } from '../auth/permissions'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import {
  listSectors,
  listNodes,
  listResponsibles,
  listDepartments,
  listChangeTypes,
  listChangeCompletionTypes,
} from '../api'
import { getJson } from '../api/client'
import { FormField } from './FormField'
import { FilterBar, FilterPanelGroup, FilterSegment } from './FilterBar'
import type { FilterChipItem } from './FilterChips'
import { RequestState } from './RequestState'
import { InternalTicketSelect } from './InternalTicketSelect'
import type { Change, ChangeCatalogs } from '../types/change'
import { formatDate, formatDuration } from '../lib/format'
import { ticketynDateTimeToIso } from '../lib/datetime'

export const changeStatuses = {
  SCHEDULED: 'Agendado',
  EXECUTING: 'En ejecución',
  FINISHED: 'Finalizado',
}
export const changeFilterKeys = [
  'search',
  'status',
  'from',
  'to',
  'manager_id',
  'support_id',
  'involved_id',
  'department_id',
  'sector_id',
  'node_id',
  'completion_type_id',
  'change_type_id',
  'sort',
  'direction',
]

export function changeQuery(params: URLSearchParams) {
  if (Boolean(params.get('from')) !== Boolean(params.get('to')))
    throw new Error('Completa ambos límites del período.')
  if (
    params.get('from') &&
    params.get('to') &&
    params.get('from')! > params.get('to')!
  )
    throw new Error('El fin debe ser igual o posterior al inicio.')
  const query = new URLSearchParams()
  for (const key of changeFilterKeys) {
    const value = params.get(key)
    if (!value) continue
    query.set(
      key,
      key === 'from' || key === 'to'
        ? ticketynDateTimeToIso(value + 'T00:00')
        : value
    )
  }
  // The UI's last day is inclusive; backend receives an exclusive local midnight.
  if (params.get('to')) {
    const day = new Date(params.get('to') + 'T12:00:00Z')
    day.setUTCDate(day.getUTCDate() + 1)
    query.set(
      'to',
      ticketynDateTimeToIso(day.toISOString().slice(0, 10) + 'T00:00')
    )
  }
  return query
}

export function useChangeCatalogs() {
  const [catalogs, setCatalogs] = useState<ChangeCatalogs | null>(null),
    [error, setError] = useState<string | null>(null),
    [retry, setRetry] = useState(0)
  useEffect(() => {
    const c = new AbortController()
    setError(null)
    Promise.all([
      listSectors(c.signal, true),
      listNodes(c.signal, true),
      listResponsibles(c.signal, true),
      listDepartments(c.signal, true),
      listChangeCompletionTypes(c.signal, true),
      listChangeTypes(c.signal, true),
    ])
      .then(([sectors, nodes, people, departments, types, changeTypes]) => {
        if (!c.signal.aborted)
          setCatalogs({ sectors, nodes, people, departments, types, changeTypes })
      })
      .catch((f) => {
        if (!c.signal.aborted)
          setError(
            f instanceof Error ? f.message : 'No se pudieron cargar los catálogos.'
          )
      })
    return () => c.abort()
  }, [retry])
  return { catalogs, error, retry: () => setRetry(retry + 1) }
}

export function ChangeFilters({
  params,
  change,
  clear,
  catalogs,
}: {
  params: URLSearchParams
  change: (values: Record<string, string>) => void
  clear: () => void
  catalogs: ChangeCatalogs | null
}) {
  const [search, setSearch] = useState(params.get('search') ?? '')
  useEffect(() => setSearch(params.get('search') ?? ''), [params])

  const fields = [
    ['manager_id', 'Encargado', catalogs?.people],
    ['support_id', 'Personal de apoyo', catalogs?.people],
    ['involved_id', 'Personal involucrado', catalogs?.people],
    ['department_id', 'Departamento', catalogs?.departments],
    ['sector_id', 'Sector', catalogs?.sectors],
    ['node_id', 'Nodo', catalogs?.nodes],
    ['completion_type_id', 'Tipo de finalización', catalogs?.types],
    ['change_type_id', 'Tipo de cambio', catalogs?.changeTypes],
  ] as const
  type FieldKey = (typeof fields)[number][0]
  const select = (key: FieldKey) => {
    const [, label, rows] = fields.find(([k]) => k === key)!
    return (
      <FormField key={key} id={'change-' + key} label={label}>
        <select id={'change-' + key} className="form-input" value={params.get(key) ?? ''} onChange={(e) => change({ [key]: e.target.value })}>
          <option value="">Todos</option>
          {rows?.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name}
              {row.active ? '' : ' (Inactivo)'}
            </option>
          ))}
        </select>
      </FormField>
    )
  }
  // Un campo ocupa una sola ranura: rápidos en la barra, el resto en el panel.
  const quickKeys: FieldKey[] = ['manager_id', 'change_type_id']
  const panelGroups: [string, FieldKey[]][] = [
    ['Clasificación', ['department_id', 'sector_id', 'node_id', 'completion_type_id']],
    ['Personas', ['support_id', 'involved_id']],
  ]

  // Cada chip quita solo su condición; el período exige ambos límites, así que se quita completo.
  const activeChips: FilterChipItem[] = []
  const status = params.get('status')
  if (params.get('search')) activeChips.push({ label: 'Búsqueda', value: `"${params.get('search')}"`, onRemove: () => { setSearch(''); change({ search: '' }) } })
  if (status) activeChips.push({ label: 'Estado', value: changeStatuses[status as keyof typeof changeStatuses] ?? status, onRemove: () => change({ status: '' }) })
  if (params.get('from') || params.get('to')) activeChips.push({ label: 'Período', value: `${params.get('from') || '—'} a ${params.get('to') || '—'}`, onRemove: () => change({ from: '', to: '' }) })
  for (const [key, label, rows] of fields) {
    const value = params.get(key)
    if (value) activeChips.push({ label, value: rows?.find((row) => String(row.id) === value)?.name ?? value, onRemove: () => change({ [key]: '' }) })
  }
  const advancedKeys = [...panelGroups.flatMap(([, keys]) => keys), 'from', 'to']
  const advancedCount = advancedKeys.filter((key) => params.get(key)).length

  return (
    <FilterBar
      label="Filtros de cambios"
      theme="cyan"
      chips={activeChips}
      panelCount={advancedCount}
      onClear={clear}
      search={
        <form className="flex items-end gap-2.5" onSubmit={(e) => { e.preventDefault(); change({ search }) }}>
          <div className="flex-1 min-w-0">
            <FormField id="change-search" label="Buscar">
              <input id="change-search" className="form-input" placeholder="Correlativo o título" value={search} onChange={(e) => setSearch(e.target.value)} />
            </FormField>
          </div>
          <button type="submit" className="button-secondary rounded-full shrink-0">Buscar</button>
        </form>
      }
      quick={quickKeys.map((key) => <div key={key} className="filter-bar-quick">{select(key)}</div>)}
      primary={
        <FilterSegment
          label="Estado"
          options={[['', 'Todos'], ...Object.entries(changeStatuses)]}
          value={params.get('status') ?? ''}
          onChange={(value) => change({ status: value })}
        />
      }
      panel={
        <>
          {panelGroups.map(([title, keys]) => <FilterPanelGroup key={title} title={title}>{keys.map(select)}</FilterPanelGroup>)}
          <FilterPanelGroup title="Inicio propuesto">
            {(['from', 'to'] as const).map((key) => (
              <FormField key={key} id={'change-' + key} label={key === 'from' ? 'Desde' : 'Hasta'}>
                <input id={'change-' + key} type="date" className="form-input" value={params.get(key) ?? ''} onChange={(e) => change({ [key]: e.target.value })} />
              </FormField>
            ))}
          </FilterPanelGroup>
          <FilterPanelGroup title="Orden">
            <FormField id="change-sort" label="Ordenar por">
              <select id="change-sort" className="form-input" value={params.get('sort') ?? 'proposed_start'} onChange={(e) => change({ sort: e.target.value })}>
                {[['proposed_start', 'Inicio propuesto'], ['reference', 'Correlativo'], ['created_at', 'Creación'], ['status', 'Estado'], ['title', 'Título']].map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </FormField>
            <FormField id="change-direction" label="Dirección">
              <select id="change-direction" className="form-input" value={params.get('direction') ?? 'desc'} onChange={(e) => change({ direction: e.target.value })}>
                <option value="desc">Descendente</option>
                <option value="asc">Ascendente</option>
              </select>
            </FormField>
          </FilterPanelGroup>
        </>
      }
    />
  )
}

export function ChangeEfficiency({ item }: { item: Change }) {
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-xs">
        {item.efficiency_label}
        {item.variation_percent !== null
          ? ` · ${Math.abs(item.variation_percent)}%`
          : ''}
      </span>
      {item.late_start && (
        <span className="chip chip-warning rounded-full font-mono text-[10px]">
          Inicio tardío
        </span>
      )}
    </div>
  )
}

export function ChangeTable({ rows }: { rows: Change[] }) {
  return (
    <div className="table-surface table-surface--cyan overflow-x-auto rounded-2xl">
      <table className="operation-table" aria-label="Control de cambios">
        <thead>
          <tr>
            {[
              'Correlativo',
              'Título',
              'Tipo de cambio',
              'Sector / Nodo',
              'Encargado',
              'Personal de apoyo',
              'Inicio agendado',
              'Duración planificada',
              'Estado',
              'Tipo de finalización',
              'Eficiencia',
            ].map((label) => (
              <th key={label}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td>
                <Can
                  permission="changes.view"
                  fallback={
                    <span className="font-mono text-cyan-400 font-semibold">
                      {row.reference}
                    </span>
                  }
                >
                  <Link
                    className="text-cyan-400 hover:text-cyan-300 font-mono font-semibold"
                    to={`/changes/${row.id}`}
                  >
                    {row.reference}
                  </Link>
                </Can>
              </td>
              <td className="font-medium text-slate-100">{row.title}</td>
              <td>
                <span className="font-mono text-xs text-slate-300">
                  {row.change_type?.name ?? 'Sin clasificar'}
                </span>
              </td>
              <td className="text-slate-300">
                {row.sector.name}
                {row.node && ` / ${row.node.name}`}
              </td>
              <td className="text-slate-200">{row.manager_name}</td>
              <td>
                {row.support.length ? (
                  <details className="cursor-pointer text-xs">
                    <summary className="text-slate-300 hover:text-white font-medium">
                      {row.support.length} participantes
                    </summary>
                    <div className="mt-1 space-y-0.5 pl-2 border-l border-slate-700">
                      {row.support.map((p) => (
                        <div key={p.id} className="text-slate-400">
                          {p.name}
                        </div>
                      ))}
                    </div>
                  </details>
                ) : (
                  <span className="text-xs text-muted">Sin apoyo</span>
                )}
              </td>
              <td className="font-mono text-xs text-slate-300">
                {formatDate(row.proposed_start)}
              </td>
              <td className="font-mono text-xs text-slate-300">
                {formatDuration(row.planned_seconds)}
              </td>
              <td>
                <span
                  className={
                    'change-status rounded-full px-2.5 py-0.5 font-mono text-xs change-status-' +
                    row.status
                  }
                >
                  {changeStatuses[row.status]}
                </span>
              </td>
              <td className="font-mono text-xs text-slate-300">
                {row.completion_name ?? '—'}
              </td>
              <td>
                <ChangeEfficiency item={row} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ChangeTicketLinks({
  items,
  onChange,
  disabled,
}: {
  items: Change['internal_tickets']
  onChange: (items: Change['internal_tickets']) => void
  disabled?: boolean
}) {
  const access = usePermissions()
  const [open, setOpen] = useState(false),
    [selected, setSelected] = useState(''),
    [error, setError] = useState<string | null>(null),
    [loading, setLoading] = useState(false)
  async function add() {
    if (!selected || loading) return
    setLoading(true)
    setError(null)
    try {
      const row = await getJson<{ id: number; reference: string; title: string }>(
        `/api/internal-tickets/${selected}`
      )
      if (!items.some((item) => item.id === row.id))
        onChange([...items, row])
      setSelected('')
      setOpen(false)
    } catch (f) {
      setError(f instanceof Error ? f.message : 'No se pudo vincular.')
    } finally {
      setLoading(false)
    }
  }
  return (
    <div>
      {items.length > 0 && (
        <ul className="mb-3 space-y-2">
          {items.map((row) => (
            <li key={row.id} className="flex flex-wrap items-center gap-3">
              <Can
                permission="internal_tickets.view"
                fallback={
                  <span className="font-mono text-xs">
                    {row.reference} — {row.title}
                  </span>
                }
              >
                <Link
                  className="font-mono text-xs text-purple-400 hover:text-purple-300 font-semibold"
                  to={`/internal-tickets/${row.id}`}
                >
                  {row.reference} — {row.title}
                </Link>
              </Can>
              <Can permission="changes.link">
                <button
                  type="button"
                  disabled={disabled}
                  className="button-ghost text-xs text-red-400 hover:text-red-300 rounded-full"
                  onClick={() => onChange(items.filter((x) => x.id !== row.id))}
                >
                  Desvincular {row.reference}
                </button>
              </Can>
            </li>
          ))}
        </ul>
      )}
      <Can permission="changes.link">
        <button
          type="button"
          disabled={disabled}
          className="button-secondary rounded-full"
          onClick={() => setOpen(!open)}
        >
          Vincular ticket interno
        </button>
      </Can>
      {open && access.can('changes.link') && (
        <div className="mt-3 p-3 rounded-xl bg-slate-900/60 border border-slate-800">
          <InternalTicketSelect
            value={selected}
            disabled={disabled || loading}
            onChange={setSelected}
          />
          <button
            type="button"
            className="button-secondary rounded-full mt-2"
            disabled={!selected || disabled || loading}
            onClick={() => void add()}
          >
            Agregar vínculo
          </button>
        </div>
      )}
      <RequestState compact error={error} />
    </div>
  )
}
