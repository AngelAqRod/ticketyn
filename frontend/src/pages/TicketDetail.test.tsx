import { act, fireEvent, render, screen, waitFor } from '../test/render'
import { MemoryRouter } from 'react-router'
import { afterAll, beforeAll, afterEach, describe, expect, it, vi } from 'vitest'
// Authentication is exercised in auth/AuthGate.test.tsx; these tests isolate operational routing.
vi.mock('../auth/AuthGate', () => ({ AuthGate: ({ children }: { children: React.ReactNode }) => children }))

import App from '../App'
import { PermissionProvider } from '../auth/permissions'
import { getTicketCatalogs } from '../api'
import { jsonResponse, ticket } from '../test/fixtures'
import type { Ticket } from '../types/ticket'
import { localDateTimeValue } from '../lib/datetime'

const originalShow = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal')
const originalClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close')
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value(this: HTMLDialogElement) { this.setAttribute('open', '') } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value(this: HTMLDialogElement) { this.removeAttribute('open') } })
})
afterAll(() => {
  for (const [name, descriptor] of [['showModal', originalShow], ['close', originalClose]] as const) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor)
    else Reflect.deleteProperty(HTMLDialogElement.prototype, name)
  }
})
const customer = { id: 1, customer_code: 'C-1', name: 'Cliente histórico', active: false, created_at: ticket.created_at }
const circuit = { node_id: 1, node: { id: 1, name: 'Nodo actual', active: true }, sector_id: 1, sector: { id: 1, name: 'Sector actual', active: true }, id: 1, customer_id: 1, circuit_code: 'C-1.01', description: 'Enlace principal', active: false, created_at: ticket.created_at }
const sector = { id: 1, name: 'Sector histórico', active: false, created_at: ticket.created_at }
const department = { ...sector, name: 'Departamento histórico' }
const incidentType = { ...sector, name: 'Tipo histórico' }
function mockApi(initial: Ticket = ticket, patch?: (options: RequestInit) => Promise<Response>, circuitStatus = 200) {
  let current = initial
  const mock = vi.fn((path: string, options?: RequestInit): Promise<Response> => {
    if (path.endsWith('/close') && options?.method === 'POST') {
      current = { ...current, status: 'CLOSED', end_at: '2026-01-01T13:00:00Z', duration_seconds: 3600 }
      return Promise.resolve(jsonResponse(current))
    }
    if (options?.method === 'PATCH') {
      if (patch) return patch(options)
      current = { ...current, ...JSON.parse(String(options.body)) }
      return Promise.resolve(jsonResponse(current))
    }
    if (path.includes('/escalations?')) return Promise.resolve(jsonResponse([]))
    if (path === '/health') return Promise.resolve(jsonResponse({ status: 'ok' }))
    if (path.startsWith('/api/tickets/1/updates')) return Promise.resolve(jsonResponse({ items: [], next_cursor: null }))
    if (path === '/api/circuits/1' && circuitStatus !== 200) return Promise.resolve(jsonResponse({ detail: 'Circuito no disponible' }, circuitStatus))
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
function open(path = '/tickets/1', permissions?: string[]) {
  const app = <MemoryRouter initialEntries={[path]}><App /></MemoryRouter>
  render(permissions ? <PermissionProvider permissions={permissions}>{app}</PermissionProvider> : app)
}
const field = (name: string) => name === 'Cliente' || name === 'Circuito' ? screen.getByRole('combobox', { name: new RegExp(`^${name}\\s*\\*?$`) }) : screen.getByLabelText(new RegExp(`^${name}\\s*\\*?$`))
async function ready() { await waitFor(() => expect(screen.getByRole('button', { name: 'Guardar cambios' })).toBeEnabled()) }
afterEach(() => vi.useRealTimers())

describe('detalle de tickets', () => {
  it('enlaza código y descripción al ID real, incluso con circuito inactivo', async () => {
    const mock = mockApi(); open()
    const link = await screen.findByRole('link', { name: 'C-1.01 — Enlace principal' })
    expect(link).toHaveAttribute('href', '/circuits/1')
    expect(link).not.toHaveAttribute('target')
    expect(mock.mock.calls.filter(([path]) => path === '/api/circuits/1')).toHaveLength(1)
  })
  it.each([403, 404])('conserva texto disponible sin enlace ante HTTP %s de circuito', async status => {
    mockApi({ ...ticket, circuit: { id: 1, circuit_code: 'HIST-200.01', description: 'Circuito histórico conservado' } }, undefined, status); open()
    expect(await screen.findByRole('heading', { name: ticket.reference })).toBeVisible()
    expect(screen.getByText('HIST-200.01 — Circuito histórico conservado')).toBeVisible()
    expect(screen.queryByRole('link', { name: /HIST-200.01/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cerrar ticket' })).toBeVisible()
  })
  it('tolera una referencia no resuelta sin texto de circuito disponible', async () => {
    mockApi({ ...ticket, circuit: undefined }, undefined, 404); open()
    expect(await screen.findByText('Sin circuito asociado')).toBeVisible()
    expect(screen.getByRole('heading', { name: ticket.reference })).toBeVisible()
  })
  it('mantiene estricto el helper utilizado por la edición tradicional', async () => {
    mockApi(ticket, undefined, 404)
    await expect(getTicketCatalogs(ticket)).rejects.toMatchObject({ status: 404 })
  })
  it('presenta texto sin enlace cuando no hay permiso de lectura de circuitos', async () => {
    mockApi(); open('/tickets/1', ['tickets.view'])
    expect(await screen.findByText('C-1.01 — Enlace principal')).toBeVisible()
    expect(screen.queryByRole('link', { name: /C-1.01/ })).not.toBeInTheDocument()
  })

  it('cierra desde cabecera y actualiza estado, duración y acciones sin perder la edición', async () => {
    const mock = mockApi(); open()
    const close = await screen.findByRole('button', { name: 'Cerrar ticket' })
    expect(close.nextElementSibling).toBe(screen.getByRole('link', { name: 'Editar ticket' }))
    expect(close.parentElement?.previousElementSibling).toBe(screen.getByRole('link', { name: 'Volver a tickets' }))
    expect(close).toHaveClass('text-emerald-300', 'bg-emerald-500/10')
    fireEvent.click(close)
    expect(screen.getByRole('dialog', { name: 'Cerrar ticket de cliente' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar cierre' }))
    expect(await screen.findByText('Ticket cerrado correctamente.')).toBeVisible()
    expect(screen.getByText('Cerrado')).toBeVisible()
    expect(screen.getByText('Duración').nextElementSibling).toHaveTextContent('1 h')
    expect(screen.queryByRole('button', { name: 'Cerrar ticket' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Editar ticket' })).toBeVisible()
    expect(mock.mock.calls.filter(([path, init]) => path.endsWith('/close') && init?.method === 'POST')).toHaveLength(1)
    fireEvent.click(screen.getByRole('link', { name: 'Editar ticket' })); await ready()
    fireEvent.change(field('Estado'), { target: { value: 'OPEN' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    await screen.findByText('Cambios guardados correctamente.')
    expect(screen.getByRole('button', { name: 'Cerrar ticket' })).toBeVisible()
    expect(screen.queryByText('Ticket cerrado correctamente.')).not.toBeInTheDocument()
  })
  it.each([true, false])('muestra el Nodo persistido y conserva NULL explícito (%s)', async (hasNode) => {
    mockApi({ ...ticket, node_id: hasNode ? 7 : null, node: hasNode ? { id: 7, name: 'UFINET', active: true } : null }); open()
    await screen.findByRole('heading', { name: ticket.reference })
    expect(screen.getByText('Nodo').nextElementSibling).toHaveTextContent(hasNode ? 'UFINET' : 'Sin asignar')
    expect(screen.queryByText('Nodo actual')).not.toBeInTheDocument()
  })
  it('muestra referencia, datos operativos y nombres históricos inactivos', async () => {
    const mock = mockApi(); open()
    expect(await screen.findByRole('heading', { name: ticket.reference })).toBeInTheDocument()
    for (const text of [ticket.title, ticket.description, 'C-1 — Cliente histórico', 'C-1.01 — Enlace principal', 'Sector histórico', 'Departamento histórico', 'Tipo histórico', 'En curso']) expect(screen.getByText(text)).toBeInTheDocument()
    expect(screen.getByText('Fin').nextElementSibling).toHaveTextContent('—')
    expect(screen.getByText('Fecha de creación')).toBeInTheDocument()
    expect(screen.getByText('Última actualización')).toBeInTheDocument()
    expect(mock).toHaveBeenCalledWith('/api/customers/1', expect.any(Object))
  })
  it('muestra "Sin fecha de fin" en detalle de ticket cerrado sin fin', async () => {
    mockApi({ ...ticket, status: 'CLOSED', end_at: null, duration_seconds: null }); open()
    await screen.findByRole('heading', { name: ticket.reference })
    expect(screen.getByText('Duración').nextElementSibling).toHaveTextContent('Sin fecha de fin')
  })
  it('muestra duración formateada en detalle cuando el ticket tiene duración calculada', async () => {
    mockApi({ ...ticket, status: 'CLOSED', end_at: '2026-01-01T13:00:00Z', duration_seconds: 3600 }); open()
    await screen.findByRole('heading', { name: ticket.reference })
    expect(screen.getByText('Duración').nextElementSibling).toHaveTextContent('1 h')
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
    expect(payload).toEqual({ title: 'Título corregido', description: ticket.description, customer_id: 1, circuit_id: 1, department_id: 1, incident_type_id: 1, responsible_id: null, start_at: new Date(2025, 9, 2, 16, 20).toISOString(), end_at: null, status: 'OPEN' })
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

it('sincroniza el detalle cuando recomendaciones detecta un cierre remoto y no vuelve a vigilarlo', async () => {
  const mock = mockApi()
  const original = mock.getMockImplementation()!
  let reads = 0
  mock.mockImplementation((path, options) => {
    if (path === '/api/tickets/1') {
      reads += 1
      return Promise.resolve(jsonResponse(reads > 1 ? { ...ticket, status: 'CLOSED', end_at: '2026-10-25T12:00:00Z' } : ticket))
    }
    if (path.endsWith('/recommendations')) return Promise.resolve(jsonResponse({ ticket_id: 1, ticket_status: 'CLOSED',
      stage_name: 'Ticket cerrado', reference_position_id: null, reference_position_name: null, stage_started_at: null,
      elapsed_minutes: 0, has_active_ack: false, active_ack: null, can_acknowledge: false, recommendations: [] }))
    return original(path, options)
  })
  open()
  await screen.findByText('Cerrado')
  expect(reads).toBe(2)
  expect(mock.mock.calls.filter(([url]) => url.endsWith('/recommendations'))).toHaveLength(1)
})
