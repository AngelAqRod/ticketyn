import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { PermissionProvider } from '../auth/permissions'
import { InstallationOrderForm } from './InstallationOrderForm'
import { orderPatch, orderPayload, orderValues } from '../components/installation/OrderFields'
import { jsonResponse } from '../test/fixtures'

const stamp = '2026-01-01T00:00:00Z'
const customer = { id: 4, customer_code: 'CLI4', name: 'Cliente de prueba', active: true, created_at: stamp }
const other = { id: 5, customer_code: 'CLI5', name: 'Otro cliente', active: true, created_at: stamp }
const named = { id: 1, name: 'Clasificación existente', active: true, created_at: stamp }
const circuit = { address: 'Zona 1', latitude: '14.634915', longitude: '-90.506882', additional_notes: 'Acceso por el portón', id: 7, customer_id: 4, circuit_code: 'CIR-7', description: 'Enlace existente', active: true, created_at: stamp, node_id: 1, node: named, sector_id: 1, sector: named, service_type_id: 1, service_type: named, distribution_device: { id: 2, name: 'CORE A', active: true }, distribution_port: { id: 3, name: 'sfp+1', active: true }, cpe_model: null }
const createdCircuit = { ...circuit, id: 10, circuit_code: 'NEW-C', description: 'Nuevo enlace' }
const originalShow = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal')
const originalClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close')
// jsdom has no native dialog cycle; only open/close is simulated, the React logic runs for real.
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value(this: HTMLDialogElement) { this.setAttribute('open', '') } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value(this: HTMLDialogElement) { this.removeAttribute('open') } })
})
afterAll(() => {
  if (originalShow) Object.defineProperty(HTMLDialogElement.prototype, 'showModal', originalShow); else Reflect.deleteProperty(HTMLDialogElement.prototype, 'showModal')
  if (originalClose) Object.defineProperty(HTMLDialogElement.prototype, 'close', originalClose); else Reflect.deleteProperty(HTMLDialogElement.prototype, 'close')
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

function mockApi(existingOrder: unknown[] = []) {
  const mock = vi.fn((path: string, init?: RequestInit): Promise<Response> => {
    if (init?.method === 'POST') {
      if (path === '/api/customers') return Promise.resolve(jsonResponse({ ...customer, id: 9, customer_code: 'NEW', name: 'Nuevo cliente' }, 201))
      if (path === '/api/circuits') return Promise.resolve(jsonResponse({ ...createdCircuit, customer_id: Number(JSON.parse(String(init.body)).customer_id) }, 201))
      return Promise.resolve(jsonResponse({ id: 8 }, 201))
    }
    if (path.startsWith('/api/installation-orders')) return Promise.resolve(new Response(JSON.stringify(existingOrder), { headers: { 'X-Total-Count': String(existingOrder.length) } }))
    if (path.startsWith('/api/customers')) return Promise.resolve(jsonResponse([customer, other]))
    if (path.startsWith('/api/circuits')) return Promise.resolve(jsonResponse(path.includes('customer_id=4') ? [circuit] : []))
    if (/^\/api\/(sectors|nodes|service-types|cpe-models)/.test(path)) return Promise.resolve(jsonResponse([named]))
    return Promise.resolve(jsonResponse([]))
  })
  vi.stubGlobal('fetch', mock)
  return mock
}
const writes = (mock: ReturnType<typeof mockApi>) => mock.mock.calls.filter(([, init]) => init?.method === 'POST')
function open(permissions: string[], url = '/') {
  render(<PermissionProvider permissions={permissions}><MemoryRouter initialEntries={[url]}><Routes><Route path="/" element={<InstallationOrderForm />} /><Route path="/installation-orders/:id" element={<p>Orden guardada</p>} /></Routes></MemoryRouter></PermissionProvider>)
}
const combo = (label: string) => screen.getByRole('combobox', { name: new RegExp(`^${label}`) })
async function pickCustomer(label = 'CLI4 — Cliente de prueba') {
  await waitFor(() => expect(combo('Cliente')).not.toBeDisabled())
  fireEvent.click(combo('Cliente')); fireEvent.click(screen.getByRole('option', { name: label }))
}
async function pickCircuit() {
  await waitFor(() => expect(combo('Circuito')).not.toBeDisabled())
  fireEvent.click(combo('Circuito')); fireEvent.click(screen.getByRole('option', { name: 'CIR-7 — Enlace existente' }))
}
const full = ['installation_orders.create', 'customers.create', 'circuits.create']

describe('payloads', () => {
  it('preserves incomplete drafts and converts dates from Guatemala, not browser time', () => {
    expect(orderPayload(orderValues(), true)).not.toHaveProperty('customer_id')
    expect(() => orderPayload(orderValues())).toThrow('Completa cliente, circuito')
    expect(orderPayload({ ...orderValues(), customer_id: '4', circuit_id: '7', requested_at: '2026-10-28T12:30' })).toMatchObject({ order_type: 'NORMAL', customer_id: 4, circuit_id: 7, requested_at: '2026-10-28T18:30:00.000Z' })
  })
  it('sends only the fields of the selected modality', () => {
    const normal = orderPayload({ ...orderValues(), customer_id: '4', circuit_id: '7', description: 'residual', node_id: '1', requested_at: '2026-10-28T12:30' })
    expect(normal).not.toHaveProperty('description'); expect(normal).not.toHaveProperty('node_id')
    const extra = orderPayload({ ...orderValues(), order_type: 'EXTRAORDINARY', customer_id: '4', circuit_id: '7', description: ' Predio ', service_type_id: '1', node_id: '1', sector_id: '1', requested_at: '2026-10-28T12:30' })
    expect(extra).toMatchObject({ order_type: 'EXTRAORDINARY', description: 'Predio', service_type_id: 1, node_id: 1, sector_id: 1 }); expect(extra).not.toHaveProperty('circuit_id')
    expect(() => orderPayload({ ...orderValues(), order_type: 'EXTRAORDINARY', customer_id: '4', requested_at: '2026-10-28T12:30' })).toThrow('descripción, servicio, nodo, sector')
  })
  it('never sends the permanent type or circuit when editing', () => {
    const patch = orderPatch({ ...orderValues(), customer_id: '4', circuit_id: '7', requested_at: '2026-10-28T12:30' })
    expect(patch).not.toHaveProperty('order_type'); expect(patch).not.toHaveProperty('circuit_id')
    expect(orderValues({ order_type: null } as never).order_type).toBe('')
  })
})

describe('orden normal', () => {
  beforeEach(() => { mockApi() })
  it('rejects a normal order without circuit and never sends a create request', async () => {
    const mock = mockApi(); open(['installation_orders.create'])
    fireEvent.click(screen.getByRole('button', { name: 'Registrar orden' }))
    expect(await screen.findByText('Completa cliente, circuito y fecha de solicitud.')).toBeVisible()
    expect(writes(mock)).toHaveLength(0)
    expect(screen.queryByRole('button', { name: 'Crear cliente' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Abrir gestión de clientes' })).not.toBeInTheDocument()
  })
  it('loads the technical data after selecting an existing circuit and registers it without copying them', async () => {
    const mock = mockApi(); open(['installation_orders.create'])
    expect(combo('Circuito')).toBeDisabled()
    await pickCustomer(); await pickCircuit()
    const technical = within(screen.getByRole('region', { name: 'Datos técnicos del circuito' }))
    for (const text of ['Clasificación existente', 'CORE A', 'sfp+1', 'No disponible']) expect(technical.getAllByText(text).length).toBeGreaterThan(0)
    const site = within(screen.getByRole('region', { name: 'Ubicación del circuito' }))
    for (const text of ['Zona 1', '14.634915, -90.506882', 'Acceso por el portón']) expect(site.getByText(text)).toBeVisible()
    expect(site.getByRole('link', { name: 'Ver en Google Maps' })).toBeVisible()
    fireEvent.change(screen.getByLabelText(/Fecha de solicitud/), { target: { value: '2026-10-28T12:30' } })
    fireEvent.click(screen.getByRole('button', { name: 'Registrar orden' }))
    expect(await screen.findByText('Orden guardada')).toBeVisible()
    const body = JSON.parse(String(writes(mock)[0][1]?.body))
    expect(body).toMatchObject({ order_type: 'NORMAL', customer_id: 4, circuit_id: 7 }); expect(body).not.toHaveProperty('service_type_id'); expect(body).not.toHaveProperty('created_by')
  })
  it('creates a customer from the order, selects it and keeps the typed form without saving the order', async () => {
    const mock = mockApi(); open(full)
    await waitFor(() => expect(combo('Cliente')).not.toBeDisabled())
    fireEvent.change(screen.getByLabelText('Observaciones'), { target: { value: 'Nota previa' } })
    fireEvent.click(screen.getByRole('button', { name: 'Crear cliente' }))
    const modal = within(screen.getByRole('dialog'))
    fireEvent.change(modal.getByLabelText(/^Código de cliente/), { target: { value: 'NEW' } }); fireEvent.change(modal.getByLabelText(/^Nombre/), { target: { value: 'Nuevo cliente' } })
    fireEvent.click(modal.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText('Cliente NEW creado y seleccionado.')).toBeVisible()
    expect(combo('Cliente')).toHaveValue('NEW — Nuevo cliente'); expect(screen.getByLabelText('Observaciones')).toHaveValue('Nota previa')
    expect(writes(mock).map(([path]) => path)).toEqual(['/api/customers'])  // the order itself was NOT saved
    await waitFor(() => expect(combo('Circuito')).not.toBeDisabled())
    expect(mock).toHaveBeenCalledWith(expect.stringContaining('/api/circuits?customer_id=9'), expect.anything())
  })
  it('creates a circuit for the selected customer, selects it and shows its technical data', async () => {
    const mock = mockApi(); open(full)
    await pickCustomer(); await waitFor(() => expect(screen.getByRole('button', { name: 'Crear circuito' })).toBeEnabled())
    fireEvent.change(screen.getByLabelText('Observaciones'), { target: { value: 'Nota previa' } })
    fireEvent.click(screen.getByRole('button', { name: 'Crear circuito' }))
    const modal = within(screen.getByRole('dialog'))
    expect(modal.getByText('CLI4 — Cliente de prueba', { exact: false })).toBeInTheDocument()
    fireEvent.change(modal.getByLabelText(/^Código de circuito/), { target: { value: 'NEW-C' } }); fireEvent.change(modal.getByLabelText(/^Descripción/), { target: { value: 'Nuevo enlace' } })
    fireEvent.change(modal.getByLabelText(/^Dirección/), { target: { value: 'Zona 2' } }); fireEvent.change(modal.getByLabelText(/^Punto GPS/), { target: { value: '14.5, -90.5' } })
    await waitFor(() => expect(modal.getByRole('option', { name: named.name })).toBeInTheDocument()); fireEvent.change(modal.getByLabelText(/^Sector/), { target: { value: '1' } })
    const node = modal.getByRole('combobox', { name: 'Nodo' }); await waitFor(() => expect(node).toBeEnabled()); fireEvent.click(node); fireEvent.click(within(screen.getByRole('listbox', { name: 'Nodo' })).getByRole('option', { name: named.name }))
    fireEvent.click(modal.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText('Circuito NEW-C creado y seleccionado.')).toBeVisible()
    expect(combo('Circuito')).toHaveValue('NEW-C — Nuevo enlace'); expect(screen.getByLabelText('Observaciones')).toHaveValue('Nota previa')
    expect(writes(mock).map(([path]) => path)).toEqual(['/api/circuits'])
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ customer_id: 4, circuit_code: 'NEW-C', address: 'Zona 2', latitude: '14.5', longitude: '-90.5', additional_notes: null })
    expect(within(screen.getByRole('region', { name: 'Datos técnicos del circuito' })).getByText('CORE A')).toBeInTheDocument()
  })
  it('keeps the form and the selection when a quick-create dialog is cancelled', async () => {
    const mock = mockApi(); open(full)
    await pickCustomer(); fireEvent.change(screen.getByLabelText('Observaciones'), { target: { value: 'Nota previa' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Crear circuito' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Crear circuito' })); fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(combo('Cliente')).toHaveValue('CLI4 — Cliente de prueba'); expect(screen.getByLabelText('Observaciones')).toHaveValue('Nota previa'); expect(writes(mock)).toHaveLength(0)
  })
  it('clears the circuit when the customer changes so customers are never mixed', async () => {
    mockApi(); open(['installation_orders.create'])
    await pickCustomer(); await pickCircuit(); expect(combo('Circuito')).toHaveValue('CIR-7 — Enlace existente')
    fireEvent.click(combo('Cliente')); fireEvent.click(screen.getByRole('option', { name: 'CLI5 — Otro cliente' }))
    await waitFor(() => expect(combo('Circuito')).toHaveValue(''))
    expect(screen.getByText('Selecciona un circuito para consultar sus datos técnicos.')).toBeVisible()
  })
  it.each([['customers.create', 'Crear cliente', 'Crear circuito'], ['circuits.create', 'Crear circuito', 'Crear cliente'], ['context.customers.create', 'Crear cliente', 'Crear circuito']])('shows quick creation only with its own permission (%s)', async (permission, shown, hidden) => {
    mockApi(); open(['installation_orders.create', permission])
    await pickCustomer()
    await waitFor(() => expect(screen.getByRole('button', { name: shown })).toBeInTheDocument()); expect(screen.queryByRole('button', { name: hidden })).not.toBeInTheDocument()
  })
  it('warns that the circuit already has a normal order and links to it', async () => {
    mockApi([{ id: 3, reference: 'OI-000003' }]); open(['installation_orders.create', 'installation_orders.view'])
    await pickCustomer(); await pickCircuit()
    expect(await screen.findByRole('link', { name: 'OI-000003' })).toHaveAttribute('href', '/installation-orders/3')
  })
  it('preloads customer and circuit when started from a circuit', async () => {
    mockApi(); open(['installation_orders.create'], '/?customer_id=4&circuit_id=7')
    await waitFor(() => expect(combo('Circuito')).toHaveValue('CIR-7 — Enlace existente'))
    expect(combo('Cliente')).toHaveValue('CLI4 — Cliente de prueba')
  })
})

describe('orden extraordinaria', () => {
  it('shows only its fields, needs no circuit and has no quick creation', async () => {
    const mock = mockApi(); open(full)
    fireEvent.click(screen.getByRole('radio', { name: 'Extraordinaria' }))
    expect(screen.queryByRole('combobox', { name: /^Circuito/ })).not.toBeInTheDocument(); expect(screen.queryByRole('button', { name: 'Crear cliente' })).not.toBeInTheDocument()
    await pickCustomer()
    fireEvent.change(screen.getByLabelText(/^Descripción/), { target: { value: 'Instalación especial' } })
    for (const label of ['Servicio solicitado', 'Nodo', 'Sector']) { await waitFor(() => expect(combo(label)).not.toBeDisabled()); fireEvent.click(combo(label)); fireEvent.click(within(screen.getByRole('listbox', { name: new RegExp(`^${label}`) })).getByRole('option', { name: named.name })) }
    fireEvent.change(screen.getByLabelText(/Fecha de solicitud/), { target: { value: '2026-10-28T12:30' } })
    fireEvent.click(screen.getByRole('button', { name: 'Registrar orden' }))
    expect(await screen.findByText('Orden guardada')).toBeVisible()
    const body = JSON.parse(String(writes(mock)[0][1]?.body))
    expect(body).toMatchObject({ order_type: 'EXTRAORDINARY', customer_id: 4, description: 'Instalación especial', service_type_id: 1, node_id: 1, sector_id: 1 }); expect(body).not.toHaveProperty('circuit_id')
  })
})
