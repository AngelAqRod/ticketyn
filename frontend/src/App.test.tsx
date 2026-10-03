import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import { jsonResponse, ticket } from './test/fixtures'

function mockApi(healthy = true) {
  vi.stubGlobal('fetch', vi.fn((path: string) => Promise.resolve(path === '/health'
    ? jsonResponse({ status: 'ok' }, healthy ? 200 : 503)
    : path === '/api/settings/ticket-number' ? jsonResponse({ id: 1, prefix: '', separator: '', next_number: 1, padding: 0 })
    : path === '/api/tickets/stats' ? jsonResponse({ total: 123, open: 20, closed: 103 })
    : path.startsWith('/api/tickets') ? jsonResponse([ticket]) : jsonResponse([]))))
}

describe('aplicación', () => {
  it('renderiza el layout, la conexión y estadísticas globales independientes del listado', async () => {
    mockApi()
    render(<MemoryRouter><App /></MemoryRouter>)
    expect(screen.getByText('Ticketyn', { exact: false })).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Navegación principal' })).toBeInTheDocument()
    expect(await screen.findByText('API conectada')).toBeInTheDocument()
    const summary = screen.getByRole('region', { name: 'Estadísticas globales de tickets' })
    expect(within(summary).getByText('Tickets totales')).toBeInTheDocument()
    expect(await within(summary).findByText('123')).toBeInTheDocument()
    expect(within(summary).getByText('20')).toBeInTheDocument()
    expect(within(summary).getByText('103')).toBeInTheDocument()
    expect(screen.queryByText(/primera página de hasta 50/)).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith('/api/tickets/stats', expect.any(Object))
    expect(await screen.findByText('TEST-003')).toBeInTheDocument()
  })
  it('navega a administración, configuración y tickets dentro del layout', async () => {
    mockApi()
    render(<MemoryRouter initialEntries={['/customers']}><App /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: 'Clientes', level: 1 })).toBeInTheDocument()
    const nav = screen.getByRole('navigation')
    for (const title of ['Circuitos', 'Catálogos', 'Configuración']) {
      fireEvent.click(within(nav).getByRole('link', { name: title }))
      expect(screen.getByRole('heading', { name: title === 'Catálogos' ? 'Sectores' : title, level: 1 })).toBeInTheDocument()
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
    await screen.findByText('Error al cargar estadísticas')
    const summary = screen.getByRole('region', { name: 'Estadísticas globales de tickets' })
    expect(within(summary).getAllByText('—')).toHaveLength(3)
  })
  it('muestra estadísticas en carga sin inventar ceros', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    render(<MemoryRouter><App /></MemoryRouter>)
    expect(screen.getByText('Cargando estadísticas...')).toBeInTheDocument()
    const summary = screen.getByRole('region', { name: 'Estadísticas globales de tickets' })
    expect(within(summary).getAllByText('—')).toHaveLength(3)
  })
  it('muestra ceros globales para una base vacía', async () => {
    vi.stubGlobal('fetch', vi.fn((path: string) => Promise.resolve(jsonResponse(
      path === '/health' ? { status: 'ok' } : path === '/api/tickets/stats'
        ? { total: 0, open: 0, closed: 0 } : [],
    ))))
    render(<MemoryRouter><App /></MemoryRouter>)
    const summary = screen.getByRole('region', { name: 'Estadísticas globales de tickets' })
    expect(await within(summary).findAllByText('0')).toHaveLength(3)
    expect(await screen.findByText('No hay tickets')).toBeInTheDocument()
  })
  it('permite recuperar estadísticas sin bloquear los recientes', async () => {
    let failStats = true
    vi.stubGlobal('fetch', vi.fn((path: string) => Promise.resolve(path === '/health'
      ? jsonResponse({ status: 'ok' }) : path === '/api/tickets/stats'
      ? jsonResponse({ total: 123, open: 20, closed: 103 }, failStats ? 503 : 200)
      : path.startsWith('/api/tickets') ? jsonResponse([ticket]) : jsonResponse([]))))
    render(<MemoryRouter><App /></MemoryRouter>)
    expect(await screen.findByText('Error al cargar estadísticas')).toBeInTheDocument()
    expect(await screen.findByText('TEST-003')).toBeInTheDocument()
    failStats = false
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar estadísticas' }))
    expect(await screen.findByText('123')).toBeInTheDocument()
    expect(screen.queryByText('Error al cargar estadísticas')).not.toBeInTheDocument()
  })
  it('conserva los conteos globales aunque fallen los recientes', async () => {
    vi.stubGlobal('fetch', vi.fn((path: string) => Promise.resolve(path === '/health'
      ? jsonResponse({ status: 'ok' }) : path === '/api/tickets/stats'
      ? jsonResponse({ total: 123, open: 20, closed: 103 }) : jsonResponse({}, 503))))
    render(<MemoryRouter><App /></MemoryRouter>)
    expect(await screen.findByText('Error al cargar tickets')).toBeInTheDocument()
    expect(await screen.findByText('123')).toBeInTheDocument()
  })
})
