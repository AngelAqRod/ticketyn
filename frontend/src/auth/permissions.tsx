import { createContext, type ReactNode, useContext, useMemo } from 'react'

export interface Access {
  can: (...codes: string[]) => boolean
  any: (...codes: string[]) => boolean
  permissions: readonly string[]
}
const denied: Access = { can: () => false, any: () => false, permissions: [] }
export const PermissionContext = createContext<Access>(denied)
export function PermissionProvider({ permissions, children }: { permissions: readonly string[]; children: ReactNode }) {
  const value = useMemo(() => {
    const grants = new Set(permissions)
    return { permissions, can: (...codes: string[]) => codes.every(code => grants.has(code)), any: (...codes: string[]) => codes.some(code => grants.has(code)) }
  }, [permissions])
  return <PermissionContext.Provider value={value}>{children}</PermissionContext.Provider>
}
export function usePermissions() { return useContext(PermissionContext) }
export function Can({ permission, anyOf, children, fallback = null }: { permission?: string; anyOf?: string[]; children: ReactNode; fallback?: ReactNode }) {
  const access = usePermissions()
  return (permission ? access.can(permission) : anyOf ? access.any(...anyOf) : false) ? children : fallback
}

const catalogs = ['sectors', 'departments', 'incident_types', 'nodes', 'positions', 'escalation_reasons', 'service_types', 'deactivation_reasons', 'cpe_models', 'internal_incident_types', 'providers', 'change_completion_types', 'change_types']
export function catalogModule(kind: string) { return ['customers', 'circuits'].includes(kind) ? kind : 'catalogs.' + kind.replaceAll('-', '_') }
export function routeAllowed(path: string, access: Access): boolean {
  if (path === '/profile' || path === '/login') return true
  if (path === '/') return access.can('dashboard.view')
  const root = path.split('/')[1]
  const modules: Record<string, string> = { tickets: 'tickets', 'internal-tickets': 'internal_tickets', changes: 'changes', customers: 'customers', circuits: 'circuits', activations: 'activations', 'capacity-changes': 'capacity_changes', 'circuit-lifecycle': 'lifecycle' }
  if (root in modules) {
    const module = modules[root]
    if (path.endsWith('/new')) return access.can(module + '.create')
    if (path.endsWith('/edit')) return access.any(module+'.edit', ...(['tickets','internal_tickets'].includes(module)?[module+'.close', ...(module==='tickets'?['tickets.link']:[])]:module==='changes'?['changes.execute','changes.link']:[]))
    return access.can(module + '.view')
  }
  if (root === 'responsibles') return access.any('catalogs.responsibles.view', 'accounts.manage')
  if (root === 'security-roles') return access.can('roles.manage')
  if (root === 'security-sessions') return access.can('sessions.manage')
  if (root === 'security-audit') return access.can('audit.view')
  if (root === 'catalogs') return access.any(...catalogs.map(key => `catalogs.${key}.view`))
  if (root === 'settings') return access.any(...['ticket_number', 'internal_ticket_number', 'activation_number', 'change_number'].map(key => `settings.${key}.view`))
  if (root === 'mail-notifications') return access.any('mail.transport.view', 'mail.oauth.view', 'mail.events.view', 'mail.processor.view')
  if (root === 'mail-templates') return access.can('mail.templates.view')
  if (root === 'reports') return access.any(...['tickets', 'internal_tickets', 'changes'].flatMap(key => [`reports.${key}.view`, `reports.${key}.export`]))
  const reports: Record<string, string> = { 'activation-reports': 'activations', 'capacity-reports': 'capacity_changes', 'lifecycle-reports': 'lifecycle' }
  if (root in reports) return access.any(`reports.${reports[root]}.view`, `reports.${reports[root]}.export`)
  return false
}
export const MODULE_PATHS = ['/', '/tickets', '/internal-tickets', '/changes', '/customers', '/circuits', '/activations', '/capacity-changes', '/circuit-lifecycle', '/reports', '/activation-reports', '/capacity-reports', '/lifecycle-reports', '/catalogs', '/settings', '/mail-notifications', '/mail-templates', '/responsibles', '/security-roles', '/security-sessions', '/security-audit']
export function firstAllowed(access: Access) { return MODULE_PATHS.find(path => routeAllowed(path, access)) ?? '/profile' }
