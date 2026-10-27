import { type FormEvent, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { getJson, postJson } from '../api/client'
import { sessionToken, setSessionToken } from './session'
import { PermissionProvider, firstAllowed, routeAllowed } from './permissions'

import { AuthContext, type Identity } from './context'
import { PasswordChangeForm } from '../components/PasswordChangeForm'
import { LoginScreen, SESSION_EXPIRED_NOTICE } from './LoginScreen'

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
    const expired = () => { initialResolved.current = false; setIdentity(null); setLoading(false); setError(SESSION_EXPIRED_NOTICE) }
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
      <LoginScreen notice={error ? { kind: error === SESSION_EXPIRED_NOTICE ? 'info' : 'error', text: error } : null} busy={busy} showPassword={showPassword} onTogglePassword={() => setShowPassword(v => !v)} onSubmit={login} />
    )}
    {change && identity && <main className="panel mx-auto mt-6 max-w-lg p-6 rounded-3xl bg-[#0b1426] border border-slate-700/60 shadow-xl"><h1 className="text-xl font-bold font-display text-white tracking-tight">Cambiar contraseña temporal</h1><p className="mb-4 text-xs font-mono text-slate-400">{identity.name} · {identity.username}</p><PasswordChangeForm /><button className="button-secondary rounded-full mt-4 text-xs font-mono" disabled={busy} onClick={() => void logout()}>Cerrar sesión</button></main>}
    {identity && !identity.operational_access && !change && <main className="panel m-6 p-6">Tu cuenta no tiene permisos sobre los módulos disponibles. Puedes acceder a Mi perfil y cerrar sesión.</main>}
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
