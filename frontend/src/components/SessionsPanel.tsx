import { useEffect, useRef, useState } from 'react'
import { getJson, postJson } from '../api/client'
import type { ActiveSession } from '../api/security'
import { useAuth } from '../auth/context'
import { formatDate } from '../lib/format'
import { RequestState } from './RequestState'
import { FeedbackMessage } from './FeedbackMessage'
import { FilterHeading } from './FilterHeading'
import { FilterChips } from './FilterChips'
import { FormField } from './FormField'
import { Info, MonitorSmartphone, RefreshCw } from 'lucide-react'

function device(agent: string) {
  const browser = /Edg\//.test(agent) ? 'Edge' : /Firefox\//.test(agent) ? 'Firefox' : /Chrome\//.test(agent) ? 'Chrome' : /Safari\//.test(agent) ? 'Safari' : 'Navegador no identificado'
  const os = /Android/.test(agent) ? 'Android' : /iPhone|iPad/.test(agent) ? 'iOS' : /Windows/.test(agent) ? 'Windows' : /Macintosh/.test(agent) ? 'macOS' : /Linux/.test(agent) ? 'Linux' : 'Sistema no identificado'
  return `${browser} · ${os}`
}

export interface SessionsStats {
  total: number
  active5m: number
}

export function SessionsPanel({
  administrative = false,
  refreshSignal,
  onStatsChange,
}: {
  administrative?: boolean
  refreshSignal?: number
  onStatsChange?: (stats: SessionsStats) => void
}) {
  const auth = useAuth(), base = administrative ? '/api/security/sessions' : '/api/auth/sessions'
  const [rows, setRows] = useState<ActiveSession[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState(''), [busy, setBusy] = useState(false), [retry, setRetry] = useState(0)
  const [person, setPerson] = useState(''), [username, setUsername] = useState(''), [ip, setIp] = useState(''), [recent, setRecent] = useState('')
  const sending = useRef(false)

  useEffect(() => {
    if (refreshSignal) setRetry(v => v + 1)
  }, [refreshSignal])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(null)
    getJson<ActiveSession[]>(base, controller.signal).then(data => {
      if (!controller.signal.aborted) {
        setRows(data)
        if (onStatsChange) {
          const active5m = data.filter(r => Date.now() - Date.parse(r.last_activity) <= 5 * 60000).length
          onStatsChange({ total: data.length, active5m })
        }
      }
    }).catch(cause => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'No se pudieron consultar las sesiones')
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false)
    })
    return () => controller.abort()
  }, [base, retry, auth?.identity.role_id, auth?.identity.role_revision, onStatsChange])

  async function revoke(id?: string) {
    if (sending.current) return
    if (!window.confirm(id ? '¿Cerrar esta sesión? Se perderán los cambios no guardados en ese acceso.' : '¿Cerrar todas tus otras sesiones?')) return
    sending.current = true; setBusy(true); setError(null); setNotice('')
    try {
      await postJson(id ? `${base}/${id}/revoke` : '/api/auth/sessions/close-others', {})
      if (rows.some(row => row.id === id && row.current)) {
        await auth?.refresh()
      }
      setNotice('Sesiones cerradas correctamente.'); setRetry(value => value + 1)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'No se pudo cerrar la sesión'); setRetry(value => value + 1)
    } finally {
      sending.current = false; setBusy(false)
    }
  }

  const visible = rows.filter(row =>
    row.name.toLocaleLowerCase().includes(person.toLocaleLowerCase()) &&
    row.username.toLocaleLowerCase().includes(username.toLocaleLowerCase()) &&
    row.ip.includes(ip) &&
    (!recent || Date.now() - Date.parse(row.last_activity) <= Number(recent) * 60000)
  )

  const activeFilterCount = (person.trim() ? 1 : 0) + (username.trim() ? 1 : 0) + (ip.trim() ? 1 : 0) + (recent ? 1 : 0)

  return (
    <section aria-label={administrative ? 'Sesiones administrativas' : 'Sesiones propias'} className="panel noc-panel mb-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="toolbar-heading">{administrative ? 'Sesiones autorizadas' : 'Mis sesiones activas'}</h2>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="button-secondary rounded-full shadow-xs text-xs"
            disabled={busy || loading}
            onClick={() => setRetry(value => value + 1)}
          >
            <RefreshCw size={13} aria-hidden="true" />
            Actualizar sesiones
          </button>
          {!administrative && (
            <button
              type="button"
              className="button-secondary rounded-full shadow-xs text-xs"
              disabled={busy || !rows.some(row => !row.current)}
              onClick={() => void revoke()}
            >
              Cerrar las demás sesiones
            </button>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2 p-3 rounded-xl bg-slate-900/60 border border-slate-800/80 text-xs font-mono text-slate-400 mb-4">
        <Info size={14} className="text-slate-400 shrink-0" aria-hidden="true" />
        <span>Solo se muestran sesiones activas en memoria RAM (SecurityMemory). Al reiniciar el backend, todas las sesiones se cierran automáticamente.</span>
      </div>

      {administrative && (
        <section aria-label="Filtros de sesiones" className="filter-toolbar filter-toolbar--slate mb-5">
          <div className="filter-toolbar-header">
            <div className="flex flex-wrap items-center gap-2.5">
              <FilterHeading title="Filtros de sesiones" theme="slate" />
              {activeFilterCount > 0 && (
                <span className="filter-count-badge filter-count-badge--slate filter-count-badge--active">
                  <span className="filter-count-dot" />
                  {activeFilterCount} {activeFilterCount === 1 ? 'filtro activo' : 'filtros activos'}
                </span>
              )}
            </div>
            {activeFilterCount > 0 && (
              <button
                type="button"
                className="button-secondary rounded-full text-xs"
                onClick={() => { setPerson(''); setUsername(''); setIp(''); setRecent('') }}
              >
                Limpiar filtros
              </button>
            )}
          </div>
          <div className="filter-toolbar-body pt-3 border-t border-slate-800/80 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <FormField id="session-person" label="Responsable">
              <input
                id="session-person"
                className="form-input rounded-full text-xs"
                placeholder="Filtrar responsable..."
                value={person}
                onChange={e => setPerson(e.target.value)}
              />
            </FormField>
            <FormField id="session-username" label="Usuario">
              <input
                id="session-username"
                className="form-input rounded-full text-xs"
                placeholder="Filtrar usuario..."
                value={username}
                onChange={e => setUsername(e.target.value)}
              />
            </FormField>
            <FormField id="session-ip" label="IP">
              <input
                id="session-ip"
                className="form-input rounded-full text-xs font-mono"
                placeholder="Filtrar IP..."
                value={ip}
                onChange={e => setIp(e.target.value)}
              />
            </FormField>
            <FormField id="session-recent" label="Actividad reciente">
              <select
                id="session-recent"
                className="form-input rounded-full text-xs"
                value={recent}
                onChange={e => setRecent(e.target.value)}
              >
                <option value="">Todas</option>
                <option value="5">Últimos 5 minutos</option>
                <option value="15">Últimos 15 minutos</option>
              </select>
            </FormField>
          </div>
          {activeFilterCount > 0 && (
            <div className="mt-3">
              <FilterChips
                theme="slate"
                items={[
                  ...(person.trim() ? [{ label: 'Responsable', value: person.trim() }] : []),
                  ...(username.trim() ? [{ label: 'Usuario', value: username.trim() }] : []),
                  ...(ip.trim() ? [{ label: 'IP', value: ip.trim() }] : []),
                  ...(recent ? [{ label: 'Actividad', value: `Últimos ${recent} min` }] : []),
                ]}
              />
            </div>
          )}
        </section>
      )}

      {notice && <FeedbackMessage variant="success" className="mb-3">{notice}</FeedbackMessage>}
      {error && <FeedbackMessage variant="error" className="mb-3">{error}</FeedbackMessage>}
      <RequestState
        loading={loading}
        empty={!loading && !visible.length}
        emptyTitle="No hay sesiones activas para mostrar."
        error={null}
      />
      {!loading && !!visible.length && (
        <div className="panel table-surface overflow-x-auto rounded-2xl bg-[#0b1426] border table-surface--slate shadow-xl">
          <table className="operation-table min-w-[650px]">
            <caption className="sr-only">Sesiones activas</caption>
            <thead>
              <tr>
                <th scope="col">Responsable / usuario</th>
                <th scope="col">Dispositivo</th>
                <th scope="col">IP</th>
                <th scope="col">Última actividad</th>
                <th scope="col">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {visible.map(row => (
                <tr key={row.id}>
                  <td>
                    <span className="font-bold text-white text-sm">{row.name}</span>
                    <span className="block text-xs text-slate-400 font-mono mt-0.5">{row.username}</span>
                    {row.current && (
                      <span className="status-badge status-active mt-1">Sesión actual</span>
                    )}
                  </td>
                  <td title={row.agent}>
                    <div className="flex items-center gap-1.5 text-slate-300">
                      <MonitorSmartphone size={14} className="text-slate-400 shrink-0" aria-hidden="true" />
                      <span>{device(row.agent)}</span>
                    </div>
                  </td>
                  <td>
                    <span className="font-mono text-xs text-slate-300 px-2 py-0.5 rounded-md bg-slate-900 border border-slate-800">
                      {row.ip || 'No disponible'}
                    </span>
                  </td>
                  <td className="whitespace-nowrap text-xs tabular-nums text-slate-400 font-mono">
                    {formatDate(row.last_activity)}
                  </td>
                  <td>
                    <div className="table-actions">
                      <button
                        type="button"
                        className="button-secondary table-action rounded-full"
                        disabled={busy}
                        onClick={() => void revoke(row.id)}
                      >
                        Cerrar sesión{row.current ? ' actual' : ''}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
