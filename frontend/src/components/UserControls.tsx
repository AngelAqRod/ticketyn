import { Link } from 'react-router'
import { LogOut, UserRound } from 'lucide-react'
import { useAuth } from '../auth/context'

export function UserControls() {
  const auth = useAuth()
  if (!auth) return null
  return <div className="header-user-controls" aria-label="Sesión actual">
    <span className="header-user-name" title={auth.identity.name}>{auth.identity.name}</span>
    <Link className="button-secondary header-user-action" to="/profile" aria-label="Mi perfil" title="Mi perfil"><UserRound size={14} aria-hidden="true" /><span>Mi perfil</span></Link>
    <button className="button-secondary header-user-action header-user-logout" disabled={auth.busy} onClick={() => void auth.logout()} aria-label="Cerrar sesión" title="Cerrar sesión"><LogOut size={14} aria-hidden="true" /><span>Cerrar sesión</span></button>
  </div>
}
