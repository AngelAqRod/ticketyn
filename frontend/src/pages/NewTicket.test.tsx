import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { jsonResponse, ticket } from '../test/fixtures'
import { localDateTimeValue } from '../lib/datetime'

const customers = [
  { id: 1, customer_code: 'SGgt-00000', name: 'Cliente de prueba', active: true, created_at: ticket.created_at },
  { id: 2, customer_code: 'OTHER', name: 'Otro cliente', active: true, created_at: ticket.created_at },
]
const circuit = { id: 5, customer_id: 1, circuit_code: 'SGgt-00000.00000', description: 'Internet principal', active: true, created_at: ticket.created_at }
const named = [{ id: 1, name: 'Catálogo de prueba', active: true, created_at: ticket.created_at }]

function mockApi(post?: (options: RequestInit) => Promise<Response>) {
  const mock = vi.fn((path: string, options?: RequestInit) => {
    if (options?.method === 'POST') return post ? post(options) : Promise.resolve(jsonResponse({ ...ticket, reference: 'TEST-002' }, 201))
    if (path === '/health') return Promise.resolve(jsonResponse({ status: 'ok' }))
    if (path.startsWith('/api/customers')) return Promise.resolve(jsonResponse(customers))
    if (path.startsWith('/api/circuits')) return Promise.resolve(jsonResponse(path.includes('customer_id=1') ? [circuit] : [{ ...circuit, id: 6, customer_id: 2, circuit_code: 'OTHER-CIRCUIT' }]))
    if (/^\/api\/(sectors|departments|incident-types|nodes|responsibles)/.test(path)) return Promise.resolve(jsonResponse(named))
    return Promise.resolve(jsonResponse([ticket]))
  })
  vi.stubGlobal('fetch', mock)
  return mock
}

function renderNewTicket() {
  return render(<MemoryRouter initialEntries={['/tickets/new']}><App /></MemoryRouter>)
}

async function fillRequired() {
  await waitFor(() => expect(screen.getByLabelText(/^Cliente\s*\*?$/)).toBeEnabled())
  fireEvent.change(screen.getByLabelText(/^Título\s*\*?$/), { target: { value: 'Incidencia retroactiva' } })
  fireEvent.change(screen.getByLabelText(/^Descripción\s*\*?$/), { target: { value: 'Sin conexión' } })
  fireEvent.click(screen.getByLabelText(/^Cliente\s*\*?$/))
  fireEvent.click(await screen.findByRole('option', { name: 'SGgt-00000 — Cliente de prueba' }))
  await waitFor(() => expect(screen.getByLabelText(/^Circuito\s*\*?$/)).toBeEnabled())
  fireEvent.click(screen.getByLabelText(/^Circuito\s*\*?$/))
  await screen.findByRole('option', { name: 'SGgt-00000.00000 — Internet principal' })
  fireEvent.click(screen.getByRole('option', { name: 'SGgt-00000.00000 — Internet principal' }))
  for (const label of ['Sector', 'Departamento', 'Tipo de incidencia']) {
    fireEvent.change(screen.getByRole('combobox', { name: new RegExp('^' + label + '\\s*\\*?$') }), { target: { value: '1' } })
  }
}

afterEach(() => vi.useRealTimers())

