import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { jsonResponse, ticket } from './test/fixtures'

function mockApi(healthy = true) {
  vi.stubGlobal('fetch', vi.fn((path: string) => Promise.resolve(path === '/health'
    ? jsonResponse({ status: 'ok' }, healthy ? 200 : 503)
    : jsonResponse([ticket]))))
}

describe('aplicación', () => {
  it('renderiza el layout, la conexión y métricas de página explícitas', async () => {
    mockApi()
    render(<MemoryRouter><App /></MemoryRouter>)
    expect(screen.getByText('Ticketyn', { exact: false })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Navegación principal' })).toBeInTheDocument()
    expect(await screen.findByText('API conectada')).toBeInTheDocument()
    const summary = screen.getByRole('region', { name: 'Resumen de la página cargada' })
    expect(within(summary).getByText('Tickets totales')).toBeInTheDocument()
    expect(within(summary).getByText(/No representa un conteo global/)).toBeInTheDocument()
    expect(await screen.findByText('TEST-003')).toBeInTheDocument()
  })
  it('navega a placeholders y tickets dentro del layout', async () => {
    mockApi()
    render(<MemoryRouter initialEntries={['/customers']}><App /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: 'Clientes', level: 1 })).toBeInTheDocument()
    const nav = screen.getByRole('navigation')
    for (const title of ['Circuitos', 'Catálogos', 'Configuración']) {
      fireEvent.click(within(nav).getByRole('link', { name: title }))
      expect(screen.getByRole('heading', { name: title, level: 1 })).toBeInTheDocument()
    }
    fireEvent.click(within(nav).getByRole('link', { name: 'Tickets' }))
    expect(await screen.findByText('TEST-003')).toBeInTheDocument()
    expect(within(nav).getByRole('link', { name: 'Tickets' })).toHaveAttribute('aria-current', 'page')
  })
  it('un health fallido no bloquea la aplicación ni los tickets', async () => {
    mockApi(false)
    render(<MemoryRouter initialEntries={['/tickets']}><App /></MemoryRouter>)
    expect(await screen.findByText('API no disponible')).toBeInTheDocument()
    expect(await screen.findByText('TEST-003')).toBeInTheDocument()
  })
  it('no presenta métricas inventadas cuando falla la API', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    render(<MemoryRouter><App /></MemoryRouter>)
    await screen.findByRole('alert')
    const summary = screen.getByRole('region', { name: 'Resumen de la página cargada' })
    expect(within(summary).getAllByText('—')).toHaveLength(3)
  })
})
