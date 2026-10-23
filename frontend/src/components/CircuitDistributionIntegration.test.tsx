import { fireEvent, render, screen, waitFor, within } from '../test/render'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router'
import { CatalogAdmin } from './CatalogAdmin'
import { CircuitEditModal } from './CircuitEditModal'
import { QuickCatalogCreate } from './QuickCatalogCreate'
import { CircuitDetail } from '../pages/CircuitDetail'
import { PermissionProvider } from '../auth/permissions'
import { listDistributionDevices, listDistributionPorts } from '../api'
import type { Circuit, DistributionDevice, DistributionPort } from '../types/catalog'
import { portGenerationResponse } from '../test/portGeneration'
import { jsonResponse } from '../test/fixtures'

const created_at = '2026-01-01T12:00:00Z'
const node = { id: 1, name: 'Nodo A', active: true, created_at }
const customer = { ...node, customer_code: 'CLIENTE', name: 'Cliente' }
const device: DistributionDevice = { ...node, id: 10, node_id: 1, name: 'SW A', description: null, port_count: 1, circuit_count: 1 }
const port: DistributionPort = { ...node, id: 20, distribution_device_id: 10, name: 'sfp+1', description: null, circuit_count: 1 }
const circuit: Circuit = { id: 1, customer_id: 1, node_id: 1, node, sector_id: 1, sector: { ...node, name: 'Sector A' }, circuit_code: 'C-1', description: 'Enlace actual', active: true, created_at, distribution_device_id: 10, distribution_port_id: 20, distribution_device: device, distribution_port: port }
const oldShow = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal'), oldClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close')
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value() { this.setAttribute('open', '') } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value() { this.removeAttribute('open') } })
})
afterAll(() => {
  for (const [key, descriptor] of [['showModal', oldShow], ['close', oldClose]] as const) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, key, descriptor)
    else Reflect.deleteProperty(HTMLDialogElement.prototype, key)
  }
})
function mockApi(item: Circuit = circuit) {
  const devices = [{ ...device, ...item.distribution_device }, { ...device, id: 11, name: 'SW B' }], ports = [{ ...port, ...item.distribution_port }]
  const mock = vi.fn((path: string, init?: RequestInit): Promise<Response> => {
    const url = new URL(path, 'http://localhost'), data = init?.body ? JSON.parse(String(init.body)) : {}
    const generation = portGenerationResponse(url, init, ports, 22)
    if (generation) return generation
    if (init?.method === 'POST' || init?.method === 'PATCH') {
      if (url.pathname === '/api/distribution-devices') { const row = { ...device, id: 12, ...data }; devices.push(row); return Promise.resolve(jsonResponse(row, 201)) }
      if (url.pathname === '/api/distribution-ports') { const row = { ...port, id: 22, ...data }; ports.push(row); return Promise.resolve(jsonResponse(row, 201)) }
      return Promise.resolve(jsonResponse({ ...item, ...data }, init.method === 'POST' ? 201 : 200))
    }
    if (url.pathname === '/api/distribution-devices') return Promise.resolve(jsonResponse(devices.filter(row => row.node_id === Number(url.searchParams.get('node_id')) && (row.active || url.searchParams.get('include_inactive') === 'true'))))
    if (url.pathname === '/api/distribution-ports') return Promise.resolve(jsonResponse(ports.filter(row => row.distribution_device_id === Number(url.searchParams.get('distribution_device_id')) && (row.active || url.searchParams.get('include_inactive') === 'true'))))
    if (url.pathname.endsWith('/operational-detail')) return Promise.resolve(jsonResponse({ circuit: item, customer, current_capacity: null, current_capacity_unit: null, initial_activation: null }))
    if (url.pathname === '/api/circuits') return Promise.resolve(jsonResponse([item]))
    if (url.pathname === '/api/customers') return Promise.resolve(jsonResponse([customer]))
    if (url.pathname === '/api/nodes') return Promise.resolve(jsonResponse([node, { ...node, id: 2, name: 'Nodo B' }]))
    if (url.pathname === '/api/sectors') return Promise.resolve(jsonResponse([{ ...node, name: 'Sector A' }]))
    return Promise.resolve(jsonResponse([]))
  })
  vi.stubGlobal('fetch', mock); return mock
}
const writes = (mock: ReturnType<typeof mockApi>) => mock.mock.calls.filter(([path, init]) => !path.endsWith('/preview') && (init?.method === 'POST' || init?.method === 'PATCH'))
const combo = (name: string) => screen.getByRole('combobox', { name })
async function choose(name: string, value: string) { const control = combo(name); await waitFor(() => expect(control).toBeEnabled()); fireEvent.click(control); fireEvent.click(screen.getByRole('option', { name: value })) }
async function openList() { render(<MemoryRouter><CatalogAdmin kind="circuits" /></MemoryRouter>); await screen.findByRole('table'); fireEvent.click(screen.getByRole('button', { name: 'Nuevo circuito' })) }
async function fillCreate() {
  fireEvent.change(screen.getByLabelText(/^Cliente/), { target: { value: '1' } }); fireEvent.change(screen.getByLabelText(/^Código de circuito/), { target: { value: 'C-2' } }); fireEvent.change(screen.getByLabelText(/^Descripción/), { target: { value: 'Datos escritos' } }); fireEvent.change(screen.getByLabelText(/^Sector/), { target: { value: '1' } })
  await choose('Nodo', 'Nodo A')
}
function openEdit(item = circuit) {
  render(<MemoryRouter><CircuitEditModal circuit={item} onSaved={vi.fn()} onCancel={vi.fn()} /></MemoryRouter>)
}
async function save() { await waitFor(() => expect(screen.getByRole('button', { name: 'Guardar' })).toBeEnabled()); fireEvent.click(screen.getByRole('button', { name: 'Guardar' })) }

