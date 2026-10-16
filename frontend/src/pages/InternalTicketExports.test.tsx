import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { InternalTickets } from './InternalTickets'
import { internalTicketExportUrl } from '../api/ticketExports'
import { jsonResponse } from '../test/fixtures'

function setup(query = '', mode = 'success') {
  vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn(() => 'blob:internal'); static revokeObjectURL = vi.fn() })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const mock = vi.fn((url: string) => {
    if (url.startsWith('/api/internal-tickets/export/')) {
      if (mode === 'pending') return new Promise<Response>(() => {})
      return Promise.resolve(mode === 'error' ? jsonResponse({ detail: 'No se pudo generar' }, 500) : new Response(new Blob(['file'])))
    }
    return Promise.resolve(jsonResponse([]))
  })
  vi.stubGlobal('fetch', mock)
  render(<MemoryRouter initialEntries={['/internal-tickets' + query]}><InternalTickets /></MemoryRouter>)
  return { mock, click }
}
describe('exportación del listado interno', () => {
  it.each(['pdf', 'xlsx'] as const)('descarga %s con todos los filtros del listado y sin paginación', async format => {
    const { mock, click } = setup('?search=energía&status=CLOSED&sector_id=1&node_id=2&department_id=3&responsible_id=4&incident_type_id=5&provider_id=6&period=custom&from=2026-10-01&to=2026-10-02&offset=50')
    await waitFor(() => expect(mock.mock.calls.some(([url]) => url.startsWith('/api/internal-tickets?'))).toBe(true))
    fireEvent.click(screen.getByRole('button', { name: format === 'pdf' ? 'Exportar PDF' : 'Exportar Excel' }))
    await waitFor(() => expect(click).toHaveBeenCalled())
    const list = new URL(mock.mock.calls.find(([url]) => url.startsWith('/api/internal-tickets?'))![0], 'http://local').searchParams
    const exported = new URL(mock.mock.calls.find(([url]) => url.startsWith(`/api/internal-tickets/export/${format}`))![0], 'http://local').searchParams
    list.delete('limit'); list.delete('offset')
    expect(exported.get('timezone')).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone)
    exported.delete('timezone')
    expect(Object.fromEntries(exported)).toEqual(Object.fromEntries(list))
    click.mockRestore()
  })
  it.each(['', 'none', '7'])('distingue proveedor Todos, Ninguno y específico (%s)', async provider => {
    const { mock, click } = setup(provider ? `?provider_id=${provider}` : '')
    fireEvent.click(screen.getByRole('button', { name: 'Exportar PDF' }))
    await waitFor(() => expect(click).toHaveBeenCalled())
    const query = new URL(mock.mock.calls.find(([url]) => url.startsWith('/api/internal-tickets/export/'))![0], 'http://local').searchParams
    expect(query.get('without_provider')).toBe(provider === 'none' ? 'true' : null)
    expect(query.get('provider_id')).toBe(provider === '7' ? '7' : null)
    click.mockRestore()
  })
  it('bloquea solicitudes repetidas y muestra carga', async () => {
    const { mock, click } = setup('', 'pending')
    const pdf = screen.getByRole('button', { name: 'Exportar PDF' })
    fireEvent.click(pdf); fireEvent.click(pdf)
    expect(await screen.findByText('Generando archivo...')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Exportar Excel' })).toBeDisabled()
    expect(mock.mock.calls.filter(([url]) => url.includes('/export/'))).toHaveLength(1)
    click.mockRestore()
  })
  it('muestra errores y permite reintentar', async () => {
    const { click } = setup('', 'error')
    fireEvent.click(screen.getByRole('button', { name: 'Exportar PDF' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo generar')
    expect(screen.getByRole('button', { name: 'Exportar Excel' })).toBeEnabled()
    click.mockRestore()
  })
  it('elimina paginación al construir la URL compartida', () => {
    const url = internalTicketExportUrl('xlsx', new URLSearchParams('limit=50&offset=100&search=A%26B'), 'UTC')
    expect(Object.fromEntries(new URL(url, 'http://local').searchParams)).toEqual({search:'A&B',timezone:'UTC'})
  })
})
