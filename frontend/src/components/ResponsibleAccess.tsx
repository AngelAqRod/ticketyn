import { useEffect, useRef, useState, type FormEvent } from 'react'
import { getJson, postJson, patchJson } from '../api/client'
import { allPages, type Account, type SecurityRole } from '../api/security'
import { FeedbackMessage } from './FeedbackMessage'
import { RequestState } from './RequestState'
import { Link } from 'react-router'
import { useAuth } from '../auth/context'
import { Shield } from 'lucide-react'

export function ResponsibleAccess({ id, onClose, onSaved }: { id: number; onClose: () => void; onSaved: () => void }) {
  const own = useAuth()?.identity.responsible_id === id
  const [person, setPerson] = useState<Account | null>(null), [roles, setRoles] = useState<SecurityRole[]>([])
  const [username, setUsername] = useState(''), [role, setRole] = useState(''), [granted, setGranted] = useState(false)
  const [password, setPassword] = useState(''), [manual, setManual] = useState(false), [temporary, setTemporary] = useState('')
  const [error, setError] = useState<string | null>(null), [busy, setBusy] = useState(false), [notice, setNotice] = useState('')
  const sending = useRef(false)
  useEffect(() => {
    const c = new AbortController()
    Promise.all([getJson<Account>(`/api/responsibles/${id}/access`, c.signal), allPages<SecurityRole>('/api/security/roles', c.signal)]).then(([p, r]) => { if (!c.signal.aborted) { setPerson(p); setRoles(r); setUsername(p.username ?? ''); setRole(p.role_id ? String(p.role_id) : ''); setGranted(p.access_granted) } }).catch(e => { if (!c.signal.aborted) setError(e instanceof Error ? e.message : 'No se pudo consultar el acceso') })
    return () => c.abort()
  }, [id])
  async function execute(reset = false) {
    if (!person || sending.current) return
    if (reset && own) return
    if ((reset || !person.account_exists) && manual && (!password || new TextEncoder().encode(password).length > 4096)) { setError('La contraseña debe contener entre 1 y 4096 bytes UTF-8'); return }
    if (reset && !window.confirm('¿Restablecer la contraseña? Se cerrarán todas sus sesiones y deberá cambiar la contraseña temporal.')) return
    sending.current = true; setBusy(true); setError(null); setNotice(''); setTemporary('')
    const path = `/api/responsibles/${id}/access`
    try {
      if (reset) {
        const response = await postJson<{ temporary_password: string }>(path + '/password', { password: manual ? password : null })
        setTemporary(response.temporary_password)
      } else if (!person.account_exists) {
        const result = await postJson<Account & { temporary_password: string }>(path, { username, role_id: Number(role), access_granted: granted, password: manual ? password : null })
        const { temporary_password, ...configured } = result
        setPerson(configured); setTemporary(temporary_password)
      } else {
        const values: Record<string, unknown> = {}
        if (username !== person.username) values.username = username
        if (Number(role) !== person.role_id) values.role_id = Number(role)
        if (granted !== person.access_granted) values.access_granted = granted
        setPerson(await patchJson<Account>(path, values))
      }
      setPassword(''); setNotice(reset ? 'Contraseña restablecida.' : 'Acceso actualizado correctamente.'); onSaved()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo guardar el acceso') }
    finally { sending.current = false; setBusy(false) }
  }
  function submit(event: FormEvent) { event.preventDefault(); void execute() }
  return <section className="panel noc-panel mb-5 p-5 md:p-6 rounded-2xl bg-[#0b1426] border border-slate-700/60 shadow-xl" aria-label="Administrar acceso">
    <div className="flex items-center gap-2.5 border-b border-slate-700/60 pb-3 mb-4">
      <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-800/80 border border-slate-700/80 text-slate-300" aria-hidden="true">
        <Shield size={15} />
      </span>
      <h2 className="text-sm font-bold font-mono text-white uppercase tracking-wider">
        {person?.account_exists ? 'Administrar acceso' : 'Configurar acceso'}{person ? ` · ${person.name}` : ''}
      </h2>
    </div>
    <RequestState loading={!person && !error} error={error} errorTitle="" />
    {notice && <FeedbackMessage variant="success" className="mb-3">{notice}</FeedbackMessage>}
    {temporary && (
      <div role="status" className="p-4 rounded-xl bg-slate-900/90 border border-amber-500/40 shadow-lg my-4 space-y-2">
        <p className="text-xs text-amber-300 font-semibold font-mono uppercase tracking-wider">
          Contraseña temporal. Se muestra una sola vez; entrégala por un canal seguro.
        </p>
        <code className="block whitespace-pre-wrap break-all p-3 rounded-lg bg-black/60 border border-slate-800 font-mono text-sm text-amber-200 select-all">
          {temporary}
        </code>
        <button
          type="button"
          className="button-secondary rounded-full text-xs shadow-xs"
          onClick={() => setTemporary('')}
        >
          Ocultar contraseña temporal
        </button>
      </div>
    )}
    {person && <form onSubmit={submit} className="grid gap-4"><fieldset disabled={busy} className="grid gap-3 sm:grid-cols-2">
      <label className="block text-xs font-semibold text-slate-300 mb-1">Nombre de usuario<input className="form-input mt-1" required maxLength={100} value={username} autoComplete="off" onChange={e => setUsername(e.target.value)} /></label>
      <label className="block text-xs font-semibold text-slate-300 mb-1">Rol de seguridad<select className="form-input mt-1" required value={role} onChange={e => setRole(e.target.value)}><option value="">Selecciona un rol</option>{roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>
      <label className="flex items-center gap-2 text-sm text-slate-200"><input type="checkbox" checked={granted} disabled={!person.active && !granted} onChange={e => setGranted(e.target.checked)} />Habilitar acceso a Ticketyn</label>
      <p className="text-xs text-slate-400 font-mono">{!person.active ? 'Responsable inactivo: el acceso efectivo está bloqueado. Se conserva la autorización previa.' : person.effective_access ? 'Acceso efectivo habilitado.' : 'Acceso efectivo deshabilitado.'}</p>
      {!own && <label className="flex items-center gap-2 text-sm text-slate-200"><input type="checkbox" checked={manual} onChange={e => { setManual(e.target.checked); setPassword('') }} />Establecer contraseña temporal manualmente</label>}
      {manual && !own && <label className="block text-xs font-semibold text-slate-300 mb-1">Contraseña temporal<input className="form-input mt-1" type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} /></label>}
      {!manual && !own && <p className="text-xs text-slate-400 font-mono">La contraseña temporal se generará de forma segura al configurar o restablecer el acceso.</p>}
    </fieldset>{own && <p className="text-xs text-slate-400 font-mono">Cambia tu propia contraseña desde <Link to="/profile" className="text-sky-400 hover:text-sky-300 underline">Mi perfil</Link> para conservar esta sesión.</p>}<div className="flex flex-wrap gap-2 pt-2 border-t border-slate-800/80"><button className="button-primary button-primary--slate rounded-full shadow-sm" disabled={busy}>{busy ? 'Guardando…' : person.account_exists ? 'Guardar acceso' : 'Configurar acceso'}</button>{person.account_exists && !own && <button type="button" className="button-secondary rounded-full shadow-xs" disabled={busy} onClick={() => void execute(true)}>Restablecer contraseña</button>}<button type="button" className="button-secondary rounded-full shadow-xs" disabled={busy} onClick={onClose}>Cerrar</button></div></form>}
    {!person && <button className="button-secondary rounded-full shadow-xs mt-3" onClick={onClose}>Cerrar</button>}
  </section>
}
