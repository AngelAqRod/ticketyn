export const moduleIdentity = [
  { path: '/', number: '01', title: 'Dashboard', group: 'Operación' },
  { path: '/tickets', number: '02', title: 'Tickets', group: 'Operación' },
  { path: '/customers', number: '03', title: 'Clientes', group: 'Operación' },
  { path: '/circuits', number: '04', title: 'Circuitos', group: 'Operación' },
  { path: '/reports', number: '05', title: 'Reportería', group: 'Análisis' },
  { path: '/catalogs', number: '06', title: 'Catálogos', group: 'Administración' },
  { path: '/settings', number: '07', title: 'Configuración', group: 'Administración' },
]
export function identityFor(pathname: string) {
  return moduleIdentity.find((item) => item.path === '/' ? pathname === '/' : pathname === item.path || pathname.startsWith(`${item.path}/`))
}
