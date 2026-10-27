import { render, screen, waitFor } from '../test/render'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { Dashboard } from './Dashboard'
import { jsonResponse, ticket } from '../test/fixtures'

describe('Dashboard (Electric Blue 2.0)', () => {
  it('renderiza la cabecera industrial con identidad Cian, telemetría y tarjetas oscuras independientes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) => {
        if (url.includes('/api/tickets/stats')) {
          return Promise.resolve(jsonResponse({ total: 10, open: 4, closed: 6 }))
        }
        if (url.includes('/api/tickets/open-overview')) {
          return Promise.resolve(jsonResponse({ generated_at: '2026-06-01T12:00:00Z', open: 0, future_start: 0, unassigned: 0, buckets: { lt_1h: 0, '1_to_4h': 0, '4_to_24h': 0, gt_24h: 0 }, sectors: [] }))
        }
        if (url.includes('/api/tickets')) {
          return Promise.resolve(jsonResponse([ticket]))
        }
        return Promise.resolve(jsonResponse([]))
      })
    )

    const { container } = render(
      <MemoryRouter initialEntries={['/']}>
        <Dashboard />
      </MemoryRouter>
    )

    expect(screen.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.getByText('RESUMEN NOC')).toBeInTheDocument()
    expect(container.querySelector('.page-heading--cyan')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /actualizar/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /nuevo ticket/i })).toHaveAttribute('href', '/tickets/new')

    await waitFor(() => {
      expect(screen.getByText('Panorama de incidencias')).toBeInTheDocument()
      expect(screen.getByText('Tickets totales')).toBeInTheDocument()
      expect(screen.getByText('Tickets abiertos')).toBeInTheDocument()
      expect(screen.getByText('Tickets cerrados')).toBeInTheDocument()
      expect(screen.getByText('10')).toBeInTheDocument()
      expect(screen.getAllByText('4').length).toBeGreaterThanOrEqual(1)
      expect(screen.getByText('6')).toBeInTheDocument()
      expect(container.querySelectorAll('.stat-card')).toHaveLength(3)
      expect(container.querySelector('.metric-strip')).not.toBeInTheDocument()
    })

    expect(screen.getByRole('heading', { level: 2, name: 'Abiertos más antiguos' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /ver todos los abiertos/i })).toHaveAttribute('href', '/tickets?status=OPEN')
  })

  const overview = { generated_at: '2026-06-01T12:00:00Z', open: 10, future_start: 1, unassigned: 4,
    buckets: { lt_1h: 1, '1_to_4h': 2, '4_to_24h': 3, gt_24h: 3 },
    sectors: [{ id: 7, name: 'Sector Norte', count: 6 }, { id: 8, name: 'Sector Sur', count: 3 }] }
  const mockApi = (calls: string[] = []) => vi.stubGlobal('fetch', vi.fn((url: string) => {
    calls.push(url)
    if (url.includes('/api/tickets/stats')) return Promise.resolve(jsonResponse({ total: 10, open: 4, closed: 6 }))
    if (url.includes('/api/tickets/open-overview')) return Promise.resolve(jsonResponse(overview))
    if (url.includes('/api/tickets')) return Promise.resolve(jsonResponse([ticket]))
    return Promise.resolve(jsonResponse([]))
  }))

  it('muestra abiertos por antigüedad con enlaces que reproducen cada filtro', async () => {
    mockApi()
    const { container } = render(<MemoryRouter><Dashboard /></MemoryRouter>)
    expect(await screen.findByRole('heading', { level: 2, name: 'Abiertos por antigüedad' })).toBeInTheDocument()
    const href = (name: RegExp) => screen.getByRole('link', { name }).getAttribute('href')
    await waitFor(() => expect(href(/menos de 1 h/i)).toBe('/tickets?status=OPEN&age_bucket=lt_1h'))
    expect(href(/^1 a 4 h/i)).toBe('/tickets?status=OPEN&age_bucket=1_to_4h')
    expect(href(/^4 a 24 h/i)).toBe('/tickets?status=OPEN&age_bucket=4_to_24h')
    expect(href(/más de 24 h/i)).toBe('/tickets?status=OPEN&age_bucket=gt_24h')
    expect(href(/sin responsable/i)).toBe('/tickets?status=OPEN&unassigned=true')   // sin tramo temporal
    // Barras con escala común: el mayor conteo (3) ocupa el 100 %, 1 ocupa un tercio.
    const widths = [...container.querySelectorAll<HTMLElement>('.age-card-bar > span')].map((bar) => bar.style.width)
    expect(widths.map((width) => Math.round(parseFloat(width)))).toEqual([33, 67, 100, 100])
    expect(screen.getByText(/1 ticket abierto tiene fecha de inicio futura/)).toBeInTheDocument()
  })

  it('pide al backend los cinco abiertos más antiguos y conserva las tres tarjetas superiores', async () => {
    const calls: string[] = []
    mockApi(calls)
    const { container } = render(<MemoryRouter><Dashboard /></MemoryRouter>)
    await screen.findByText('Sector Norte')
    const listing = calls.find((url) => url.startsWith('/api/tickets?'))!
    const query = new URL(listing, 'http://x').searchParams
    expect(Object.fromEntries(query)).toEqual({ status: 'OPEN', order: 'start_at_asc', limit: '5', offset: '0' })
    expect(container.querySelectorAll('.stat-card')).toHaveLength(3)
    expect(screen.getByRole('link', { name: 'Sector Norte' })).toHaveAttribute('href', '/tickets?status=OPEN&sector_id=7')
    expect(screen.getByText('Un sector con varios abiertos a la vez puede indicar un evento común.')).toBeInTheDocument()
    expect(screen.getByText(/El detalle histórico está en/)).toBeInTheDocument()
  })
})