describe('creación de tickets', () => {
  it('renderiza la ruta, catálogos activos y fechas iniciales', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 9, 2, 16, 20, 40))
    const fetchMock = mockApi()
    renderNewTicket()
    expect(screen.getByRole('heading', { name: 'Nuevo ticket' })).toBeInTheDocument()
    expect(screen.getByLabelText(/^Inicio\s*\*?$/)).toHaveValue('2026-10-02T16:20')
    expect(screen.getByLabelText('Fin', { exact: true })).toHaveValue('')
    expect(screen.getByLabelText(/^Estado\s*\*?$/)).toHaveValue('OPEN')
    expect(screen.getByLabelText(/^Circuito\s*\*?$/)).toBeDisabled()
    await waitFor(() => expect(screen.getByLabelText(/^Cliente\s*\*?$/)).toBeEnabled())
    for (const path of ['customers', 'sectors', 'departments', 'incident-types']) {
      expect(fetchMock).toHaveBeenCalledWith(`/api/${path}?include_inactive=false&limit=200&offset=0`, expect.any(Object))
    }
  })
  it('los dos botones Ahora actualizan fechas editables y no envían', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 9, 2, 16, 20))
    const fetchMock = mockApi()
    renderNewTicket()
    await fillRequired()
    vi.setSystemTime(new Date(2026, 9, 2, 17, 35))
    for (const label of ['Inicio', 'Fin']) {
      const button = screen.getByRole('button', { name: `Ahora de ${label}` })
      expect(button).toHaveAttribute('type', 'button')
      fireEvent.click(button)
      const input = screen.getByLabelText(new RegExp('^' + label + '\\s*\\*?$'))
      expect(input).toHaveValue('2026-10-02T17:35')
      fireEvent.change(input, { target: { value: '2025-01-02T08:15' } })
      expect(input).toHaveValue('2025-01-02T08:15')
    }
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false)
  })
  it('filtra circuitos por ID y limpia la selección al cambiar cliente', async () => {
    const fetchMock = mockApi()
    renderNewTicket()
    await fillRequired()
    expect(screen.getByLabelText(/^Circuito\s*\*?$/)).toHaveValue('SGgt-00000.00000 — Internet principal')
    expect(fetchMock).toHaveBeenCalledWith('/api/circuits?customer_id=1&include_inactive=false&limit=200&offset=0', expect.any(Object))
    fireEvent.click(screen.getByLabelText(/^Cliente\s*\*?$/))
    fireEvent.click(screen.getByRole('option', { name: 'OTHER — Otro cliente' }))
    expect(screen.getByLabelText(/^Circuito\s*\*?$/)).toHaveValue('')
    await waitFor(() => expect(screen.getByLabelText(/^Circuito\s*\*?$/)).toBeEnabled())
    fireEvent.click(screen.getByLabelText(/^Circuito\s*\*?$/))
    await screen.findByRole('option', { name: 'OTHER-CIRCUIT — Internet principal' })
    expect(screen.queryByRole('option', { name: 'SGgt-00000.00000 — Internet principal' })).not.toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/circuits?customer_id=2&include_inactive=false&limit=200&offset=0', expect.any(Object))
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar Cliente' }))
    expect(screen.getByLabelText(/^Circuito\s*\*?$/)).toBeDisabled()
  })
  it('envía IDs y la fecha local como el mismo instante ISO, fin null y confirma referencia', async () => {
    let payload: unknown
    mockApi(async (options) => {
      payload = JSON.parse(String(options.body))
      return jsonResponse({ ...ticket, reference: 'TEST-002' }, 201)
    })
    renderNewTicket()
    await fillRequired()
    fireEvent.change(screen.getByLabelText(/^Inicio\s*\*?$/), { target: { value: '2026-10-02T16:20' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText('Ticket TEST-002 creado correctamente.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Tickets', level: 1 })).toBeInTheDocument()
    expect(payload).toEqual({
      title: 'Incidencia retroactiva', description: 'Sin conexión', customer_id: 1, circuit_id: 5,
      sector_id: 1, department_id: 1, incident_type_id: 1, responsible_id: null,
      start_at: new Date(2026, 9, 2, 16, 20).toISOString(), end_at: null, status: 'OPEN',
    })
  })
  it('permite crear CLOSED con fin y fechas introducidas manualmente', async () => {
    let payload: unknown
    mockApi(async (options) => { payload = JSON.parse(String(options.body)); return jsonResponse(ticket, 201) })
    renderNewTicket()
    await fillRequired()
    fireEvent.change(screen.getByLabelText(/^Inicio\s*\*?$/), { target: { value: '2020-01-02T08:15' } })
    fireEvent.change(screen.getByLabelText('Fin'), { target: { value: '2020-01-02T09:15' } })
    fireEvent.change(screen.getByLabelText(/^Estado\s*\*?$/), { target: { value: 'CLOSED' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await screen.findByText('Ticket TEST-003 creado correctamente.')
    expect(payload).toMatchObject({ status: 'CLOSED', end_at: new Date(2020, 0, 2, 9, 15).toISOString() })
  })
  it('rechaza fin anterior al inicio sin enviar', async () => {
    const fetchMock = mockApi()
    renderNewTicket()
    await fillRequired()
    fireEvent.change(screen.getByLabelText(/^Inicio\s*\*?$/), { target: { value: '2026-10-02T16:20' } })
    fireEvent.change(screen.getByLabelText('Fin'), { target: { value: '2026-10-02T15:20' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Fin debe ser igual o posterior a Inicio')
    expect(screen.getByLabelText('Fin')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Fin')).toHaveAccessibleDescription('Fin debe ser igual o posterior a Inicio.')
    expect(screen.getByLabelText(/^Inicio\s*\*?$/)).not.toHaveAttribute('aria-invalid')
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false)
  })
  it.each([
    [409, 'Conflicto de numeración', 'Conflicto de numeración'],
    [422, [{ loc: ['body', 'customer_id'], msg: 'Field required' }], 'Cliente: Campo obligatorio'],
    [500, { unexpected: true }, 'HTTP 500'],
  ])('presenta errores backend %s comprensibles', async (status, detail, message) => {
    mockApi(async () => jsonResponse({ detail }, status))
    renderNewTicket()
    await fillRequired()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(String(message))
    expect(screen.getByRole('form', { name: 'Crear ticket' })).toHaveAttribute('aria-describedby', screen.getByRole('alert').id)
    if (status === 422) {
      expect(screen.getByRole('combobox', { name: /^Cliente/ })).toHaveAttribute('aria-invalid', 'true')
      expect(screen.getByRole('combobox', { name: /^Cliente/ })).toHaveAccessibleDescription(String(message))
    } else expect(screen.getByRole('combobox', { name: /^Cliente/ })).not.toHaveAttribute('aria-invalid')
    expect(screen.queryByText('[object Object]')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Guardar' })).toBeEnabled()
  })
  it('deshabilita Guardar y evita doble POST mientras se crea', async () => {
    let resolvePost: (response: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => { resolvePost = resolve })
    const fetchMock = mockApi(() => pending)
    renderNewTicket()
    await fillRequired()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(screen.getByRole('button', { name: 'Creando...' })).toBeDisabled()
    fireEvent.submit(screen.getByRole('form', { name: 'Crear ticket' }))
    expect(fetchMock.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1)
    await act(async () => resolvePost(jsonResponse(ticket, 201)))
    await screen.findByText('Ticket TEST-003 creado correctamente.')
  })
  it('muestra errores de catálogos y permite reintentar', async () => {
    const fetchMock = mockApi()
    const normal = fetchMock.getMockImplementation()!
    let failed = true
    fetchMock.mockImplementation((path, options) => path.startsWith('/api/customers') && failed
      ? Promise.resolve(jsonResponse({ detail: 'Catálogo no disponible' }, 503)) : normal(path, options))
    renderNewTicket()
    expect(await screen.findByRole('alert')).toHaveTextContent('Error al cargar catálogos')
    expect(screen.getByRole('button', { name: 'Guardar' })).toBeDisabled()
    failed = false
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar catálogos' }))
    await waitFor(() => expect(screen.getByLabelText(/^Cliente\s*\*?$/)).toBeEnabled())
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  })
  it.each(['sGGT', 'PRUEBA'])('busca Cliente por código o nombre: %s', async (search) => {
    mockApi(); renderNewTicket()
    const input = screen.getByRole('combobox', { name: /^Cliente/ })
    await waitFor(() => expect(input).toBeEnabled())
    fireEvent.click(input); fireEvent.change(input, { target: { value: search } })
    expect(screen.getByRole('option', { name: 'SGgt-00000 — Cliente de prueba' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'OTHER — Otro cliente' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('option', { name: 'SGgt-00000 — Cliente de prueba' }))
    expect(input).toHaveValue('SGgt-00000 — Cliente de prueba')
    await waitFor(() => expect(screen.getByRole('combobox', { name: /^Circuito/ })).toBeEnabled())
  })
  it.each(['sgGT-00000.00000', 'PRINCIPAL'])('busca Circuito por código o descripción: %s', async (search) => {
    mockApi(); renderNewTicket(); await fillRequired()
    const input = screen.getByRole('combobox', { name: /^Circuito/ })
    fireEvent.click(input); fireEvent.change(input, { target: { value: search } })
    expect(screen.getByRole('option', { name: 'SGgt-00000.00000 — Internet principal' })).toBeInTheDocument()
    fireEvent.change(input, { target: { value: 'not-found' } })
    expect(screen.getByText('No se encontraron circuitos.')).toBeInTheDocument()
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(input).toHaveValue('SGgt-00000.00000 — Internet principal')
  })
  it('cliente sin circuitos activos muestra un mensaje distinto de búsqueda sin coincidencias', async () => {
    const mock = mockApi()
    const normal = mock.getMockImplementation()!
    mock.mockImplementation((path, options) => path.startsWith('/api/circuits') ? Promise.resolve(jsonResponse([])) : normal(path, options))
    renderNewTicket()
    const customer = screen.getByRole('combobox', { name: /^Cliente/ })
    await waitFor(() => expect(customer).toBeEnabled())
    const circuitInput = screen.getByRole('combobox', { name: /^Circuito/ })
    expect(circuitInput).toBeDisabled()
    expect(circuitInput).toHaveAttribute('placeholder', 'Selecciona primero un cliente.')
    fireEvent.click(customer); fireEvent.click(screen.getByRole('option', { name: 'SGgt-00000 — Cliente de prueba' }))
    expect(await screen.findByText('Este cliente no tiene circuitos activos.')).toBeInTheDocument()
    expect(circuitInput).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Completa los campos obligatorios')
    expect(circuitInput).toHaveAttribute('aria-invalid', 'true')
    expect(circuitInput).toHaveAccessibleDescription('Completa los campos obligatorios antes de guardar.')
    expect(customer).not.toHaveAttribute('aria-invalid')
    expect(mock.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false)
  })
  it('volver a seleccionar el mismo cliente no borra su circuito', async () => {
    mockApi(); renderNewTicket(); await fillRequired()
    const customer = screen.getByRole('combobox', { name: /^Cliente/ })
    fireEvent.click(customer)
    fireEvent.click(screen.getByRole('option', { name: 'SGgt-00000 — Cliente de prueba' }))
    expect(screen.getByRole('combobox', { name: /^Circuito/ })).toHaveValue('SGgt-00000.00000 — Internet principal')
  })
  it('conserva Sector, Departamento y Tipo de incidencia como selects nativos', async () => {
    mockApi(); renderNewTicket(); await fillRequired()
    for (const label of ['Sector', 'Departamento', 'Tipo de incidencia']) {
      const select = screen.getByLabelText(new RegExp('^' + label + '\\s*\\*?$'))
      expect(select.tagName).toBe('SELECT')
      expect(select).toHaveValue('1')
    }
  })
  it('Nuevo ticket y Cancelar navegan sin recargar', async () => {
    mockApi()
    render(<MemoryRouter initialEntries={['/tickets']}><App /></MemoryRouter>)
    fireEvent.click(screen.getByRole('link', { name: 'Nuevo ticket' }))
    expect(screen.getByRole('heading', { name: 'Nuevo ticket' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(screen.getByRole('heading', { name: 'Tickets', level: 1 })).toBeInTheDocument()
    await screen.findByText('TEST-003')
  })
})
