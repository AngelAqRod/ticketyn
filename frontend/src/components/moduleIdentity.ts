export const moduleIdentity = [
  { path: '/', number: '01', title: 'Dashboard', group: 'Operación' },
  { path: '/tickets', number: '02', title: 'Tickets', group: 'Operación' },
  { path: '/customers', number: '03', title: 'Clientes', group: 'Operación' },
  { path: '/circuits', number: '04', title: 'Circuitos', group: 'Operación' },
  { path: '/reports', number: '05', title: 'Reportería de tickets', group: 'Análisis' },
  { path: '/catalogs', number: '06', title: 'Catálogos', group: 'Administración' },
  { path: '/settings', number: '07', title: 'Configuración', group: 'Administración' },
  { path: '/activations', number: '08', title: 'Activaciones', group: 'Operación' },
  { path: '/capacity-changes', number: '09', title: 'Cambios de capacidad', group: 'Operación' },
  { path: '/circuit-lifecycle', number: '10', title: 'Bajas y Reactivaciones', group: 'Operación' },
  { path: '/activation-reports', number: '11', title: 'Reportería de activaciones', group: 'Análisis' },
  { path: '/capacity-reports', number: '12', title: 'Reportería de cambios de capacidad', group: 'Análisis' },
  { path: '/lifecycle-reports', number: '13', title: 'Reportería de bajas y reactivaciones', group: 'Análisis' },
]
export function identityFor(pathname: string) {
  return moduleIdentity.find((item) => item.path === '/' ? pathname === '/' : pathname === item.path || pathname.startsWith(`${item.path}/`))
}
