import { fireEvent, render, screen, within } from '../test/render'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { Layout } from './Layout'
import { jsonResponse } from '../test/fixtures'
import { PermissionProvider } from '../auth/permissions'

function setup(path = '/', permissions?: string[]) {
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(jsonResponse(url === '/health' ? { status: 'ok' } : { version: '0.4.3' }))))
  render(<MemoryRouter initialEntries={[path]}>{permissions ? <PermissionProvider permissions={permissions}><Layout /></PermissionProvider> : <Layout />}</MemoryRouter>)
}

describe('Navegación Electric Blue', () => {
  it('numera correlativamente los módulos en su orden visual sin cambiar rutas', async () => {
    setup()
    await screen.findByText('API conectada')
    const links = within(screen.getByRole('navigation')).getAllByRole('link')
    expect(links.map(link => link.querySelector('.nav-number')?.textContent)).toEqual(Array.from({ length: 22 }, (_, i) => String(i + 1).padStart(2, '0')))
    expect(links.map(link => link.getAttribute('href'))).toEqual(['/', '/tickets', '/internal-tickets', '/changes', '/customers', '/circuits', '/distribution-devices', '/activations', '/capacity-changes', '/circuit-lifecycle', '/reports', '/activation-reports', '/capacity-reports', '/lifecycle-reports', '/responsibles', '/security-roles', '/security-sessions', '/catalogs', '/settings', '/mail-notifications', '/mail-templates', '/security-audit'])
    expect(document.querySelector('#main-navigation')).toHaveClass('md:w-56', 'xl:w-60')
    expect(document.querySelector('.header-brand')).toContainElement(screen.getByText('Ticketyn', { exact: true }).closest('.brand-capsule') as HTMLElement)
  })
  it('conserva el estado activo en detalles y cierra el menú móvil al navegar', async () => {
    setup('/activations/42')
    await screen.findByText('API conectada')
    const nav = screen.getByRole('navigation')
    expect(within(nav).getByRole('link', { name: 'Activaciones' })).toHaveAttribute('aria-current', 'page')
    fireEvent.click(screen.getByRole('button', { name: 'Abrir navegación' }))
    expect(screen.getByRole('button', { name: 'Cerrar navegación' })).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(within(nav).getByRole('link', { name: 'Tickets' }))
    expect(screen.getByRole('button', { name: 'Abrir navegación' })).toHaveAttribute('aria-expanded', 'false')
    expect(within(nav).getByRole('link', { name: 'Tickets' })).toHaveAttribute('aria-current', 'page')
  })
})

it.each(['/distribution-devices', '/distribution-devices/10'])('marca distribución activa y púrpura en %s', async path => {
  setup(path)
  await screen.findByText('API conectada')
  const nav = within(screen.getByRole('navigation', { name: 'Navegación principal' }))
  const link = nav.getByRole('link', { name: 'Equipos de distribución' })
  expect(link).toHaveAttribute('href', '/distribution-devices')
  expect(link).toHaveAttribute('aria-current', 'page')
  expect(link).toHaveClass('nav-link')
  expect(link).toHaveAttribute('data-theme', 'purple')
  expect(link.querySelector(':scope > svg')).toHaveClass('lucide-server')
  expect(nav.getByRole('link', { name: 'Circuitos' })).not.toHaveAttribute('aria-current')
  expect(nav.getByRole('link', { name: 'Circuitos' })).not.toHaveClass('distribution-theme')
})

it.each([{ permissions: [] }, { permissions: ['circuits.view'] }, { permissions: ['distribution_devices.lookup'] }])('oculta distribución sin el permiso view ($permissions)', async ({ permissions }) => {
  setup('/', permissions)
  await screen.findByText('API conectada')
  expect(screen.queryByRole('link', { name: 'Equipos de distribución' })).not.toBeInTheDocument()
})

it('permite entrar con view sin permiso de Circuitos y cierra el menú móvil al navegar', async () => {
  setup('/', ['distribution_devices.view'])
  await screen.findByText('API conectada')
  const nav = within(screen.getByRole('navigation', { name: 'Navegación principal' }))
  expect(nav.queryByRole('link', { name: 'Circuitos' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Abrir navegación' }))
  expect(screen.getByRole('button', { name: 'Cerrar navegación' })).toHaveAttribute('aria-expanded', 'true')
  fireEvent.click(nav.getByRole('link', { name: 'Equipos de distribución' }))
  expect(nav.getByRole('link', { name: 'Equipos de distribución' })).toHaveAttribute('aria-current', 'page')
  expect(screen.getByRole('button', { name: 'Abrir navegación' })).toHaveAttribute('aria-expanded', 'false')
})


it('separa la navegación desplazable de la marca y conserva accesible Configuración', async () => {
  setup()
  await screen.findByText('API conectada')
  const navigation = screen.getByRole('navigation', { name: 'Navegación principal' })
  expect(navigation).toHaveClass('sidebar-navigation-scroll')
  expect(navigation).toHaveAttribute('tabindex', '0')
  expect(navigation).not.toHaveClass('md:sticky')
  expect(navigation).not.toContainElement(document.querySelector('.brand-capsule') as HTMLElement)
  const settings = within(navigation).getByRole('link', { name: 'Configuración' })
  settings.focus()
  expect(settings).toHaveFocus()
  fireEvent.click(settings)
  expect(settings).toHaveAttribute('aria-current', 'page')
})

it('separa configuración y plantillas de correo en Administración', async () => {
  setup('/mail-templates')
  await screen.findByText('API conectada')
  const nav = screen.getByRole('navigation')
  expect(within(nav).getByRole('link', { name: 'Configuración de correo' })).toHaveAttribute('href', '/mail-notifications')
  const templates = within(nav).getByRole('link', { name: 'Plantillas de correo' })
  expect(templates).toHaveAttribute('aria-current', 'page')
  fireEvent.click(within(nav).getByRole('link', { name: 'Configuración de correo' }))
  expect(within(nav).getByRole('link', { name: 'Configuración de correo' })).toHaveAttribute('aria-current', 'page')
})


it.each([
  ['/', 'Dashboard', 'cyan'],
  ['/tickets/new', 'Tickets', 'blue'],
  ['/tickets/42/edit', 'Tickets', 'blue'],
  ['/internal-tickets', 'Tickets internos', 'purple'],
  ['/internal-tickets/42/edit', 'Tickets internos', 'purple'],
  ['/changes', 'Control de cambios', 'amber'],
  ['/changes/new', 'Control de cambios', 'amber'],
  ['/changes/42/edit', 'Control de cambios', 'amber'],
  ['/circuits/42', 'Circuitos', 'blue'],
  ['/distribution-devices/42', 'Equipos de distribución', 'purple'],
  ['/activations/42', 'Activaciones', 'emerald'],
  ['/activation-reports', 'Reportería de activaciones', 'emerald'],
  ['/security-audit', 'Auditoría de seguridad', 'slate'],
])('resuelve una sola selección con identidad del módulo en %s', async (path, title, theme) => {
  setup(path)
  await screen.findByText('API conectada')
  const nav = screen.getByRole('navigation')
  const selected = within(nav).getByRole('link', { name: title })
  expect(selected).toHaveAttribute('aria-current', 'page')
  expect(selected).toHaveAttribute('data-theme', theme)
  expect(nav.querySelectorAll('[aria-current="page"]')).toHaveLength(1)
  expect(selected).not.toHaveClass('distribution-theme')
})