describe('contratos de circuito y distribución', () => {
  it('crea desde el listado con identificadores y conserva todos los datos', async () => {
    const mock = mockApi(); await openList(); await fillCreate(); await choose('Equipo de distribución', 'SW A'); await choose('Puerto de distribución', 'sfp+1'); await save()
    await waitFor(() => expect(writes(mock)).toHaveLength(1))
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ circuit_code: 'C-2', description: 'Datos escritos', node_id: 1, distribution_device_id: 10, distribution_port_id: 20 })
  })
  it('crea un equipo sin puerto y conserva el catálogo aunque se cancele el circuito', async () => {
    const mock = mockApi(); await openList(); await fillCreate()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Nuevo equipo de distribución' })).toBeEnabled()); fireEvent.click(screen.getByRole('button', { name: 'Nuevo equipo de distribución' }))
    const modal = within(screen.getByRole('dialog')); await waitFor(() => expect(modal.getByRole('button', { name: 'Crear' })).toBeEnabled())
    fireEvent.change(modal.getByLabelText(/^Nombre/), { target: { value: 'SW creado' } }); fireEvent.click(modal.getByRole('button', { name: 'Crear' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument()); expect(combo('Equipo de distribución')).toHaveValue('SW creado'); expect(screen.getByLabelText(/^Descripción/)).toHaveValue('Datos escritos')
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' })); expect(writes(mock)).toHaveLength(1); expect(writes(mock)[0][0]).toBe('/api/distribution-devices')
    expect(mock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)
  })
  it('envía equipo sin puerto en un alta válida', async () => {
    const mock = mockApi(); await openList(); await fillCreate(); await choose('Equipo de distribución', 'SW A'); await save()
    await waitFor(() => expect(writes(mock)).toHaveLength(1)); const body = JSON.parse(String(writes(mock)[0][1]?.body))
    expect(body.distribution_device_id).toBe(10); expect(body).not.toHaveProperty('distribution_port_id')
  })
  it('PATCH de otros datos omite asociaciones, incluidas las históricas inactivas', async () => {
    const item = { ...circuit, distribution_device: { ...device, active: false }, distribution_port: { ...port, active: false } }
    const mock = mockApi(item); openEdit(item)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Guardar' })).toBeEnabled()); expect(combo('Equipo de distribución')).toHaveValue('SW A'); expect(screen.getByText(/Equipo asignado inactivo/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/^Descripción/), { target: { value: 'Corregida' } }); await save()
    await waitFor(() => expect(writes(mock)).toHaveLength(1)); const body = JSON.parse(String(writes(mock)[0][1]?.body))
    expect(body.description).toBe('Corregida'); expect(body).not.toHaveProperty('distribution_device_id'); expect(body).not.toHaveProperty('distribution_port_id')
  })
  it('retira equipo y puerto en la misma actualización con null explícito', async () => {
    const mock = mockApi(); openEdit(); await waitFor(() => expect(combo('Equipo de distribución')).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar Equipo de distribución' })); await save()
    await waitFor(() => expect(writes(mock)).toHaveLength(1)); expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ distribution_device_id: null, distribution_port_id: null })
  })
  it('retira solamente el puerto sin cambiar el equipo', async () => {
    const mock = mockApi(); openEdit(); await waitFor(() => expect(combo('Puerto de distribución')).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar Puerto de distribución' })); await save()
    await waitFor(() => expect(writes(mock)).toHaveLength(1)); const body = JSON.parse(String(writes(mock)[0][1]?.body))
    expect(body.distribution_port_id).toBeNull(); expect(body).not.toHaveProperty('distribution_device_id')
  })
  it('cambiar el nodo elimina ambas referencias sin enviar una relación incompatible', async () => {
    const mock = mockApi(); openEdit(); await waitFor(() => expect(screen.getByRole('button', { name: 'Guardar' })).toBeEnabled()); await choose('Nodo', 'Nodo B'); await save()
    await waitFor(() => expect(writes(mock)).toHaveLength(1)); expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ node_id: 2, distribution_device_id: null, distribution_port_id: null })
  })
  it('crear circuito rápido permite anidar las altas de equipo y puerto sin perder datos ni enviar anticipadamente', async () => {
    const mock = mockApi(), created = vi.fn()
    render(<QuickCatalogCreate kind="circuit" customer={customer} onCreated={created} onCancel={vi.fn()} />)
    const parent = within(screen.getByRole('dialog', { name: 'Nuevo circuito' }))
    fireEvent.change(parent.getByLabelText(/^Código de circuito/), { target: { value: 'RAPIDO' } }); fireEvent.change(parent.getByLabelText(/^Descripción/), { target: { value: 'Escrito antes de abrir modales' } })
    await waitFor(() => expect(parent.getByRole('option', { name: 'Sector A' })).toBeInTheDocument()); fireEvent.change(parent.getByLabelText(/^Sector/), { target: { value: '1' } }); await choose('Nodo', 'Nodo A')
    for (const [kind, name] of [['equipo', 'SW rápido'], ['puerto', 'sfp10']] as const) {
      await waitFor(() => expect(screen.getByRole('button', { name: `Nuevo ${kind} de distribución` })).toBeEnabled()); fireEvent.click(screen.getByRole('button', { name: `Nuevo ${kind} de distribución` }))
      const modal = within(screen.getByRole('dialog', { name: `Nuevo ${kind} de distribución` }))
      expect(parent.getByRole('button', { name: 'Guardar' })).toBeDisabled()
      if (kind === 'equipo') {
        await waitFor(() => expect(modal.getByRole('button', { name: 'Crear' })).toBeEnabled())
        fireEvent.change(modal.getByLabelText(/^Nombre/), { target: { value: name } }); fireEvent.click(modal.getByRole('button', { name: 'Crear' }))
      } else {
        await choose('Nomenclatura', 'Fibra (sfp+)')
        fireEvent.change(modal.getByLabelText(/^Número del puerto/), { target: { value: '10' } })
        await waitFor(() => expect(modal.getByRole('button', { name: 'Crear puertos' })).toBeEnabled())
        fireEvent.click(modal.getByRole('button', { name: 'Crear puertos' }))
      }
      await waitFor(() => expect(screen.queryByRole('dialog', { name: `Nuevo ${kind} de distribución` })).not.toBeInTheDocument())
    }
    expect(parent.getByLabelText(/^Descripción/)).toHaveValue('Escrito antes de abrir modales'); expect(writes(mock)).toHaveLength(2)
    await save(); await waitFor(() => expect(created).toHaveBeenCalledOnce())
    expect(JSON.parse(String(writes(mock).at(-1)![1]?.body))).toMatchObject({ customer_id: 1, circuit_code: 'RAPIDO', description: 'Escrito antes de abrir modales', distribution_device_id: 12, distribution_port_id: 22 })
  })
})

