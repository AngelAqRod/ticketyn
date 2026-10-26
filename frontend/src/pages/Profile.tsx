import { useAuth } from '../auth/context'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { KeyRound, Monitor, UserRound, Activity, UserCheck, History, TrendingUp, ShieldAlert } from 'lucide-react'
import { getJson, patchJson } from '../api/client'
import type { Account } from '../api/security'
import { getMyTicketsSummary } from '../api/myTickets'
import type { MyTicketsSummaryResponse } from '../types/myTickets'
import { usePermissions } from '../auth/permissions'
import { LcdOperatorAvatar } from '../components/LcdOperatorAvatar'
import { PasswordChangeForm } from '../components/PasswordChangeForm'
import { SessionsPanel } from '../components/SessionsPanel'
import { RequestState } from '../components/RequestState'
import { FeedbackMessage } from '../components/FeedbackMessage'
import '../styles/operatorProfile.css'

interface OwnProfile extends Account { preferences?: { home_page: 'DASHBOARD' | 'MY_TICKETS' } }

function ProfilePreferences({ profile }: { profile: OwnProfile }) {
  const auth = useAuth()
  const [homePage, setHomePage] = useState<'DASHBOARD' | 'MY_TICKETS'>(profile.preferences?.home_page ?? 'DASHBOARD')
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const sending = useRef(false)

  useEffect(() => {
    if (profile.preferences?.home_page) {
      setHomePage(profile.preferences.home_page)
    }
  }, [profile.preferences?.home_page])

  async function save(event: FormEvent) {
    event.preventDefault()
    if (sending.current) return
    sending.current = true; setBusy(true); setError(''); setNotice('')
    try {
      await patchJson('/api/auth/profile/preferences', { home_page: homePage })
      setNotice(`Preferencia guardada: ${homePage === 'MY_TICKETS' ? 'Mis tickets' : 'Dashboard / Inicio'}.`)
      if (auth?.identity) {
        auth.accept({ ...auth.identity, preferred_home_page: homePage })
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo guardar la preferencia.') }
    finally { sending.current = false; setBusy(false) }
  }
  return <section className="profile-panel" aria-labelledby="profile-preferences-title">
    <h2 id="profile-preferences-title"><Monitor size={18} aria-hidden="true" />Preferencias</h2>
    <form onSubmit={save} aria-label="Preferencias personales">
      <fieldset disabled={busy} className="profile-home-options"><legend>Pantalla inicial</legend>
        <label><input type="radio" name="home_page" value="DASHBOARD" checked={homePage === 'DASHBOARD'} onChange={() => setHomePage('DASHBOARD')} />Dashboard / Inicio</label>
        <label><input type="radio" name="home_page" value="MY_TICKETS" checked={homePage === 'MY_TICKETS'} onChange={() => setHomePage('MY_TICKETS')} />Mis tickets</label>
      </fieldset>
      <p className="profile-note">El inicio respeta siempre tus permisos de acceso.</p>
      {error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}
      {notice && <FeedbackMessage variant="success">{notice}</FeedbackMessage>}
      <button className="button-secondary" disabled={busy}>{busy ? 'Guardando…' : 'Guardar preferencia'}</button>
    </form>
  </section>
}

function ProfileActivity() {
  const access = usePermissions()
  const canAccessMyTickets = access.any('tickets.view', 'internal_tickets.view')
  const [summary, setSummary] = useState<MyTicketsSummaryResponse | null>(null)

  useEffect(() => {
    if (!canAccessMyTickets) return
    const controller = new AbortController()
    getMyTicketsSummary(controller.signal)
      .then(data => { if (!controller.signal.aborted) setSummary(data) })
      .catch(() => {})
    return () => controller.abort()
  }, [canAccessMyTickets])

  return <section className="profile-panel profile-activity-panel" aria-labelledby="profile-activity-title">
    <h2 id="profile-activity-title"><Activity size={18} aria-hidden="true" />Mi actividad</h2>
    {canAccessMyTickets ? (
      <div className="profile-activity-grid" role="navigation" aria-label="Accesos a mi actividad">
        <Link to="/my-tickets?view=assigned" className="profile-activity-card">
          <div className="profile-activity-card-title">
            <UserCheck size={16} aria-hidden="true" />
            <span>Asignados a mí</span>
          </div>
          {summary !== null && (
            <span className="profile-activity-badge" title={`${summary.assigned_count} tickets activos`}>
              {summary.assigned_count}
            </span>
          )}
        </Link>
        <Link to="/my-tickets?view=participated" className="profile-activity-card">
          <div className="profile-activity-card-title">
            <History size={16} aria-hidden="true" />
            <span>He participado</span>
          </div>
          {summary !== null && (
            <span className="profile-activity-badge" title={`${summary.participated_count} tickets participados`}>
              {summary.participated_count}
            </span>
          )}
        </Link>
        <Link to="/my-tickets?view=escalations" className="profile-activity-card">
          <div className="profile-activity-card-title">
            <TrendingUp size={16} aria-hidden="true" />
            <span>Mis escalamientos</span>
          </div>
          {summary !== null && (
            <span className="profile-activity-badge" title={`${summary.escalations_count} escalamientos activos`}>
              {summary.escalations_count}
            </span>
          )}
        </Link>
        <Link to="/my-tickets?view=to_verify" className={`profile-activity-card ${summary && summary.to_verify_count > 0 ? 'profile-activity-card--warning' : ''}`}>
          <div className="profile-activity-card-title">
            <ShieldAlert size={16} aria-hidden="true" />
            <span>Por verificar</span>
          </div>
          {summary !== null && (
            <span className={`profile-activity-badge ${summary.to_verify_count > 0 ? 'profile-activity-badge--warning' : ''}`} title={`${summary.to_verify_count} por verificar`}>
              {summary.to_verify_count}
            </span>
          )}
        </Link>
      </div>
    ) : (
      <p className="profile-note">No tienes permisos para acceder a las bandejas de Mis tickets.</p>
    )}
  </section>
}

export function Profile() {
  const auth = useAuth()
  const [profile, setProfile] = useState<OwnProfile | null>(null), [error, setError] = useState<string | null>(null), [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController(); setError(null); setProfile(null)
    getJson<OwnProfile>('/api/auth/profile', controller.signal).then(data => { if (!controller.signal.aborted) setProfile(data) }).catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'No se pudo consultar el perfil') })
    return () => controller.abort()
  }, [retry, auth?.identity.responsible_id, auth?.identity.name, auth?.identity.username, auth?.identity.role_id, auth?.identity.role_revision])
  return <div className="operator-profile">
    <RequestState loading={!profile && !error} error={error} onRetry={() => setRetry(value => value + 1)} />
    {profile && <>
      <h1 className="profile-page-title">Mi perfil</h1>
      <header className="operator-identity" aria-labelledby="operator-name">
        <div className="operator-lcd"><LcdOperatorAvatar name={profile.name} username={profile.username ?? ''} /></div>
        <div className="operator-identity-content">
          <h2 id="operator-name">{profile.name}</h2>
          <p className="operator-username">@{profile.username}</p>
          <dl className="operator-assignment"><div><dt>Puesto operativo</dt><dd>{profile.position?.name ?? 'Sin puesto asignado'}</dd></div><div><dt>Rol de seguridad</dt><dd>{profile.role_name ?? 'Sin rol asignado'}</dd></div></dl>
        </div>
        <span className={`operator-access ${profile.effective_access ? 'is-enabled' : ''}`}>{profile.effective_access ? 'Acceso habilitado' : 'Acceso no habilitado'}</span>
      </header>
      <div className="profile-workspace">
        <section className="profile-panel" aria-labelledby="profile-data-title">
          <h2 id="profile-data-title"><UserRound size={18} aria-hidden="true" />Datos personales</h2>
          <dl className="profile-data"><div><dt>Nombre de usuario</dt><dd>{profile.username}</dd></div><div><dt>Departamento</dt><dd>{profile.department?.name ?? 'Sin asignar'}</dd></div></dl>
          <p className="profile-note">Tu identidad y asignación operativa se administran desde Responsables. Desde aquí puedes cambiar tu contraseña y tus preferencias personales.</p>
        </section>
        <ProfilePreferences profile={profile} />
      </div>
      <section className="profile-panel profile-security" aria-labelledby="profile-security-title">
        <h2 id="profile-security-title"><KeyRound size={18} aria-hidden="true" />Seguridad</h2>
        <p className="profile-note">Cambia tu contraseña personal. Las demás sesiones se cerrarán al confirmar el cambio.</p>
        <PasswordChangeForm />
      </section>
      <ProfileActivity />
      <div className="profile-sessions"><SessionsPanel /></div>
    </>}
  </div>
}
