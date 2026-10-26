import { type FormEvent, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { getJson, postJson } from '../api/client'
import { sessionToken, setSessionToken } from './session'
import { PermissionProvider, firstAllowed, routeAllowed } from './permissions'

import { AuthContext, type Identity } from './context'
import { PasswordChangeForm } from '../components/PasswordChangeForm'
import { Eye, EyeOff, Lock, User, ChevronRight } from 'lucide-react'

export function AuthGate({ children }: { children: ReactNode }) {
  const [identity, setIdentity] = useState<Identity | null>(null)
  const [loading, setLoading] = useState(!!sessionToken())
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const previousPermissions = useRef('')
  const lastAllowedPath = useRef<string | null>(null)
  const initialResolved = useRef(false)
  const [busy, setBusy] = useState(false)
  const [remaining, setRemaining] = useState(0)
  const [draftOwner, setDraftOwner] = useState<number | null>(null)
  const expires = useRef(0)
  const activityAt = useRef(0)
  const inFlight = useRef(false)
  const actionInFlight = useRef(false)
  const location = useLocation()
  const navigate = useNavigate()
  const accept = useCallback((data: Identity) => {
    const signature = JSON.stringify([data.role_id, data.role_revision, data.permissions ?? []])
    if (previousPermissions.current && previousPermissions.current !== signature) setNotice('Tus permisos han sido actualizados.')
    previousPermissions.current = signature
    expires.current = Date.now() + data.expires_in * 1000
    setRemaining(data.expires_in)
    setDraftOwner(data.responsible_id)
    setIdentity(data)
    setLoading(false)
  }, [])
  const refresh = useCallback(async () => {
    const token = sessionToken()
    if (!token || inFlight.current) return
    inFlight.current = true
    try {
      const data = await getJson<Identity>('/api/auth/me')
      if (sessionToken() === token) accept(data)
    }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo comprobar la sesión'); setLoading(false) }
    finally { inFlight.current = false }
  }, [accept])
  useEffect(() => {
    const expired = () => { initialResolved.current = false; setIdentity(null); setLoading(false); setError('Tu sesión venció o fue invalidada. Iniciá sesión nuevamente.') }
    window.addEventListener('ticketyn:unauthorized', expired)
    const focus = () => { void refresh() }
    window.addEventListener('focus', focus)
    const polling = window.setInterval(() => { void refresh() }, 15000)
    const timer = window.setInterval(() => setRemaining(Math.max(0, (expires.current - Date.now()) / 1000)), 1000)
    return () => { window.removeEventListener('ticketyn:unauthorized', expired); window.removeEventListener('focus', focus); clearInterval(polling); clearInterval(timer) }
  }, [refresh])
  useEffect(() => { void refresh() }, [location.key, refresh])
  const access = useMemo(() => {
    const permissions = identity?.permissions ?? []
    const grants = new Set(permissions)
    return { permissions, can: (...codes: string[]) => codes.every(code => grants.has(code)), any: (...codes: string[]) => codes.some(code => grants.has(code)) }
  }, [identity])
  useEffect(() => {
    if (!identity || identity.password_change_required) { lastAllowedPath.current = null; return }
    const permitted = routeAllowed(location.pathname, access)
    const lostAccess = !permitted && lastAllowedPath.current === location.pathname
    if (permitted) lastAllowedPath.current = location.pathname

    if (!initialResolved.current) {
      initialResolved.current = true
      if (location.pathname === '/' && !location.state?.explicit && identity.preferred_home_page === 'MY_TICKETS' && routeAllowed('/my-tickets', access)) {
        navigate('/my-tickets', { replace: true })
        return
      }
    }

    if (location.pathname === '/login' || lostAccess || (!access.permissions.length && location.pathname !== '/profile')) {
      lastAllowedPath.current = null
      navigate(firstAllowed(access, identity.preferred_home_page), { replace: true })
    }
  }, [access, identity, location.pathname, location.state, navigate])
  const continueSession = useCallback(async () => {
    const token = sessionToken()
    if (!token || inFlight.current) return
    inFlight.current = true
    try {
      const data = await postJson<Identity>('/api/auth/activity', {})
      if (sessionToken() === token) { accept(data); activityAt.current = Date.now() }
    }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo continuar la sesión') }
    finally { inFlight.current = false }
  }, [accept])
  useEffect(() => {
    const activity = (event: Event) => {
      if (event.isTrusted && document.visibilityState === 'visible' && sessionToken() && Date.now() - activityAt.current > 60000) void continueSession()
    }
    window.addEventListener('pointerdown', activity)
    window.addEventListener('keydown', activity)
    return () => { window.removeEventListener('pointerdown', activity); window.removeEventListener('keydown', activity) }
  }, [continueSession])
  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (actionInFlight.current) return
    actionInFlight.current = true
    setBusy(true); setError('')
    const form = event.currentTarget
    const fields = new FormData(form)
    try {
      const result = await postJson<Identity & { token: string }>('/api/auth/login', { username: fields.get('username'), password: fields.get('password') })
      setSessionToken(result.token); accept(result); form.reset()
      setNotice('')
      initialResolved.current = true
      const grants=new Set(result.permissions)
      const nextAccess={permissions:result.permissions,can:(...codes:string[])=>codes.every(code=>grants.has(code)),any:(...codes:string[])=>codes.some(code=>grants.has(code))}
      const target = firstAllowed(nextAccess, result.preferred_home_page)
      if (location.pathname === '/login' || location.pathname === '/' || !routeAllowed(location.pathname, nextAccess)) {
        navigate(target, { replace: true })
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo iniciar sesión') }
    finally { actionInFlight.current = false; setBusy(false) }
  }
  async function logout() {
    if (actionInFlight.current) return
    actionInFlight.current = true
    setBusy(true); setError('')
    try {
      await postJson('/api/auth/logout', {})
      setSessionToken(null); setIdentity(null); setDraftOwner(null); previousPermissions.current = ''; lastAllowedPath.current = null; initialResolved.current = false; setNotice('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo cerrar la sesión') }
    finally { actionInFlight.current = false; setBusy(false) }
  }
  if (loading) return <main className="panel m-6 p-6" role="status">Comprobando sesión…</main>
  const change = identity?.password_change_required
  // Keep operational forms mounted, hidden and inert after expiration. Unsaved drafts
  // remain only in component RAM; passwords and tokens are never written to draft storage.
  return <AuthContext.Provider value={identity ? { identity, busy, logout, accept, refresh } : null}><PermissionProvider permissions={identity?.permissions ?? []}>
    {identity && notice && <p role="status" className="panel m-3 p-3 rounded-xl bg-cyan-950/40 border border-cyan-800/60 text-xs font-mono text-cyan-200">{notice}</p>}

    {identity && remaining <= 120 && <div role="alert" className="panel m-3 p-3 rounded-xl bg-amber-950/40 border border-amber-800/60 text-xs font-mono text-amber-200 flex items-center justify-between gap-3"><span>Tu sesión está por vencer por inactividad.</span> <button className="button-primary button-primary--amber rounded-full px-3.5 py-1 text-xs" onClick={() => void continueSession()}>Continuar sesión</button></div>}
    {identity && error && <p role="alert" className="panel m-3 p-3 rounded-xl bg-rose-950/40 border border-rose-800/80 text-xs font-mono text-rose-200">{error}</p>}
    {!identity && (
      <div className="min-h-screen relative flex flex-col items-center justify-center overflow-x-hidden bg-[#030712] text-slate-100 select-none px-4 py-8 sm:py-12">
        <svg className="absolute inset-0 w-full h-full pointer-events-none opacity-40" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
          <defs>
            <linearGradient id="netGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#0879F8" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#00D1FF" stopOpacity="0.15" />
            </linearGradient>
          </defs>
          <g stroke="url(#netGrad)" strokeWidth="0.85" fill="none">
            <line x1="8%" y1="8%" x2="22%" y2="12%" />
            <line x1="22%" y1="12%" x2="18%" y2="24%" />
            <line x1="18%" y1="24%" x2="28%" y2="30%" />
            <line x1="78%" y1="10%" x2="92%" y2="16%" />
            <line x1="92%" y1="16%" x2="84%" y2="26%" />
            <line x1="84%" y1="26%" x2="72%" y2="20%" />
            <line x1="72%" y1="20%" x2="65%" y2="12%" />
            <line x1="5%" y1="45%" x2="14%" y2="52%" />
            <line x1="14%" y1="52%" x2="8%" y2="65%" />
            <line x1="88%" y1="42%" x2="95%" y2="55%" />
            <line x1="95%" y1="55%" x2="86%" y2="68%" />
            <line x1="12%" y1="80%" x2="25%" y2="86%" />
            <line x1="25%" y1="86%" x2="38%" y2="82%" />
            <line x1="38%" y1="82%" x2="48%" y2="90%" />
            <line x1="62%" y1="88%" x2="75%" y2="82%" />
            <line x1="75%" y1="82%" x2="88%" y2="88%" />
          </g>
          <g fill="#00D1FF">
            <circle cx="8%" cy="8%" r="2" opacity="0.4" />
            <circle cx="22%" cy="12%" r="2.5" opacity="0.6" />
            <circle cx="18%" cy="24%" r="2" opacity="0.5" />
            <circle cx="28%" cy="30%" r="3" opacity="0.7" />
            <circle cx="78%" cy="10%" r="2.5" opacity="0.5" />
            <circle cx="92%" cy="16%" r="2" opacity="0.4" />
            <circle cx="84%" cy="26%" r="3" opacity="0.8" />
            <circle cx="72%" cy="20%" r="2" opacity="0.5" />
            <circle cx="65%" cy="12%" r="2.5" opacity="0.6" />
            <circle cx="5%" cy="45%" r="2" opacity="0.4" />
            <circle cx="14%" cy="52%" r="3" opacity="0.7" />
            <circle cx="8%" cy="65%" r="2.5" opacity="0.5" />
            <circle cx="88%" cy="42%" r="2.5" opacity="0.6" />
            <circle cx="95%" cy="55%" r="2" opacity="0.4" />
            <circle cx="86%" cy="68%" r="3" opacity="0.75" />
            <circle cx="12%" cy="80%" r="2" opacity="0.4" />
            <circle cx="25%" cy="86%" r="3" opacity="0.7" />
            <circle cx="38%" cy="82%" r="2" opacity="0.5" />
            <circle cx="48%" cy="90%" r="2.5" opacity="0.6" />
            <circle cx="62%" cy="88%" r="2" opacity="0.4" />
            <circle cx="75%" cy="82%" r="3" opacity="0.7" />
            <circle cx="88%" cy="88%" r="2.5" opacity="0.5" />
          </g>
        </svg>

        <div className="absolute inset-0 pointer-events-none flex items-center justify-center overflow-hidden" aria-hidden="true">
          <div className="w-[600px] h-[600px] rounded-full bg-[#0879F8]/8 blur-[120px] sm:-translate-y-[44px]"></div>
        </div>

        <div className="relative z-10 w-full flex flex-col items-center sm:-translate-y-[44px]">
          <div className="flex flex-col items-center mb-6 sm:mb-8 text-center">
            <div className="relative w-44 h-44 sm:w-52 sm:h-52 flex items-center justify-center">
              <svg className="absolute inset-0 w-full h-full pointer-events-none radar-pulse" viewBox="0 0 220 220" aria-hidden="true">
                <circle cx="110" cy="110" r="100" fill="none" stroke="rgba(8, 121, 248, 0.16)" strokeWidth="1" />
                <circle cx="110" cy="110" r="76" fill="none" stroke="rgba(0, 209, 255, 0.22)" strokeWidth="1" strokeDasharray="4,5" />
                <circle cx="110" cy="110" r="54" fill="none" stroke="rgba(8, 121, 248, 0.3)" strokeWidth="1" strokeDasharray="3,3" />
                <circle cx="178" cy="62" r="3" fill="#00D1FF" opacity="0.85" />
                <circle cx="42" cy="145" r="2.5" fill="#0879F8" opacity="0.75" />
                <circle cx="132" cy="184" r="3" fill="#00D1FF" opacity="0.85" />
                <circle cx="68" cy="48" r="2" fill="#0879F8" opacity="0.7" />
                <line x1="32" y1="188" x2="188" y2="32" stroke="rgba(0, 209, 255, 0.16)" strokeWidth="1" strokeDasharray="3,4" />
              </svg>
              <img src="/branding/isotipo_oscuro.svg" alt="" aria-hidden="true" className="w-24 h-24 sm:w-28 sm:h-28 relative z-10 drop-shadow-[0_0_30px_rgba(0,209,255,0.45)]" />
            </div>

            <div className="-mt-1 sm:-mt-2 flex flex-col items-center">
              <img src="/branding/logotipo_oscuro.svg" alt="Ticketyn" className="h-14 sm:h-[62px] w-auto drop-shadow-[0_4px_18px_rgba(8,121,248,0.4)]" />
              <p className="text-xs sm:text-sm font-mono text-slate-400 tracking-widest mt-2.5 uppercase flex items-center justify-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_6px_#00D1FF]" aria-hidden="true"></span>
                <span>Centro de Operaciones de Red</span>
              </p>
            </div>
          </div>

          <main className="panel w-full max-w-[460px] sm:max-w-[470px] rounded-3xl bg-[#0b1426]/95 border border-slate-700/80 p-8 sm:p-10 shadow-[0_25px_60px_rgba(0,0,0,0.8)] backdrop-blur-md relative">
            <div className="absolute -top-px left-14 right-14 h-px bg-gradient-to-r from-transparent via-cyan-400/60 to-transparent" aria-hidden="true"></div>

            <div className="mb-7 text-center">
              <h1 className="text-2xl sm:text-[26px] font-bold font-display text-white tracking-tight">
                Iniciar sesión en Ticketyn
              </h1>
              <p className="text-xs sm:text-sm text-slate-400 mt-1.5 font-mono">
                Ingresá tus credenciales para continuar
              </p>
            </div>

            {error && (
              <p role="alert" className="mb-5 p-3.5 rounded-xl bg-rose-950/40 border border-rose-800/80 text-xs font-mono text-rose-200 leading-relaxed shadow-sm">
                {error}
              </p>
            )}

            <form onSubmit={login} className="space-y-5">
              <div>
                <label className="block text-xs font-mono font-bold tracking-wider uppercase text-slate-300 mb-2">
                  Usuario
                  <div className="relative mt-1 flex items-center">
                    <span className="absolute left-4 pointer-events-none text-slate-500" aria-hidden="true">
                      <User size={16} />
                    </span>
                    <input
                      className="form-input font-mono w-full bg-[#070d1a] border border-[#1e2c4a] rounded-xl pl-11 pr-4 py-3 text-sm text-slate-100 placeholder:text-slate-400 placeholder:opacity-100 focus:outline-none input-focused-glow transition duration-150"
                      name="username"
                      autoComplete="username"
                      required
                      maxLength={100}
                      placeholder="Ej. operador.noc"
                    />
                  </div>
                </label>
              </div>

              <div>
                <label className="block text-xs font-mono font-bold tracking-wider uppercase text-slate-300 mb-2">
                  Contraseña
                  <div className="relative mt-1 flex items-center">
                    <span className="absolute left-4 pointer-events-none text-sky-400" aria-hidden="true">
                      <Lock size={16} />
                    </span>
                    <input
                      className="form-input font-mono w-full bg-[#070d1a] border border-[#1e2c4a] rounded-xl pl-11 pr-11 py-3 text-sm text-slate-100 placeholder:text-slate-400 placeholder:opacity-100 focus:outline-none input-focused-glow transition duration-150"
                      name="password"
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="current-password"
                      required
                      placeholder="••••••••••••"
                    />
                    <button
                      type="button"
                      aria-label={showPassword ? 'Ocultar contraseña' : 'Ver contraseña'}
                      onClick={() => setShowPassword(v => !v)}
                      className="absolute right-3.5 text-slate-400 hover:text-slate-200 transition"
                    >
                      {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </label>
              </div>

              <div className="pt-2">
                <button
                  className="button-primary btn-gradient-electric w-full rounded-full py-3.5 px-6 font-mono text-xs sm:text-sm font-bold tracking-wider uppercase flex items-center justify-center gap-2 cursor-pointer transition-all duration-200"
                  disabled={busy}
                >
                  <span>{busy ? 'Iniciando…' : 'Iniciar sesión'}</span>
                  <ChevronRight size={16} aria-hidden="true" />
                </button>
              </div>
            </form>
          </main>

          <div className="mt-8 text-center">
            <p className="text-xs font-mono text-slate-400 tracking-wider">
              Acceso autorizado · Centro de Operaciones de Red
            </p>
          </div>
        </div>
      </div>
    )}
    {change && identity && <main className="panel mx-auto mt-6 max-w-lg p-6 rounded-3xl bg-[#0b1426] border border-slate-700/60 shadow-xl"><h1 className="text-xl font-bold font-display text-white tracking-tight">Cambiar contraseña temporal</h1><p className="mb-4 text-xs font-mono text-slate-400">{identity.name} · {identity.username}</p><PasswordChangeForm /><button className="button-secondary rounded-full mt-4 text-xs font-mono" disabled={busy} onClick={() => void logout()}>Cerrar sesión</button></main>}
    {identity && !identity.operational_access && !change && <main className="panel m-6 p-6">Tu cuenta no tiene permisos sobre los módulos disponibles. Podés acceder a Mi perfil y cerrar sesión.</main>}
    {identity && !change && !routeAllowed(location.pathname, access) && <main className="panel m-6 p-6" role="alert"><h1 className="text-xl font-semibold">Acceso denegado</h1><p>No tienes permiso para acceder a este módulo.</p><button className="button-secondary mt-3" onClick={() => navigate(firstAllowed(access, identity?.preferred_home_page))}>Ir a un módulo autorizado</button></main>}
    <OperationalDraft key={draftOwner ?? 'signed-out'} visible={!!identity && (identity.operational_access || location.pathname === '/profile') && !change && routeAllowed(location.pathname, access)}>{children}</OperationalDraft>
  </PermissionProvider></AuthContext.Provider>
}

function OperationalDraft({ visible, children }: { visible: boolean; children: ReactNode }) {
  const mounted = useRef(false)
  if (visible) mounted.current = true
  if (!mounted.current) return null
  return <div hidden={!visible} inert={!visible}>{children}</div>
}
