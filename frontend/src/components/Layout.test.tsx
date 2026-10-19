import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { Layout } from './Layout'
import { jsonResponse } from '../test/fixtures'

function setup(path = '/') {
  vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(jsonResponse(url === '/health' ? { status: 'ok' } : { version: '0.4.3' }))))
  render(<MemoryRouter initialEntries={[path]}><Layout /></MemoryRouter>)
}

describe('Navegación Electric Blue', () => {
  it('numera correlativamente los módulos en su orden visual sin cambiar rutas', async () => {
    setup()
    await screen.findByText('API conectada')
    const links = within(screen.getByRole('navigation')).getAllByRole('link')
    expect(links.map(link => link.querySelector('.nav-number')?.textContent)).toEqual(Array.from({ length: 17 }, (_, i) => String(i + 1).padStart(2, '0')))
    expect(links.map(link => link.getAttribute('href'))).toEqual(['/', '/tickets', '/internal-tickets', '/changes', '/customers', '/circuits', '/activations', '/capacity-changes', '/circuit-lifecycle', '/reports', '/activation-reports', '/capacity-reports', '/lifecycle-reports', '/catalogs', '/settings', '/mail-notifications', '/mail-templates'])
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
