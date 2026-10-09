import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { jsonResponse, ticket } from '../test/fixtures'
import type { Ticket } from '../types/ticket'
import { localDateTimeValue } from '../lib/datetime'

const customer = { id: 1, customer_code: 'C-1', name: 'Cliente histórico', active: false, created_at: ticket.created_at }
const circuit = { id: 1, customer_id: 1, circuit_code: 'C-1.01', description: 'Enlace principal', active: false, created_at: ticket.created_at }
const sector = { id: 1, name: 'Sector histórico', active: false, created_at: ticket.created_at }
const department = { ...sector, name: 'Departamento histórico' }
const incidentType = { ...sector, name: 'Tipo histórico' }
function mockApi(initial: Ticket = ticket, patch?: (options: RequestInit) => Promise<Response>) {
  let current = initial
  const mock = vi.fn((path: string, options?: RequestInit): Promise<Response> => {
    if (options?.method === 'PATCH') {
      if (patch) return patch(options)
      current = { ...current, ...JSON.parse(String(options.body)) }
      return Promise.resolve(jsonResponse(current))
    }
    if (path.includes('/escalations?')) return Promise.resolve(jsonResponse([]))
    if (path === '/health') return Promise.resolve(jsonResponse({ status: 'ok' }))
    if (path.startsWith('/api/tickets/1/updates')) return Promise.resolve(jsonResponse({ items: [], next_cursor: null }))
    if (path === '/api/tickets/1') return Promise.resolve(jsonResponse(current))
    if (path.startsWith('/api/tickets?')) return Promise.resolve(jsonResponse([current]))
    if (path.startsWith('/api/responsibles') || path.startsWith('/api/nodes')) return Promise.resolve(jsonResponse([]))
    const catalogs = { customers: customer, circuits: circuit, sectors: sector, departments: department, 'incident-types': incidentType }
    for (const [resource, item] of Object.entries(catalogs)) {
      if (path === `/api/${resource}/1`) return Promise.resolve(jsonResponse(item))
      if (path.startsWith(`/api/${resource}?`)) {
        if (resource === 'customers') return Promise.resolve(jsonResponse([{ ...customer, id: 2, active: true, customer_code: 'C-2', name: 'Otro cliente' }]))
        if (resource === 'circuits') return Promise.resolve(jsonResponse(path.includes('customer_id=2') ? [{ ...circuit, id: 2, customer_id: 2, active: true, circuit_code: 'C-2.01' }] : []))
        return Promise.resolve(jsonResponse([]))
      }
    }
    return Promise.resolve(jsonResponse({ detail: 'No encontrado' }, 404))
  })
  vi.stubGlobal('fetch', mock)
  return mock
}
function open(path = '/tickets/1') { render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>) }
const field = (name: string) => name === 'Cliente' || name === 'Circuito' ? screen.getByRole('combobox', { name: new RegExp(`^${name}\\s*\\*?$`) }) : screen.getByLabelText(new RegExp(`^${name}\\s*\\*?$`))
async function ready() { await waitFor(() => expect(screen.getByRole('button', { name: 'Guardar cambios' })).toBeEnabled()) }
afterEach(() => vi.useRealTimers())

