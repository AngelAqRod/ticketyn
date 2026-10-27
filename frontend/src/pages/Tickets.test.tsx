import { fireEvent, render as renderReact, screen, waitFor, within } from '../test/render'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Tickets } from './Tickets'
import { jsonResponse, ticket } from '../test/fixtures'

const render = (element: ReactElement) => renderReact(element, { wrapper: MemoryRouter })

// Por omisión Nodo, Tipo y Fin están ocultos; estas pruebas necesitan todas las columnas.
beforeEach(() => localStorage.setItem('ticketyn_ticket_hidden_columns', '[]'))
afterEach(() => localStorage.clear())

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
      ticket,
      { ...ticket, id: 2, reference: 'TEST-004', status: 'CLOSED', end_at: '2026-01-01T13:02:00Z', duration_seconds: 3720 },
      { ...ticket, id: 3, reference: 'TEST-005', status: 'CLOSED', end_at: null, duration_seconds: null },
    ] : []))))
    render(<Tickets />)
    expect(await screen.findByRole('table')).toBeInTheDocument()
    expect(screen.getByText('TEST-003')).toBeInTheDocument()
    expect(screen.getByText('TEST-005')).toBeInTheDocument()
    expect(within(screen.getByRole('table')).getByText('Abierto')).toBeInTheDocument()
    expect(within(screen.getByRole('table')).getAllByText('Cerrado')).toHaveLength(2)
    // Los abiertos muestran su antigüedad (tiempo transcurrido), no «En curso».
    expect(screen.getByTitle('Tiempo transcurrido desde el inicio')).toHaveTextContent(/^\d+ d/)
    expect(screen.getByText('Sin fecha de fin')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
    expect(screen.getByText('1 h 2 min')).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'id' })).not.toBeInTheDocument()
  })
  it('usa X-Total-Count para el total, el rango y la última página', async () => {
    const page = (offset: number) => new Response(JSON.stringify(Array.from({ length: offset === 150 ? 33 : 50 }, (_, i) => ({ ...ticket, id: offset + i + 1, reference: `TEST-${offset + i + 1}` }))), { status: 200, headers: { 'Content-Type': 'application/json', 'X-Total-Count': '183' } })
    const fetchMock = vi.fn((path: string) => Promise.resolve(path.startsWith('/api/tickets?') ? page(Number(new URL(path, 'http://x').searchParams.get('offset'))) : jsonResponse([])))
    vi.stubGlobal('fetch', fetchMock)
    render(<Tickets />)
    expect(await screen.findByText('Página 1 de 4 · Registros 1–50 de 183')).toBeInTheDocument()
    expect(screen.getByText(/Mostrando 1–50 de 183/)).toBeInTheDocument()
    expect(screen.getByText('Fechas en America/Guatemala')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Siguiente' })).toBeEnabled()
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

describe('columnas opcionales y filtros rápidos', () => {
  const listing = (path: string) => Promise.resolve(jsonResponse(path.startsWith('/api/tickets?') ? [ticket] : []))
  it('oculta Nodo, Tipo y Fin por omisión y conserva la preferencia', async () => {
    localStorage.clear()
    vi.stubGlobal('fetch', vi.fn(listing))
    render(<Tickets />)
    const table = within(await screen.findByRole('table'))
    expect(table.queryByRole('columnheader', { name: 'Nodo' })).not.toBeInTheDocument()
    expect(table.getByRole('columnheader', { name: 'Sector' })).toBeInTheDocument()
    fireEvent.click(within(screen.getByRole('group', { name: 'Columnas opcionales' })).getByLabelText('Mostrar Nodo'))
    expect(table.getByRole('columnheader', { name: 'Nodo' })).toBeInTheDocument()
    expect(localStorage.getItem('ticketyn_ticket_hidden_columns')).toBe('["type","end"]')
  })
  it('los filtros rápidos consultan al backend y reflejan la selección en la URL', async () => {
    const mock = vi.fn(listing)
    vi.stubGlobal('fetch', mock)
    render(<Tickets />)
    await screen.findByRole('table')
    fireEvent.click(screen.getByRole('button', { name: 'Sin responsable' }))
    fireEvent.click(screen.getByRole('button', { name: 'Más de 24 h' }))
    await waitFor(() => expect(mock.mock.calls.some(([path]) => /status=OPEN/.test(path) && /unassigned=true/.test(path) && /age_bucket=gt_24h/.test(path))).toBe(true))
    expect(screen.getByRole('button', { name: 'Abiertos' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Más de 24 h' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('Antigüedad: Más de 24 h')).toBeInTheDocument()
    // Cerrados apaga ambos interruptores: no quedan condiciones contradictorias.
    fireEvent.click(screen.getByRole('button', { name: 'Cerrados' }))
    await waitFor(() => expect(mock.mock.calls.at(-1)![0]).toMatch(/status=CLOSED/))
    expect(mock.mock.calls.at(-1)![0]).not.toMatch(/unassigned|age_bucket/)
    expect(screen.getByRole('button', { name: 'Sin responsable' })).toHaveAttribute('aria-pressed', 'false')
  })
  it('un tramo llegado desde el Dashboard aparece en filtros activos y puede quitarse', async () => {
    const mock = vi.fn(listing)
    vi.stubGlobal('fetch', mock)
    renderReact(<MemoryRouter initialEntries={['/tickets?status=OPEN&age_bucket=1_to_4h']}><Tickets /></MemoryRouter>)
    expect(await screen.findByText('Antigüedad: 1 a 4 h')).toBeInTheDocument()
    expect(mock.mock.calls.some(([path]) => /age_bucket=1_to_4h/.test(path))).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Quitar filtro Antigüedad: 1 a 4 h' }))
    await waitFor(() => expect(screen.queryByText('Antigüedad: 1 a 4 h')).not.toBeInTheDocument())
    expect(mock.mock.calls.at(-1)![0]).not.toMatch(/age_bucket/)
  })
})

describe('barra de filtros: chips, limpieza y navegación', () => {
  const listing = (path: string) => Promise.resolve(jsonResponse(path.startsWith('/api/tickets?') ? [ticket] : []))
  const lastTicketsCall = (mock: ReturnType<typeof vi.fn>) => mock.mock.calls.map(([path]) => String(path)).filter((path) => path.startsWith('/api/tickets?')).at(-1)!
  const at = (entry: string) => renderReact(<MemoryRouter initialEntries={[entry]}><Tickets /></MemoryRouter>)

  it('quitar un chip conserva los demás filtros y reinicia la paginación', async () => {
    const mock = vi.fn(listing)
    vi.stubGlobal('fetch', mock)
    at('/tickets?status=OPEN&search=abc&customer_id=3&offset=50')
    await screen.findByRole('table')
    expect(lastTicketsCall(mock)).toMatch(/offset=50/)
    fireEvent.click(screen.getByRole('button', { name: 'Quitar filtro Búsqueda: abc' }))
    await waitFor(() => expect(lastTicketsCall(mock)).not.toMatch(/search=/))
    expect(lastTicketsCall(mock)).toMatch(/status=OPEN/)
    expect(lastTicketsCall(mock)).toMatch(/customer_id=3/)
    expect(lastTicketsCall(mock)).not.toMatch(/offset=50/)
  })
  it('«Limpiar todo» funciona con el panel cerrado, deja una sola acción y reinicia la paginación', async () => {
    const mock = vi.fn(listing)
    vi.stubGlobal('fetch', mock)
    at('/tickets?status=CLOSED&node_id=4&sector_id=2&offset=50')
    await screen.findByRole('table')
    expect(screen.getByRole('button', { name: 'Filtros (2)' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getAllByRole('button', { name: /Limpiar/ })).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar todo' }))
    await waitFor(() => expect(lastTicketsCall(mock)).not.toMatch(/status=|node_id|sector_id|offset=50/))
    expect(screen.queryByRole('button', { name: /Limpiar/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Filtros' })).toBeInTheDocument()
  })
  it('el estado vacío conserva los filtros y el acceso a limpiarlos', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse([]))))
    at('/tickets?search=nada')
    expect(await screen.findByText('Búsqueda: nada')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Limpiar todo' })).toBeInTheDocument()
  })
})
