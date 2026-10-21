import { useAuth } from '../auth/context'
import { useEffect, useState } from 'react'
import { getJson } from '../api/client'
import type { Account } from '../api/security'
import { PageHeading } from '../components/PageHeading'
import { PasswordChangeForm } from '../components/PasswordChangeForm'
import { SessionsPanel } from '../components/SessionsPanel'
import { RequestState } from '../components/RequestState'

export function Profile() {
  const auth = useAuth()
  const [profile, setProfile] = useState<Account | null>(null), [error, setError] = useState<string | null>(null), [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController(); setError(null)
    getJson<Account>('/api/auth/profile', controller.signal).then(data => { if (!controller.signal.aborted) setProfile(data) }).catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'No se pudo consultar el perfil') })
    return () => controller.abort()
  }, [retry, auth?.identity.role_id, auth?.identity.role_revision])
  return <><PageHeading title="Mi perfil" description="Tu identidad de acceso, contraseña y sesiones activas." />
    <RequestState loading={!profile && !error} error={error} onRetry={() => setRetry(value => value + 1)} />
    {profile && <section className="panel mb-4 p-4 sm:p-6"><dl className="grid gap-4 sm:grid-cols-2"><div><dt className="text-sm text-muted">Responsable</dt><dd>{profile.name}</dd></div><div><dt className="text-sm text-muted">Usuario</dt><dd>{profile.username}</dd></div><div><dt className="text-sm text-muted">Departamento</dt><dd>{profile.department?.name ?? 'Sin asignar'}</dd></div><div><dt className="text-sm text-muted">Puesto operativo</dt><dd>{profile.position?.name ?? 'Sin asignar'}</dd></div><div><dt className="text-sm text-muted">Rol asignado</dt><dd>{profile.role_name ?? 'Sin asignar'}</dd></div></dl></section>}
    <section className="panel mb-4 p-4 sm:p-6"><h2 className="toolbar-heading mb-4">Cambiar contraseña</h2><div className="max-w-lg"><PasswordChangeForm /></div></section>
    <SessionsPanel />
  </>
}
