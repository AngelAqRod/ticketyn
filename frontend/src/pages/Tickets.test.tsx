import { fireEvent, render as renderReact, screen, waitFor, within } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { Tickets } from './Tickets'
import { jsonResponse, ticket } from '../test/fixtures'

const render = (element: ReactElement) => renderReact(element, { wrapper: MemoryRouter })

describe('listado de tickets', () => {
  it('muestra el estado de carga', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    render(<Tickets />)
    expect(screen.getByText('Cargando...')).toBeInTheDocument()
  })
  it('muestra el estado vacío', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse([]))))
    render(<Tickets />)
    expect(await screen.findByText('No hay tickets')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
  })
  it('muestra tickets, estados, fin y duración', async () => {
    vi.stubGlobal('fetch', vi.fn((path: string) => Promise.resolve(jsonResponse(path.startsWith('/api/tickets?') ? [
      ticket, { ...ticket, id: 2, reference: 'TEST-004', status: 'CLOSED', end_at: '2026-01-01T13:02:00Z', duration_seconds: 3720 },
    ] : []))))
    render(<Tickets />)
    expect(await screen.findByRole('table')).toBeInTheDocument()
    expect(screen.getByText('TEST-003')).toBeInTheDocument()
    expect(within(screen.getByRole('table')).getByText('Abierto')).toBeInTheDocument()
    expect(within(screen.getByRole('table')).getByText('Cerrado')).toBeInTheDocument()
    expect(screen.getByText('En curso')).toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.getByText('1 h 2 min')).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'id' })).not.toBeInTheDocument()
  })
  it('muestra el error y permite reintentar', async () => {
    let failed = false
    const fetchMock = vi.fn((path: string) => {
      if (!path.startsWith('/api/tickets?')) return Promise.resolve(jsonResponse([]))
      if (!failed) { failed = true; return Promise.reject(new TypeError('offline')) }
      return Promise.resolve(jsonResponse([ticket]))
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<Tickets />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Error al cargar tickets')
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(await screen.findByText('TEST-003')).toBeInTheDocument()
  })
  it('avanza por offset y permite regresar de una página vacía', async () => {
    const page = Array.from({ length: 50 }, (_, i) => ({ ...ticket, id: i + 1, reference: `T-${i + 1}` }))
    const fetchMock = vi.fn().mockImplementation((path: string) => Promise.resolve(jsonResponse(!path.startsWith('/api/tickets?') || path.includes('offset=50') ? [] : page)))
    vi.stubGlobal('fetch', fetchMock)
    render(<Tickets />)
    await screen.findByText('T-1')
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
    await screen.findByText('No hay tickets')
    expect(fetchMock).toHaveBeenLastCalledWith('/api/tickets?limit=50&offset=50', expect.any(Object))
    fireEvent.click(screen.getByRole('button', { name: 'Anterior' }))
    await waitFor(() => expect(screen.getByText('T-1')).toBeInTheDocument())
  })
})

it('muestra Nodo derivado y Responsable, conservando Sin asignar para NULL', async () => {
  const rows = [{ ...ticket, node: { id: 1, name: 'Nodo visible', active: false }, responsible: { id: 1, name: 'Responsable histórico', active: false } }, { ...ticket, id: 2, reference: 'TEST-NULL', node: null, responsible: null }]
  const mock = vi.fn((path: string) => Promise.resolve(jsonResponse(path.startsWith('/api/tickets?') ? rows : [])))
  vi.stubGlobal('fetch', mock)
  render(<Tickets />)
  const table = within(await screen.findByRole('table'))
  expect(table.getByText('Nodo visible')).toBeInTheDocument()
  expect(table.getByText('Responsable histórico')).toBeInTheDocument()
  expect(table.getAllByText('Sin asignar')).toHaveLength(2)
  expect(mock.mock.calls.some(([path]) => /^\/api\/(nodes|responsibles)\/\d/.test(path))).toBe(false)
})
