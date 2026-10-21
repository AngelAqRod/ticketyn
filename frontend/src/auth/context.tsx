import { createContext, useContext } from 'react'

export interface Identity {
  responsible_id: number; username: string; name: string; role: string | null
  password_change_required: boolean; operational_access: boolean
  permissions: string[]; role_id?: number
  expires_in: number; warning_seconds: number; role_revision: number
}
export interface AuthState {
  identity: Identity
  busy: boolean
  logout: () => Promise<void>
  accept: (identity: Identity) => void
  refresh: () => Promise<void>
}
export const AuthContext = createContext<AuthState | null>(null)
export const useAuth = () => useContext(AuthContext)
