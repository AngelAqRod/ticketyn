export interface ModuleDefinition {
  path: string
  number: string
  title: string
  group: string
  theme: 'blue' | 'purple' | 'amber' | 'emerald' | 'slate' | 'cyan'
  badge: string
}

export const moduleIdentity: Omit<ModuleDefinition, 'number'>[] = [
  { path: '/my-tickets', title: 'Mis tickets', group: 'Operación', theme: 'blue', badge: 'PERSONAL' },
  { path: '/', title: 'Dashboard', group: 'Operación', theme: 'cyan', badge: 'RESUMEN NOC' },
  { path: '/tickets', title: 'Tickets', group: 'Operación', theme: 'blue', badge: 'CLIENTES' },
  { path: '/internal-tickets', title: 'Tickets internos', group: 'Operación', theme: 'purple', badge: 'INFRAESTRUCTURA NOC' },
  { path: '/changes', title: 'Control de cambios', group: 'Operación', theme: 'cyan', badge: 'MANTENIMIENTOS' },
  { path: '/customers', title: 'Clientes', group: 'Operación', theme: 'blue', badge: 'CATÁLOGO' },
  { path: '/circuits', title: 'Circuitos', group: 'Operación', theme: 'blue', badge: 'RED Y ENLACES' },
  { path: '/distribution-devices', title: 'Equipos de distribución', group: 'Operación', theme: 'purple', badge: 'RED Y DISTRIBUCIÓN' },
  { path: '/reports', title: 'Reportería de tickets', group: 'Análisis', theme: 'blue', badge: 'REPORTES' },
  { path: '/catalogs', title: 'Catálogos', group: 'Administración', theme: 'slate', badge: 'SISTEMA' },
  { path: '/settings', title: 'Configuración', group: 'Administración', theme: 'slate', badge: 'SISTEMA' },
  { path: '/activations', title: 'Activaciones', group: 'Operación', theme: 'emerald', badge: 'FMS ACTIVACIONES' },
  { path: '/capacity-changes', title: 'Cambios de capacidad', group: 'Operación', theme: 'emerald', badge: 'FMS CAPACIDAD' },
  { path: '/circuit-lifecycle', title: 'Bajas y Reactivaciones', group: 'Operación', theme: 'emerald', badge: 'FMS CICLO' },
  { path: '/activation-reports', title: 'Reportería de activaciones', group: 'Análisis', theme: 'emerald', badge: 'FMS REPORTES' },
  { path: '/capacity-reports', title: 'Reportería de cambios de capacidad', group: 'Análisis', theme: 'emerald', badge: 'FMS REPORTES' },
  { path: '/lifecycle-reports', title: 'Reportería de bajas y reactivaciones', group: 'Análisis', theme: 'emerald', badge: 'FMS REPORTES' },
  { path: '/mail-notifications', title: 'Configuración de correo', group: 'Administración', theme: 'slate', badge: 'NOTIFICACIONES' },
  { path: '/mail-templates', title: 'Plantillas de correo', group: 'Administración', theme: 'slate', badge: 'NOTIFICACIONES' },
  { path: '/responsibles', title: 'Responsables', group: 'Administración', theme: 'slate', badge: 'SEGURIDAD' },
  { path: '/security-roles', title: 'Roles y permisos', group: 'Administración', theme: 'slate', badge: 'SEGURIDAD' },
  { path: '/security-sessions', title: 'Sesiones', group: 'Administración', theme: 'slate', badge: 'SEGURIDAD' },
  { path: '/security-audit', title: 'Auditoría de seguridad', group: 'Administración', theme: 'slate', badge: 'SEGURIDAD' },
]

export const moduleGroups = ['Operación', 'Análisis', 'Administración']

export const orderedModuleIdentity: ModuleDefinition[] = moduleGroups
  .flatMap(group => {
    const items = moduleIdentity.filter(item => item.group === group)
    if (group !== 'Administración') return items
    const first = ['/responsibles', '/security-roles', '/security-sessions']
    return [...first.flatMap(path => items.filter(item => item.path === path)), ...items.filter(item => !first.includes(item.path))]
  })
  .map((item, index) => ({ ...item, number: String(index + 1).padStart(2, '0') }))

export function identityFor(pathname: string): ModuleDefinition | undefined {
  return orderedModuleIdentity.find(item => item.path === '/' ? pathname === '/' : pathname === item.path || pathname.startsWith(`${item.path}/`))
}