describe('consulta de distribución actual', () => {
  it.each([true, false])('Auditor consulta ficha, sin atribuir distribución a históricos; tiene asignación: %s', async assigned => {
    mockApi(assigned ? circuit : { ...circuit, distribution_device_id: null, distribution_port_id: null, distribution_device: null, distribution_port: null })
    render(<PermissionProvider permissions={['circuits.view']}><MemoryRouter initialEntries={['/circuits/1']}><Routes><Route path="/circuits/:id" element={<CircuitDetail />} /></Routes></MemoryRouter></PermissionProvider>)
    const section = within(await screen.findByRole('region', { name: 'Distribución actual del circuito' }))
    expect(section.getByText('Nodo A')).toBeInTheDocument()
    if (assigned) { expect(section.getByText('SW A')).toBeInTheDocument(); expect(section.getByText('sfp+1')).toBeInTheDocument() }
    else expect(section.getAllByText('No asignado')).toHaveLength(2)
    expect(screen.queryByRole('button', { name: /Editar/ })).not.toBeInTheDocument(); expect(screen.queryByRole('button', { name: 'Nuevo equipo de distribución' })).not.toBeInTheDocument()
  })
})

describe('catálogos de distribución paginados', () => {
  it.each(['devices', 'ports'])('recorre todas las páginas de %s conservando padre, filtro y señal', async kind => {
    const controller = new AbortController()
    const mock = vi.fn((path: string) => {
      const url = new URL(path, 'http://localhost'), offset = Number(url.searchParams.get('offset'))
      return Promise.resolve(jsonResponse(Array.from({ length: offset ? 1 : 200 }, (_, index) => kind === 'devices' ? { ...device, id: index + offset } : { ...port, id: index + offset })))
    }); vi.stubGlobal('fetch', mock)
    const result = await (kind === 'devices' ? listDistributionDevices(1, controller.signal, true) : listDistributionPorts(10, controller.signal, true))
    expect(result).toHaveLength(201); expect(mock).toHaveBeenCalledTimes(2)
    for (const [path] of mock.mock.calls) { const url = new URL(path, 'http://localhost'); expect(url.searchParams.get('include_inactive')).toBe('true'); expect(url.searchParams.get(kind === 'devices' ? 'node_id' : 'distribution_device_id')).toBe(kind === 'devices' ? '1' : '10') }
  })
  it('rechaza una respuesta inválida en lugar de mostrar opciones incompletas', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ items: [] }))))
    await expect(listDistributionDevices(1)).rejects.toThrow('La API no devolvió un catálogo válido.')
  })
})

