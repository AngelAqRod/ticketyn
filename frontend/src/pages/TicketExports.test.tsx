import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { Tickets } from './Tickets'
import { ticketExportUrl } from '../api/ticketExports'
import { jsonResponse, ticket } from '../test/fixtures'

function setup(path: string, options: { error?: boolean; pending?: boolean } = {}) {
  vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn(() => 'blob:ticket'); static revokeObjectURL = vi.fn() })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const mock = vi.fn((path: string) => {
    if (path.startsWith('/api/tickets/export/')) {
      if (options.pending) return new Promise<Response>(() => {})
      return Promise.resolve(options.error ? jsonResponse({ detail: [{ loc: ['query', 'from'], msg: 'Fecha inválida' }] }, 422) : new Response(new Blob(['file'])))
    }
    return Promise.resolve(jsonResponse(path.startsWith('/api/tickets?') ? [ticket] : []))
  })
  vi.stubGlobal('fetch', mock)
  render(<MemoryRouter initialEntries={[path]}><Tickets /></MemoryRouter>)
  return { mock, click }
}
describe('exportación de tickets', () => {
  it.each(['pdf', 'xlsx'] as const)('descarga %s sin filtros ni paginación', async (format) => {
    const { mock, click } = setup('/tickets?offset=50')
    await screen.findByText(ticket.reference)
    fireEvent.click(screen.getByRole('button', { name: format === 'pdf' ? 'Exportar PDF' : 'Exportar Excel' }))
    await waitFor(() => expect(click).toHaveBeenCalled())
    const path = mock.mock.calls.find(([path]) => path.startsWith(`/api/tickets/export/${format}`))![0]
    const params = new URL(path, 'http://local').searchParams
    expect([...params.keys()]).toEqual(['timezone'])
    expect(params.get('timezone')).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone)
    click.mockRestore()
  })
  it('exporta exactamente los filtros y conserva los límites temporales locales', async () => {
    const { mock, click } = setup('/tickets?search=prueba&status=OPEN&customer_id=1&circuit_id=2&sector_id=3&department_id=4&incident_type_id=5&from=2026-10-01&to=2026-10-02&offset=50')
    await screen.findByText(ticket.reference)
    fireEvent.click(screen.getByRole('button', { name: 'Exportar Excel' }))
    await waitFor(() => expect(click).toHaveBeenCalled())
    const query = new URL(mock.mock.calls.find(([path]) => path.startsWith('/api/tickets/export/xlsx'))![0], 'http://local').searchParams
    for (const [key, value] of Object.entries({ search: 'prueba', status: 'OPEN', customer_id: '1', circuit_id: '2', sector_id: '3', department_id: '4', incident_type_id: '5' })) expect(query.get(key)).toBe(value)
    expect(query.get('from')).toBe(new Date(2026, 9, 1).toISOString())
    expect(query.get('to')).toBe(new Date(2026, 9, 3).toISOString())
    expect(query.has('offset')).toBe(false); expect(query.has('limit')).toBe(false)
    click.mockRestore()
  })
  it('deshabilita descargas mientras genera el archivo', async () => {
    const { click } = setup('/tickets', { pending: true })
    fireEvent.click(screen.getByRole('button', { name: 'Exportar PDF' }))
    expect(await screen.findByText('Generando archivo...')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Exportar Excel' })).toBeDisabled()
    click.mockRestore()
  })
  it('normaliza errores de exportación sin perder el listado', async () => {
    const { click } = setup('/tickets', { error: true })
    await screen.findByText(ticket.reference)
    fireEvent.click(screen.getByRole('button', { name: 'Exportar PDF' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Fecha inválida')
    expect(screen.getByText(ticket.reference)).toBeInTheDocument()
    click.mockRestore()
  })
  it('quita limit/offset incluso si el cliente recibe una query paginada', () => {
    const url = new URL(ticketExportUrl('pdf', { limit: 50, offset: 100, search: 'A&B' }, 'UTC'), 'http://local')
    expect(Object.fromEntries(url.searchParams)).toEqual({ search: 'A&B', timezone: 'UTC' })
  })
})