describe('detalle de tickets', () => {
  it('muestra referencia, datos operativos y nombres históricos inactivos', async () => {
    const mock = mockApi(); open()
    expect(await screen.findByRole('heading', { name: ticket.reference })).toBeInTheDocument()
    for (const text of [ticket.title, ticket.description, 'C-1 — Cliente histórico', 'C-1.01 — Enlace principal', 'Sector histórico', 'Departamento histórico', 'Tipo histórico', 'En curso']) expect(screen.getByText(text)).toBeInTheDocument()
    expect(screen.getByText('Fin').nextElementSibling).toHaveTextContent('—')
    expect(screen.getByText('Fecha de creación')).toBeInTheDocument()
    expect(screen.getByText('Última actualización')).toBeInTheDocument()
    expect(mock).toHaveBeenCalledWith('/api/customers/1', expect.any(Object))
  })
  it('mantiene disponible el seguimiento en tickets cerrados', async () => {
    mockApi({ ...ticket, status: 'CLOSED', end_at: '2026-01-01T13:00:00Z' }); open()
    expect(await screen.findByRole('heading', { name: 'Seguimiento' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Nueva intervención' })).toBeEnabled())
    expect(await screen.findByText('Sin actualizaciones')).toBeInTheDocument()
  })
  it('formatea duración final en días, horas y minutos', async () => {
    mockApi({ ...ticket, end_at: '2026-01-03T16:15:00Z', duration_seconds: 188100 }); open()
    expect(await screen.findByText('2 d 4 h 15 min')).toBeInTheDocument()
  })
  it('muestra un error comprensible para un ticket inexistente', async () => {
    mockApi(); open('/tickets/999')
    expect(await screen.findByRole('alert')).toHaveTextContent('no encontrado')
  })
  it('referencia y Editar navegan mediante enlaces', async () => {
    mockApi(); open('/tickets')
    fireEvent.click(await screen.findByRole('link', { name: ticket.reference }))
    await screen.findByRole('heading', { name: ticket.reference })
    fireEvent.click(screen.getByRole('link', { name: 'Editar ticket' }))
    await ready()
    expect(screen.getByRole('heading', { name: `Editar ${ticket.reference}` })).toBeInTheDocument()
  })
})

describe('edición de tickets', () => {
  it('precarga campos, circuito histórico y fechas locales sin editar referencia', async () => {
    mockApi(); open('/tickets/1/edit'); await ready()
    expect(field('Título')).toHaveValue(ticket.title)
    expect(field('Descripción')).toHaveValue(ticket.description)
    expect(field('Cliente')).toHaveValue('C-1 — Cliente histórico')
    expect(field('Circuito')).toHaveValue('C-1.01 — Enlace principal')
    expect(field('Inicio')).toHaveValue(localDateTimeValue(new Date(ticket.start_at)))
    expect(field('Fin')).toHaveValue('')
    expect(screen.queryByRole('textbox', { name: /referencia/i })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(ticket.reference)
  })
  it('los valores históricos inactivos son visibles pero no seleccionables como nuevas opciones', async () => {
    mockApi(); open('/tickets/1/edit'); await ready()
    expect(field('Cliente')).toHaveValue('C-1 — Cliente histórico')
    expect(field('Circuito')).toHaveValue('C-1.01 — Enlace principal')
    fireEvent.click(field('Circuito'))
    const oldCircuit = screen.getByRole('option', { name: /C-1.01 — Enlace principal/ })
    expect(oldCircuit).toHaveAttribute('aria-disabled', 'true')
    fireEvent.keyDown(field('Circuito'), { key: 'Escape' })
    fireEvent.click(field('Cliente'))
    const oldCustomer = screen.getByRole('option', { name: /C-1 — Cliente histórico/ })
    expect(oldCustomer).toHaveAttribute('aria-disabled', 'true')
    fireEvent.click(screen.getByRole('option', { name: 'C-2 — Otro cliente' }))
    expect(field('Circuito')).toHaveValue('')
    await waitFor(() => expect(field('Circuito')).toBeEnabled())
    fireEvent.click(field('Cliente'))
    fireEvent.click(screen.getByRole('option', { name: /C-1 — Cliente histórico/ }))
    fireEvent.keyDown(field('Cliente'), { key: 'Escape' })
    expect(field('Cliente')).toHaveValue('C-2 — Otro cliente')
  })
  it('cambiar cliente limpia circuito y utiliza el filtro customer_id', async () => {
    const mock = mockApi(); open('/tickets/1/edit'); await ready()
    fireEvent.click(field('Cliente'))
    fireEvent.click(screen.getByRole('option', { name: 'C-2 — Otro cliente' }))
    expect(field('Circuito')).toHaveValue('')
    await waitFor(() => expect(field('Circuito')).toBeEnabled())
    fireEvent.click(field('Circuito'))
    await screen.findByRole('option', { name: 'C-2.01 — Enlace principal' })
    expect(screen.queryByRole('option', { name: 'C-1.01 — Enlace principal' })).not.toBeInTheDocument()
    expect(mock).toHaveBeenCalledWith('/api/circuits?customer_id=2&include_inactive=false&limit=200&offset=0', expect.any(Object))
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar Cliente' }))
    expect(field('Circuito')).toBeDisabled()
  })
  it('envía PATCH soportado, fecha local convertida y fin null, y refresca detalle', async () => {
    const mock = mockApi(); open('/tickets/1/edit'); await ready()
    fireEvent.change(field('Título'), { target: { value: 'Título corregido' } })
    fireEvent.change(field('Inicio'), { target: { value: '2025-10-02T16:20' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    expect(await screen.findByText('Cambios guardados correctamente.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Título corregido' })).toBeInTheDocument()
    const payload = JSON.parse(String(mock.mock.calls.find(([, options]) => options?.method === 'PATCH')?.[1]?.body))
    expect(payload).toEqual({ title: 'Título corregido', description: ticket.description, customer_id: 1, circuit_id: 1, sector_id: 1, department_id: 1, incident_type_id: 1, responsible_id: null, start_at: new Date(2025, 9, 2, 16, 20).toISOString(), end_at: null, status: 'OPEN' })
  })
  it('mantiene segundos originales cuando las fechas no se cambian', async () => {
    const initial = { ...ticket, start_at: '2026-01-01T12:00:37Z', end_at: '2026-01-01T13:10:42Z' }
    const mock = mockApi(initial); open('/tickets/1/edit'); await ready()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    await screen.findByText('Cambios guardados correctamente.')
    const payload = JSON.parse(String(mock.mock.calls.find(([, options]) => options?.method === 'PATCH')?.[1]?.body))
    expect(payload.start_at).toBe(initial.start_at); expect(payload.end_at).toBe(initial.end_at)
  })
  it('bloquea Fin anterior a Inicio sin PATCH', async () => {
    const mock = mockApi(); open('/tickets/1/edit'); await ready()
    fireEvent.change(field('Fin'), { target: { value: '2020-01-01T00:00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Fin debe ser igual o posterior')
    expect(mock.mock.calls.some(([, options]) => options?.method === 'PATCH')).toBe(false)
  })
  it('CLOSED es editable y reabrir no borra Fin', async () => {
    const initial: Ticket = { ...ticket, status: 'CLOSED', end_at: '2026-01-01T13:00:00Z' }
    const mock = mockApi(initial); open('/tickets/1/edit'); await ready()
    const end = localDateTimeValue(new Date(initial.end_at!))
    expect(field('Estado')).toHaveValue('CLOSED')
    fireEvent.change(field('Estado'), { target: { value: 'OPEN' } })
    expect(field('Fin')).toHaveValue(end)
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    await screen.findByText('Cambios guardados correctamente.')
    expect(JSON.parse(String(mock.mock.calls.find(([, options]) => options?.method === 'PATCH')?.[1]?.body))).toMatchObject({ status: 'OPEN', end_at: initial.end_at })
  })
  it('permite cerrar sin Fin', async () => {
    const mock = mockApi(); open('/tickets/1/edit'); await ready()
    fireEvent.change(field('Estado'), { target: { value: 'CLOSED' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    await screen.findByText('Cambios guardados correctamente.')
    expect(JSON.parse(String(mock.mock.calls.find(([, options]) => options?.method === 'PATCH')?.[1]?.body))).toMatchObject({ status: 'CLOSED', end_at: null })
  })
  it('permite definir Fin manteniendo OPEN', async () => {
    const mock = mockApi(); open('/tickets/1/edit'); await ready()
    fireEvent.change(field('Fin'), { target: { value: '2026-10-02T16:20' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    await screen.findByText('Cambios guardados correctamente.')
    expect(JSON.parse(String(mock.mock.calls.find(([, options]) => options?.method === 'PATCH')?.[1]?.body))).toMatchObject({ status: 'OPEN', end_at: new Date(2026, 9, 2, 16, 20).toISOString() })
  })
  it('permite borrar Fin explícitamente de un ticket cerrado', async () => {
    const mock = mockApi({ ...ticket, status: 'CLOSED', end_at: '2026-01-01T13:00:00Z' }); open('/tickets/1/edit'); await ready()
    fireEvent.change(field('Fin'), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    await screen.findByText('Cambios guardados correctamente.')
    expect(JSON.parse(String(mock.mock.calls.find(([, options]) => options?.method === 'PATCH')?.[1]?.body))).toMatchObject({ status: 'CLOSED', end_at: null })
  })
  it('muestra errores de catálogos en edición y permite reintentar', async () => {
    const mock = mockApi()
    const normal = mock.getMockImplementation()!
    let failed = true
    mock.mockImplementation((path, options) => failed && path === '/api/sectors/1' ? Promise.resolve(jsonResponse({ detail: 'Catálogo no disponible' }, 503)) : normal(path, options))
    open('/tickets/1/edit')
    expect(await screen.findByRole('alert')).toHaveTextContent('Catálogo no disponible')
    expect(screen.getByRole('button', { name: 'Guardar cambios' })).toBeDisabled()
    failed = false
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar catálogos' }))
    await ready()
    expect(field('Circuito')).toHaveValue('C-1.01 — Enlace principal')
  })
  it('Finalizar ahora prepara Fin y CLOSED con reloj local, sin guardar automáticamente', async () => {
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date(2026, 9, 2, 16, 20))
    const mock = mockApi(); open('/tickets/1/edit'); await ready()
    const button = screen.getByRole('button', { name: 'Finalizar ahora' })
    expect(button).toHaveAttribute('type', 'button')
    fireEvent.click(button)
    expect(field('Estado')).toHaveValue('CLOSED'); expect(field('Fin')).toHaveValue('2026-10-02T16:20')
    expect(mock.mock.calls.some(([, options]) => options?.method === 'PATCH')).toBe(false)
    fireEvent.change(field('Fin'), { target: { value: '2026-10-02T15:20' } })
    expect(field('Fin')).toHaveValue('2026-10-02T15:20')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    await screen.findByText('Cambios guardados correctamente.')
    expect(mock.mock.calls.filter(([, options]) => options?.method === 'PATCH')).toHaveLength(1)
  })
  it('deshabilita Guardar y evita doble PATCH durante envío', async () => {
    let finish: (response: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => { finish = resolve })
    const mock = mockApi(ticket, () => pending); open('/tickets/1/edit'); await ready()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    expect(screen.getByRole('button', { name: 'Guardando...' })).toBeDisabled()
    fireEvent.submit(screen.getByRole('form', { name: 'Editar ticket' }))
    expect(mock.mock.calls.filter(([, options]) => options?.method === 'PATCH')).toHaveLength(1)
    await act(async () => finish(jsonResponse(ticket)))
    await screen.findByText('Cambios guardados correctamente.')
  })
  it.each([409, 422, 500])('muestra errores PATCH %s sin perder los datos', async (status) => {
    mockApi(ticket, async () => jsonResponse({ detail: 'No se pudo guardar' }, status)); open('/tickets/1/edit'); await ready()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo guardar')
    expect(field('Título')).toHaveValue(ticket.title)
    expect(screen.getByRole('button', { name: 'Guardar cambios' })).toBeEnabled()
  })
})

describe('resolución y textos autorizados', () => {
  it('muestra resolución interna separada de descripción y ofrece ambos PDF', async () => {
    mockApi({ ...ticket, resolution: 'Solución interna documentada' }); open()
    expect(await screen.findByText('Solución interna documentada')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Resolución documentada' })).toBeInTheDocument()
    expect(screen.getByText(ticket.description)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Exportar PDF'))
    expect(screen.getByRole('button', { name: 'Reporte técnico interno' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reporte para cliente' })).toBeInTheDocument()
  })

  it('edita la resolución de un cerrado sin cambiar sus fechas y autoriza textos explícitos', async () => {
    const closed = { ...ticket, status: 'CLOSED' as const, end_at: '2026-01-01T13:00:00Z', resolution: 'Resolución anterior' }
    const mock = mockApi(closed); open('/tickets/1/edit')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Guardar cambios' })).toBeEnabled())
    expect(screen.getByLabelText('Resolución interna')).toHaveValue('Resolución anterior')
    expect(screen.getByLabelText('Descripción del incidente')).toHaveValue('')
    expect(screen.getByLabelText('Resolución del incidente')).toHaveValue('')
    expect(screen.getByText(/Nunca se copia automáticamente/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Resolución interna'), { target: { value: 'Resolución corregida' } })
    fireEvent.change(screen.getByLabelText('Descripción del incidente'), { target: { value: 'Incidente compartible' } })
    fireEvent.change(screen.getByLabelText('Resolución del incidente'), { target: { value: 'Solución compartible' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    await screen.findByText('Cambios guardados correctamente.')
    const body = JSON.parse(String(mock.mock.calls.find(([, options]) => options?.method === 'PATCH')![1]?.body))
    expect(body).toMatchObject({ resolution: 'Resolución corregida', customer_description: 'Incidente compartible', customer_resolution: 'Solución compartible', start_at: closed.start_at, end_at: closed.end_at, status: 'CLOSED' })
  })

  it('puede retirar el contenido autorizado con null y asocia los errores de resolución', async () => {
    const mock = mockApi({ ...ticket, customer_description: 'Antes', customer_resolution: 'Antes' }, async () => jsonResponse({ detail: [{ loc: ['body', 'resolution'], msg: 'Contenido inválido' }] }, 422))
    open('/tickets/1/edit')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Guardar cambios' })).toBeEnabled())
    fireEvent.change(screen.getByLabelText('Descripción del incidente'), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('Resolución del incidente'), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('Resolución interna'), { target: { value: 'Borrador preservado' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Resolución documentada: Contenido inválido')
    expect(screen.getByLabelText('Resolución interna')).toHaveValue('Borrador preservado')
    expect(screen.getByLabelText('Resolución interna')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Resolución interna')).toHaveAttribute('aria-describedby', 'ticket-submit-error')
    const body = JSON.parse(String(mock.mock.calls.find(([, options]) => options?.method === 'PATCH')![1]?.body))
    expect(body.customer_description).toBeNull()
    expect(body.customer_resolution).toBeNull()
  })
})
