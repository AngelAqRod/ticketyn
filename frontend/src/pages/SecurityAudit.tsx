import { useEffect, useState, type FormEvent } from 'react'
import { getSecurityAudit, type AuditPage } from '../api/securityAudit'
import { usePermissions } from '../auth/permissions'
import { PageHeading } from '../components/PageHeading'
import { PaginationBar } from '../components/PaginationBar'
import { RequestState } from '../components/RequestState'
import { AuditRetentionSettings } from '../components/AuditRetentionSettings'
import { useUrlFilters } from '../hooks/useUrlFilters'
import { ticketynDateTimeToIso, ticketynDateTimeValue, ticketynTimezone } from '../lib/datetime'
import { Filter, RotateCw } from 'lucide-react'

const filterKeys = ['username', 'from_at', 'to_at', 'event', 'result']
function displayDate(value: string | null) {
  if (!value || Number.isNaN(Date.parse(value))) return ''
  return ticketynDateTimeValue(new Date(value), true)
}

export function SecurityAudit() {
  const access = usePermissions(), allowed = access.can('audit.view')
  const { params, change, clear } = useUrlFilters(filterKeys)
  const key = params.toString(), permissionKey = access.permissions.join('\0')
  const [data, setData] = useState<AuditPage | null>(null)
  const [loading, setLoading] = useState(true), [error, setError] = useState<string | null>(null)
  const [retry, setRetry] = useState(0), [validation, setValidation] = useState<string | null>(null)
  const [username, setUsername] = useState(''), [event, setEvent] = useState(''), [result, setResult] = useState('ALL')
  const [from, setFrom] = useState(''), [to, setTo] = useState('')
  useEffect(() => {
    const selected = new URLSearchParams(key)
    setUsername(selected.get('username') ?? ''); setEvent(selected.get('event') ?? '')
    setResult(selected.get('result') ?? 'ALL')
    setFrom(displayDate(selected.get('from_at'))); setTo(displayDate(selected.get('to_at')))
  }, [key])
  useEffect(() => {
    setData(null); setError(null); setLoading(allowed)
    if (!allowed) return
    const controller = new AbortController(), query = new URLSearchParams(key)
    query.set('limit', '50')
    getSecurityAudit(query.toString(), controller.signal).then(page => {
      if (!controller.signal.aborted) { setData(page); setLoading(false) }
    }).catch(cause => {
      if (!controller.signal.aborted) { setError(cause instanceof Error ? cause.message : 'No se pudo consultar la auditoría.'); setLoading(false) }
    })
    return () => controller.abort()
  }, [key, permissionKey, allowed, retry])

  function submit(e: FormEvent) {
    e.preventDefault(); setValidation(null)
    try {
      const start = from ? ticketynDateTimeToIso(from) : '', end = to ? ticketynDateTimeToIso(to) : ''
      if (start && end && start >= end) throw new Error('El inicio del período debe ser anterior al final.')
      change({ username, event, result: result === 'ALL' ? '' : result, from_at: start, to_at: end })
    } catch (cause) { setValidation(cause instanceof Error ? cause.message : 'Revisa el período.') }
  }

  if (!allowed) return <RequestState error="No tienes permiso para consultar la auditoría de seguridad." errorTitle="Acceso denegado" />
  const offset = Number(params.get('offset') ?? 0)
  return <>
    <PageHeading
      title="Auditoría de seguridad"
      description="Consulta de eventos de acceso, credenciales, roles y sesiones. Los registros son de solo lectura."
      telemetry={data ? (
        <>
          <div className="telemetry-item">
            <span className="telemetry-label">Eventos</span>
            <span className="telemetry-value telemetry-value--slate font-mono text-xs">
              {data.events.length}
            </span>
          </div>
          <div className="telemetry-item">
            <span className="telemetry-label">Registros</span>
            <span className="telemetry-value telemetry-value--slate font-mono text-xs">
              {data.total}
            </span>
          </div>
        </>
      ) : undefined}
      action={
        <button
          type="button"
          className="button-secondary rounded-full shadow-xs font-mono text-xs px-4 py-2 inline-flex items-center gap-1.5"
          disabled={loading}
          onClick={() => setRetry(value => value + 1)}
        >
          <RotateCw size={13} className={loading ? 'animate-spin' : ''} />
          Actualizar
        </button>
      }
    />
    <AuditRetentionSettings onSaved={() => setRetry(value => value + 1)} />
    <form className="panel mb-4 p-4 sm:p-6 rounded-2xl border border-slate-700/60 bg-[#0b1426] shadow-xl" aria-label="Filtros de auditoría" onSubmit={submit}>
      <div className="flex items-center gap-2 mb-4 pb-3 border-b border-slate-800/80">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-slate-700 bg-slate-800/60 text-slate-300">
          <Filter size={14} />
        </span>
        <h2 className="text-xs font-mono font-bold uppercase tracking-wider text-white">Filtros de auditoría</h2>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <label className="text-xs font-mono font-semibold text-slate-300">
          Usuario o responsable
          <input className="form-input font-mono mt-1 text-xs py-2 bg-[#070d1a] border-[#1e2c4a] focus:border-slate-500" value={username} maxLength={100} onChange={e => setUsername(e.target.value)} />
        </label>
        <label className="text-xs font-mono font-semibold text-slate-300">
          Desde ({ticketynTimezone})
          <input className="form-input font-mono mt-1 text-xs py-2 bg-[#070d1a] border-[#1e2c4a] focus:border-slate-500" type="datetime-local" step="1" value={from} onChange={e => setFrom(e.target.value)} />
        </label>
        <label className="text-xs font-mono font-semibold text-slate-300">
          Hasta, excluido ({ticketynTimezone})
          <input className="form-input font-mono mt-1 text-xs py-2 bg-[#070d1a] border-[#1e2c4a] focus:border-slate-500" type="datetime-local" step="1" value={to} onChange={e => setTo(e.target.value)} />
        </label>
        <label className="text-xs font-mono font-semibold text-slate-300">
          Tipo de evento
          <select className="form-input font-mono mt-1 text-xs py-2 bg-[#070d1a] border-[#1e2c4a] focus:border-slate-500" value={event} onChange={e => setEvent(e.target.value)}>
            <option value="">Todos los eventos</option>
            {data?.events.map(option => <option key={option.code} value={option.code}>{option.label}</option>)}
          </select>
        </label>
        <label className="text-xs font-mono font-semibold text-slate-300">
          Resultado
          <select className="form-input font-mono mt-1 text-xs py-2 bg-[#070d1a] border-[#1e2c4a] focus:border-slate-500" value={result} onChange={e => setResult(e.target.value)}>
            <option value="ALL">Todos</option>
            <option value="SUCCESS">Exitoso</option>
            <option value="FAILURE">Fallido</option>
          </select>
        </label>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button className="button-primary button-primary--slate rounded-full shadow-sm font-mono text-xs px-5 py-2" disabled={loading}>
          Aplicar filtros
        </button>
        <button className="button-secondary rounded-full shadow-xs font-mono text-xs px-4 py-2" type="button" onClick={() => { setValidation(null); setUsername(''); setEvent(''); setResult('ALL'); setFrom(''); setTo(''); clear() }}>
          Limpiar filtros
        </button>
      </div>
      {validation && <p role="alert" className="mt-3 text-xs font-mono text-rose-300 bg-rose-950/40 border border-rose-800/60 rounded-xl px-3.5 py-2.5">{validation}</p>}
    </form>
    <RequestState loading={loading} error={error} errorTitle="No se pudo consultar la auditoría" onRetry={() => setRetry(value => value + 1)}
      empty={!loading && !error && data?.items.length === 0} emptyTitle="Sin eventos de seguridad" emptyDescription="No se encontraron registros con los filtros seleccionados." />
    {!loading && !error && data && data.items.length > 0 && <div className="panel mb-4 p-4 rounded-2xl border border-slate-700/60 bg-[#0b1426] shadow-xl overflow-x-auto">
      <table className="operation-table table-surface table-surface--slate min-w-[750px]" aria-label="Registros de auditoría de seguridad">
        <thead>
          <tr>
            {['Fecha y hora', 'Usuario o identificador', 'Evento', 'Resultado', 'Detalles'].map(label => (
              <th key={label} scope="col" className="p-3 text-left font-mono text-xs uppercase tracking-wider text-slate-400 border-b border-slate-800">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.items.map(row => (
            <tr key={row.id} className="border-t border-slate-800/80 hover:bg-[#0e1930]/60 transition-colors align-top">
              <td className="whitespace-nowrap p-3 font-mono text-xs">
                <time dateTime={row.occurred_at} className="font-semibold text-slate-200">
                  {ticketynDateTimeValue(new Date(row.occurred_at), true).replace('T', ' ')}
                </time>
                <div className="text-[11px] text-slate-400 font-mono mt-0.5">{ticketynTimezone}</div>
              </td>
              <td className="p-3 [overflow-wrap:anywhere] font-mono text-xs">
                {row.actor ? (
                  <>
                    <span className="font-semibold text-white">{row.actor.name}</span>
                    <div className="text-[11px] text-slate-400 mt-0.5">{row.actor.username ?? `Responsable #${row.actor.id}`} · datos actuales</div>
                  </>
                ) : (
                  <span className="text-slate-300">{row.identifier ?? (row.source === 'Administración local' ? 'Administración local' : 'Usuario no identificado')}</span>
                )}
              </td>
              <td className="p-3 font-mono text-xs">
                <span className="font-medium text-slate-200">{row.event_label}</span>
                <div className="text-[11px] text-slate-400 mt-0.5">{row.source}</div>
              </td>
              <td className="p-3 font-mono text-xs">
                <span className={`chip ${row.success ? 'chip-success' : 'chip-danger'} inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold border ${row.success ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800/80' : 'bg-rose-950/60 text-rose-300 border-rose-800/80'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${row.success ? 'bg-emerald-400 shadow-[0_0_6px_#34d399]' : 'bg-rose-400 shadow-[0_0_6px_#fb7185]'}`}></span>
                  {row.success ? 'Exitoso' : 'Fallido'}
                </span>
              </td>
              <td className="min-w-56 p-3 [overflow-wrap:anywhere] font-mono text-xs text-slate-300">
                {row.target && (
                  <p className="mb-1.5 text-slate-200">
                    <span className="font-semibold text-slate-400">Responsable afectado: </span>{row.target.name} · #{row.target.id} (datos actuales)
                  </p>
                )}
                {row.details.length > 0 ? (
                  <dl className="space-y-1">
                    {row.details.map((detail, index) => (
                      <div key={index} className="text-slate-300">
                        <dt className="inline font-semibold text-slate-400">{detail.label}: </dt>
                        <dd className="inline whitespace-pre-wrap text-slate-200">{detail.value}</dd>
                      </div>
                    ))}
                  </dl>
                ) : (
                  <span className="text-slate-400 italic">Sin detalles adicionales registrados.</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>}
    <PaginationBar page={Math.floor(offset / 50) + 1} info={data ? `${data.total} registros · 50 por página` : '50 registros por página'}
      previousDisabled={loading || Boolean(error) || offset <= 0} nextDisabled={loading || Boolean(error) || !data || offset + 50 >= data.total}
      onPrevious={() => change({ offset: String(Math.max(0, offset - 50)) }, false)} onNext={() => change({ offset: String(offset + 50) }, false)} />
  </>
}