describe('IP de gestión CPE', () => {
  it.each(['192.0.2.10', '2001:db8::10', ''])('crea el circuito con IP opcional %s sin perder distribución', async ip => {
    const mock = mockApi(); await openList(); await fillCreate()
    fireEvent.change(screen.getByLabelText('IP de gestión CPE'), { target: { value: ip } })
    await choose('Equipo de distribución', 'SW A'); await choose('Puerto de distribución', 'sfp+1')
    expect(screen.getByLabelText('IP de gestión CPE')).toHaveValue(ip)
    await save(); await waitFor(() => expect(writes(mock)).toHaveLength(1))
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ cpe_management_ip: ip || null, node_id: 1, distribution_device_id: 10, distribution_port_id: 20 })
  })
  it.each(['2001:db8::20', ''])('edita o limpia una IP existente: %s', async ip => {
    const item = { ...circuit, cpe_management_ip: '192.0.2.10' }, mock = mockApi(item); openEdit(item)
    expect(screen.getByLabelText('IP de gestión CPE')).toHaveValue('192.0.2.10')
    fireEvent.change(screen.getByLabelText('IP de gestión CPE'), { target: { value: ip } })
    await save(); await waitFor(() => expect(writes(mock)).toHaveLength(1))
    const body = JSON.parse(String(writes(mock)[0][1]?.body))
    expect(body.cpe_management_ip).toBe(ip || null)
    expect(body).not.toHaveProperty('distribution_device_id'); expect(body).not.toHaveProperty('distribution_port_id')
  })
  it('omite la IP sin cambios al editar otros datos', async () => {
    const item = { ...circuit, cpe_management_ip: '2001:db8::1' }, mock = mockApi(item); openEdit(item)
    fireEvent.change(screen.getByLabelText(/^Descripción/), { target: { value: 'Descripción corregida' } })
    await save(); await waitFor(() => expect(writes(mock)).toHaveLength(1))
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).not.toHaveProperty('cpe_management_ip')
  })
  it('conserva la IP en creación rápida mientras cambia el nodo', async () => {
    const mock = mockApi(), created = vi.fn()
    render(<QuickCatalogCreate kind="circuit" customer={customer} onCreated={created} onCancel={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/^Código de circuito/), { target: { value: 'IP-QUICK' } })
    fireEvent.change(screen.getByLabelText(/^Descripción/), { target: { value: 'Rápido' } })
    fireEvent.change(screen.getByLabelText('IP de gestión CPE'), { target: { value: '2001:db8::10' } })
    await waitFor(() => expect(screen.getByRole('option', { name: 'Sector A' })).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText(/^Sector/), { target: { value: '1' } }); await choose('Nodo', 'Nodo A')
    expect(screen.getByLabelText('IP de gestión CPE')).toHaveValue('2001:db8::10')
    await save(); await waitFor(() => expect(created).toHaveBeenCalledOnce())
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ cpe_management_ip: '2001:db8::10', node_id: 1 })
  })
  it('muestra el error del servidor y conserva la entrada inválida', async () => {
    const original = mockApi()
    vi.stubGlobal('fetch', vi.fn((path: string, init?: RequestInit) => init?.method === 'PATCH'
      ? Promise.resolve(jsonResponse({ detail: [{ loc: ['body', 'cpe_management_ip'], msg: 'Introduce una dirección IPv4 o IPv6 válida' }] }, 422))
      : original(path, init)))
    openEdit(); fireEvent.change(screen.getByLabelText('IP de gestión CPE'), { target: { value: 'cpe.example.net' } })
    await save(); expect(await screen.findByText(/IP de gestión CPE: Introduce una dirección/)).toBeInTheDocument()
    expect(screen.getByLabelText('IP de gestión CPE')).toHaveValue('cpe.example.net')
    expect(screen.getByLabelText('IP de gestión CPE')).toHaveAttribute('aria-invalid', 'true')
  })
  it.each(['192.0.2.10', '2001:db8::10', null])('muestra el dato informativo al Auditor: %s', async ip => {
    mockApi({ ...circuit, cpe_management_ip: ip })
    render(<PermissionProvider permissions={['circuits.view']}><MemoryRouter initialEntries={['/circuits/1']}><Routes><Route path="/circuits/:id" element={<CircuitDetail />} /></Routes></MemoryRouter></PermissionProvider>)
    expect(await screen.findByText('IP de gestión CPE')).toBeInTheDocument()
    expect(screen.getByText(ip || 'No asignada')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Editar circuito/ })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('IP de gestión CPE')).not.toBeInTheDocument()
  })
})
