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

    expect(screen.getByRole('heading', { level: 2, name: 'Tickets recientes' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /ver todos los tickets/i })).toHaveAttribute('href', '/tickets')
  })
})
