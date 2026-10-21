import { useEffect, useRef, useState, type FormEvent } from 'react'
import { getAuditRetention, saveAuditRetention } from '../api/securityAudit'
import { ApiError } from '../api/client'
import { usePermissions } from '../auth/permissions'
import { Clock, RotateCw } from 'lucide-react'

export function AuditRetentionSettings({ onSaved }: { onSaved: () => void }) {
  const access = usePermissions(), allowed = access.can('security.configure')
  const permissionKey = access.permissions.join('\0')
  const [current, setCurrent] = useState<number | null>(null), [days, setDays] = useState('')
  const [confirmed, setConfirmed] = useState(false), [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false), [retry, setRetry] = useState(0)
  const [error, setError] = useState<string | null>(null), [success, setSuccess] = useState<string | null>(null)
  const busy = useRef(false), pending = useRef<AbortController | null>(null)
  useEffect(() => {
    const controller = new AbortController()
    pending.current?.abort(); pending.current = controller; busy.current = false
    setCurrent(null); setDays(''); setConfirmed(false); setError(null); setSuccess(null); setSaving(false)
    setLoading(allowed)
    if (!allowed) return () => controller.abort()
    getAuditRetention(controller.signal).then(value => {
      if (!controller.signal.aborted) { setCurrent(value.retention_days); setDays(String(value.retention_days)); setLoading(false) }
    }).catch(cause => {
      if (!controller.signal.aborted) { setError(cause instanceof Error ? cause.message : 'No se pudo consultar la conservación.'); setLoading(false) }
    })
    return () => { controller.abort(); pending.current?.abort() }
  }, [allowed, permissionKey, retry])

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (busy.current || current === null || !allowed) return
    setError(null); setSuccess(null)
    const value = Number(days)
    if (!/^\d+$/.test(days) || !Number.isInteger(value) || value < 1 || value > 3650) {
      setError('Introduce un número entero entre 1 y 3650 días.'); return
    }
    if (value < current && !confirmed) { setError('Confirma la reducción del período de conservación.'); return }
    busy.current = true; setSaving(true)
    const controller = new AbortController(); pending.current = controller
    try {
      const result = await saveAuditRetention(value, current, confirmed, controller.signal)
      if (!controller.signal.aborted) {
        setCurrent(result.retention_days); setDays(String(result.retention_days)); setConfirmed(false)
        setSuccess('Conservación guardada. Se aplicará en la próxima limpieza automática.'); onSaved()
      }
    } catch (cause) {
      if (!controller.signal.aborted) {
        if (cause instanceof ApiError && cause.status === 409) setCurrent(null)
        setError(cause instanceof Error ? cause.message : 'No se pudo guardar la conservación.')
      }
    } finally { if (!controller.signal.aborted) { busy.current = false; setSaving(false) } }
  }

  if (!allowed) return null
  return <section className="panel mb-4 p-4 sm:p-6 rounded-2xl border border-slate-700/60 bg-[#0b1426] shadow-xl" aria-labelledby="audit-retention-title">
    <div className="flex items-center gap-2.5 mb-3 pb-3 border-b border-slate-800/80">
      <span className="flex h-8 w-8 items-center justify-center rounded-xl border border-slate-700 bg-slate-800/60 text-slate-300 shadow-inner">
        <Clock size={16} />
      </span>
      <h2 id="audit-retention-title" className="text-base font-bold font-display text-white tracking-tight">Conservación de registros</h2>
    </div>
    {loading ? <p role="status" className="text-xs font-mono text-slate-400">Consultando conservación…</p> : <form onSubmit={submit}>
      <label className="block max-w-xs text-xs font-mono font-semibold text-slate-300">
        Días de conservación
        <input type="number" className="form-input font-mono mt-1.5 text-xs py-2 bg-[#070d1a] border-[#1e2c4a] focus:border-slate-500" min={1} max={3650} step={1} required
          value={days} disabled={saving || current === null} onChange={e => { setDays(e.target.value); setConfirmed(false); setSuccess(null) }} />
      </label>
      {current !== null && <p className="mt-2 text-xs font-mono text-slate-400">Valor actual: <span className="text-slate-200 font-semibold">{current} días</span>.</p>}
      <p className="mt-1 text-xs font-mono text-slate-500">Entre 1 y 3650 días. Guardar no elimina registros en este momento.</p>
      {current !== null && Number(days) < current && <label className="mt-3 flex items-start gap-2.5 p-3 rounded-xl bg-amber-950/30 border border-amber-800/60 text-xs font-mono text-amber-200">
        <input type="checkbox" className="mt-0.5 rounded border-amber-700 bg-[#070d1a] text-amber-500 focus:ring-0" checked={confirmed} disabled={saving} onChange={e => setConfirmed(e.target.checked)} />
        <span>Confirmo reducir la conservación de {current} a {days} días. La próxima limpieza automática podrá eliminar registros adicionales.</span>
      </label>}
      <div className="mt-4 flex flex-wrap gap-2">
        <button className="button-primary button-primary--slate rounded-full shadow-sm font-mono text-xs px-5 py-2 inline-flex items-center gap-1.5" disabled={saving || current === null}>
          {saving ? 'Guardando…' : 'Guardar'}
        </button>
        {current === null && <button type="button" className="button-secondary rounded-full shadow-xs font-mono text-xs px-4 py-2 inline-flex items-center gap-1.5" onClick={() => setRetry(value => value + 1)}>
          <RotateCw size={13} />Actualizar conservación
        </button>}
      </div>
    </form>}
    {error && <p role="alert" className="mt-3 text-xs font-mono text-rose-300 bg-rose-950/40 border border-rose-800/60 rounded-xl px-3.5 py-2.5">{error}</p>}
    {success && <p role="status" className="mt-3 text-xs font-mono text-emerald-300 bg-emerald-950/40 border border-emerald-800/60 rounded-xl px-3.5 py-2.5">{success}</p>}
  </section>
}
