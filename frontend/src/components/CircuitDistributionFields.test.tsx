import { useState } from 'react'
import { act, fireEvent, render, screen, waitFor, within } from '../test/render'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { PermissionProvider } from '../auth/permissions'
import { CircuitDistributionFields } from './CircuitDistributionFields'
import type { Circuit, DistributionDevice, DistributionPort } from '../types/catalog'
import { portGenerationResponse } from '../test/portGeneration'
import { jsonResponse } from '../test/fixtures'

const device = (id = 10, node_id = 1, name = 'Equipo A', active = true): DistributionDevice => ({ id, node_id, name, active, description: null, created_at: '', port_count: 0, circuit_count: 0 })
const port = (id = 20, distribution_device_id = 10, name = 'sfp+1', active = true): DistributionPort => ({ id, distribution_device_id, name, active, description: null, created_at: '', circuit_count: 0 })
const permissions = ['circuits.create', 'circuits.edit', ...['distribution_devices', 'distribution_ports'].flatMap(module => ['lookup', 'create'].map(action => `${module}.${action}`))]
const historical: Circuit = { id: 1, node_id: 1, customer_id: 1, circuit_code: 'C-1', description: 'Enlace', active: true, created_at: '', distribution_device_id: 10, distribution_port_id: 20, distribution_device: device(), distribution_port: port() }
const combo = (name: string) => screen.getByRole('combobox', { name })
const equipment = () => combo('Equipo de distribución')
const connector = () => combo('Puerto de distribución')
const postCalls = (mock: ReturnType<typeof mockApi>) => mock.mock.calls.filter(([, init]) => init?.method === 'POST')
function mockApi(devices = [device()], ports = [port()], override?: (url: URL, init?: RequestInit) => Promise<Response> | undefined) {
  const mock = vi.fn((path: string, init?: RequestInit): Promise<Response> => {
    const url = new URL(path, 'http://localhost')
    const result = override?.(url, init)
    if (result) return result
    const generation = portGenerationResponse(url, init, ports, 21)
    if (generation) return generation
    if (init?.method === 'POST') {
      const input = JSON.parse(String(init.body))
      if (url.pathname.endsWith('distribution-devices')) { const row = { ...device(11), ...input }; devices.push(row); return Promise.resolve(jsonResponse(row, 201)) }
      const row = { ...port(21), ...input }; ports.push(row); return Promise.resolve(jsonResponse(row, 201))
    }
    const all = url.searchParams.get('include_inactive') === 'true'
    return Promise.resolve(jsonResponse(url.pathname.endsWith('distribution-devices')
      ? devices.filter(row => row.node_id === Number(url.searchParams.get('node_id')) && (all || row.active))
      : ports.filter(row => row.distribution_device_id === Number(url.searchParams.get('distribution_device_id')) && (all || row.active))))
  })
  vi.stubGlobal('fetch', mock)
  return mock
}
function Harness({ initialNode = '', original }: { initialNode?: string; original?: Circuit }) {
  const [node, setNode] = useState(initialNode), [selectedDevice, setDevice] = useState(String(original?.distribution_device_id ?? ''))
  const [selectedPort, setPort] = useState(String(original?.distribution_port_id ?? '')), [open, setOpen] = useState(false)
  return <form onSubmit={event => { event.preventDefault(); throw new Error('El modal no debe enviar el circuito') }}>
    <input aria-label="Datos escritos" defaultValue="Datos del circuito conservados" />
    <select aria-label="Nodo de prueba" value={node} onChange={event => { setNode(event.target.value); setDevice(''); setPort('') }}><option value="">Sin nodo</option><option value="1">Nodo A</option><option value="2">Nodo B</option></select>
    <CircuitDistributionFields nodeId={node} nodeName={`Nodo ${node === '1' ? 'A' : 'B'}`} deviceId={selectedDevice} portId={selectedPort} original={original} onModalChange={setOpen} onChange={(d, p) => { setDevice(d); setPort(p) }} />
    <output aria-label="Asociaciones">{selectedDevice || '-'} / {selectedPort || '-'}</output><output aria-label="Modal abierto">{String(open)}</output>
  </form>
}
async function choose(name: string, option: string) { const input = combo(name); await waitFor(() => expect(input).toBeEnabled()); fireEvent.click(input); fireEvent.click(screen.getByRole('option', { name: option })) }
async function newModal(kind: 'equipo' | 'puerto') {
  const button = screen.getByRole('button', { name: `Nuevo ${kind} de distribución` })
  await waitFor(() => expect(button).toBeEnabled()); fireEvent.click(button)
  const modal = within(screen.getByRole('dialog', { name: `Nuevo ${kind} de distribución` }))
  if (kind === 'equipo') await waitFor(() => expect(modal.getByRole('button', { name: 'Crear' })).toBeEnabled())
  else await waitFor(() => expect(modal.getByRole('combobox', { name: 'Nomenclatura' })).toBeEnabled())
  return modal
}
const originalShow = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal')
const originalClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close')
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value(this: HTMLDialogElement) { this.setAttribute('open', '') } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value(this: HTMLDialogElement) { this.removeAttribute('open') } })
})
afterAll(() => {
  if (originalShow) Object.defineProperty(HTMLDialogElement.prototype, 'showModal', originalShow)
  else Reflect.deleteProperty(HTMLDialogElement.prototype, 'showModal')
  if (originalClose) Object.defineProperty(HTMLDialogElement.prototype, 'close', originalClose)
  else Reflect.deleteProperty(HTMLDialogElement.prototype, 'close')
})

describe('asignación opcional de distribución', () => {
  it.each([false, true])('conserva orden natural en 24 opciones, incluida la referencia inactiva al editar: %s', async editing => {
    const ports = Array.from({ length: 24 }, (_, index) => port(100 + index, 10, `SFP${index + 1}`, index !== 1))
    const mock = mockApi([device()], ports)
    render(<Harness initialNode="1" original={editing ? { ...historical, distribution_port_id: ports[1].id, distribution_port: ports[1] } : undefined} />)
    if (!editing) await choose('Equipo de distribución', 'Equipo A')
    await waitFor(() => expect(connector()).toBeEnabled()); fireEvent.click(connector())
    const names = within(screen.getByRole('listbox', { name: 'Puerto de distribución' })).getAllByRole('option').map(option => option.textContent!.match(/SFP\d+/)![0])
    expect(names).toEqual(ports.filter(row => row.active || editing).map(row => row.name))
    expect(mock.mock.calls.some(([path]) => path.includes('/distribution-ports?') && path.includes('include_inactive=true'))).toBe(true)
    if (editing) {
      expect(screen.getByRole('option', { name: /SFP2\s*\(Inactivo\)/ })).toHaveAttribute('aria-disabled', 'true')
      fireEvent.click(screen.getByRole('button', { name: 'Limpiar Puerto de distribución' })); fireEvent.click(connector())
      expect(screen.queryByRole('option', { name: /SFP2\s*\(Inactivo\)/ })).not.toBeInTheDocument()
    }
  })
  it('deshabilita sin padre, filtra por nodo/equipo y nunca elige automáticamente', async () => {
    const mock = mockApi([device(), device(11, 2, 'Equipo B'), device(12, 1, 'Equipo retirado', false)], [port(), port(22, 11, 'ether2')])
    render(<Harness />)
    expect(equipment()).toBeDisabled(); expect(connector()).toBeDisabled(); expect(mock).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Nuevo equipo de distribución' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Nodo de prueba'), { target: { value: '1' } })
    await waitFor(() => expect(equipment()).toBeEnabled()); expect(equipment()).toHaveValue('')
    fireEvent.click(equipment()); expect(screen.queryByRole('option', { name: 'Equipo B' })).not.toBeInTheDocument(); expect(screen.queryByRole('option', { name: 'Equipo retirado' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('option', { name: 'Equipo A' }))
    await waitFor(() => expect(connector()).toBeEnabled()); expect(connector()).toHaveValue('')
    fireEvent.click(connector()); expect(screen.queryByRole('option', { name: 'ether2' })).not.toBeInTheDocument(); fireEvent.click(screen.getByRole('option', { name: 'sfp+1' }))
    expect(screen.getByLabelText('Asociaciones')).toHaveTextContent('10 / 20')
    expect(mock.mock.calls.some(([path]) => path.includes('node_id=1'))).toBe(true)
    expect(mock.mock.calls.some(([path]) => path.includes('distribution_device_id=10'))).toBe(true)
  })
  it('limpia el puerto al cambiar equipo y ambas asociaciones al cambiar nodo sin borrar otros datos', async () => {
    mockApi([device(), device(11, 1, 'Equipo C')]); render(<Harness initialNode="1" />)
    await choose('Equipo de distribución', 'Equipo A'); await choose('Puerto de distribución', 'sfp+1')
    await choose('Equipo de distribución', 'Equipo C'); expect(screen.getByLabelText('Asociaciones')).toHaveTextContent('11 / -')
    fireEvent.change(screen.getByLabelText('Nodo de prueba'), { target: { value: '2' } })
    expect(screen.getByLabelText('Asociaciones')).toHaveTextContent('- / -'); expect(connector()).toBeDisabled()
    expect(screen.getByLabelText('Datos escritos')).toHaveValue('Datos del circuito conservados')
  })
  it('conserva y permite retirar asociaciones históricas inactivas sin ofrecerlas para nuevas asignaciones', async () => {
    mockApi([device(10, 1, 'Equipo retirado', false)], [port(20, 10, 'Puerto retirado', false)])
    render(<Harness initialNode="1" original={{ ...historical, distribution_device: device(10, 1, 'Equipo retirado', false), distribution_port: port(20, 10, 'Puerto retirado', false) }} />)
    await waitFor(() => expect(equipment()).toBeEnabled()); expect(equipment()).toHaveValue('Equipo retirado'); expect(screen.getByText(/Equipo asignado inactivo/)).toBeInTheDocument()
    await waitFor(() => expect(connector()).toBeEnabled()); expect(connector()).toHaveValue('Puerto retirado'); expect(screen.getByText(/Puerto asignado inactivo/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Nuevo puerto de distribución' })).toBeDisabled()
    fireEvent.click(connector()); expect(screen.getByRole('option', { name: /Puerto retirado/ })).toHaveAttribute('aria-disabled', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar Puerto de distribución' })); expect(screen.getByLabelText('Asociaciones')).toHaveTextContent('10 / -')
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar Equipo de distribución' })); expect(screen.getByLabelText('Asociaciones')).toHaveTextContent('- / -')
  })
  it('ignora respuestas tardías de otro nodo incluso cuando fetch no respeta la cancelación', async () => {
    let resolve!: (response: Response) => void
    const mock = mockApi([], [], (url) => url.searchParams.get('node_id') === '1' ? new Promise(done => { resolve = done }) : undefined)
    render(<Harness initialNode="1" />)
    fireEvent.change(screen.getByLabelText('Nodo de prueba'), { target: { value: '2' } })
    await waitFor(() => expect(equipment()).toBeEnabled())
    await act(async () => resolve(jsonResponse([device()])))
    fireEvent.click(equipment()); expect(screen.queryByRole('option', { name: 'Equipo A' })).not.toBeInTheDocument()
    expect(mock.mock.calls[0][1]?.signal?.aborted).toBe(true)
  })
  it('ignora respuestas tardías de puertos del equipo anterior', async () => {
    let resolve!: (response: Response) => void
    mockApi([device(), device(11, 1, 'Equipo C')], [port(22, 11, 'Puerto C')], url => url.searchParams.get('distribution_device_id') === '10' ? new Promise(done => { resolve = done }) : undefined)
    render(<Harness initialNode="1" />); await choose('Equipo de distribución', 'Equipo A'); await choose('Equipo de distribución', 'Equipo C')
    await waitFor(() => expect(connector()).toBeEnabled()); await act(async () => resolve(jsonResponse([port()])))
    fireEvent.click(connector()); expect(screen.getByRole('option', { name: 'Puerto C' })).toBeInTheDocument(); expect(screen.queryByRole('option', { name: 'sfp+1' })).not.toBeInTheDocument()
  })
  it('muestra errores de red, permite reintentar y preserva el formulario', async () => {
    let failed = true
    mockApi(undefined, undefined, url => url.pathname.endsWith('distribution-devices') && failed ? Promise.reject(new Error('offline')) : undefined)
    render(<Harness initialNode="1" />)
    expect(await screen.findByText(/No se pudo conectar con la API/)).toBeInTheDocument(); expect(equipment()).toBeDisabled()
    failed = false; fireEvent.click(screen.getByRole('button', { name: 'Reintentar equipos' })); await choose('Equipo de distribución', 'Equipo A')
    expect(screen.getByLabelText('Datos escritos')).toHaveValue('Datos del circuito conservados')
  })
  it('cancela las consultas al desmontarse', async () => {
    const mock = mockApi([], [], () => new Promise(() => {})); const view = render(<Harness initialNode="1" />)
    view.unmount(); expect(mock.mock.calls[0][1]?.signal?.aborted).toBe(true)
  })
})

describe('creación rápida sin abandonar el circuito', () => {
  it('hereda nodo, crea y selecciona equipo, sin enviar el formulario principal', async () => {
    const mock = mockApi(); render(<Harness initialNode="1" />)
    const modal = await newModal('equipo'); expect(modal.getByText('Nodo A')).toBeInTheDocument(); expect(modal.queryByRole('combobox')).not.toBeInTheDocument()
    fireEvent.change(modal.getByLabelText(/^Nombre/), { target: { value: 'Switch nuevo' } }); fireEvent.change(modal.getByLabelText('Descripción (opcional)'), { target: { value: 'Agregación' } })
    fireEvent.click(modal.getByRole('button', { name: 'Crear' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument()); expect(equipment()).toHaveValue('Switch nuevo')
    expect(JSON.parse(String(postCalls(mock)[0][1]?.body))).toEqual({ node_id: 1, name: 'Switch nuevo', description: 'Agregación' })
    expect(screen.getByLabelText('Datos escritos')).toHaveValue('Datos del circuito conservados')
  })
  it('hereda equipo, muestra puertos registrados y selecciona el puerto nuevo', async () => {
    const mock = mockApi(); render(<Harness initialNode="1" />); await choose('Equipo de distribución', 'Equipo A')
    const modal = await newModal('puerto'); expect(modal.getByText('Equipo A')).toBeInTheDocument()
    await choose('Nomenclatura', 'Fibra (sfp+)')
    fireEvent.change(modal.getByLabelText(/^Número del puerto/), { target: { value: '3' } })
    await waitFor(() => expect(modal.getByRole('button', { name: 'Crear puertos' })).toBeEnabled())
    fireEvent.click(modal.getByRole('button', { name: 'Crear puertos' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument()); await waitFor(() => expect(connector()).toHaveValue('sfp+3'))
    const call = postCalls(mock).find(([path]) => path === '/api/distribution-ports')!
    expect(JSON.parse(String(call[1]?.body))).toMatchObject({ distribution_device_id: 10, nomenclature_id: 90, start: 3, preview_token: 'checked' })
  })
  it('rechaza duplicados conservadores incluso inactivos y no fusiona alias ambiguos', async () => {
    const mock = mockApi([device(), device(12, 1, '  SW   ÚNICO  ', false)]); render(<Harness initialNode="1" />)
    const modal = await newModal('equipo'); fireEvent.change(modal.getByLabelText(/^Nombre/), { target: { value: 'sw único' } }); fireEvent.click(modal.getByRole('button', { name: 'Crear' }))
    expect(await modal.findByText(/Ya existe un equipo/)).toBeInTheDocument(); expect(postCalls(mock)).toHaveLength(0)
  })
  it('presenta HTTP 409 y conserva los valores para corregirlos', async () => {
    const mock = mockApi(undefined, undefined, (_url, init) => init?.method === 'POST' ? Promise.resolve(jsonResponse({ detail: 'Nombre registrado por otro operador.' }, 409)) : undefined)
    render(<Harness initialNode="1" />); const modal = await newModal('equipo')
    fireEvent.change(modal.getByLabelText(/^Nombre/), { target: { value: 'Nuevo' } }); fireEvent.click(modal.getByRole('button', { name: 'Crear' }))
    expect(await modal.findByText(/Nombre registrado por otro operador/)).toBeInTheDocument(); expect(modal.getByLabelText(/^Nombre/)).toHaveValue('Nuevo'); expect(postCalls(mock)).toHaveLength(1)
  })
  it('bloquea doble clic y cancela la respuesta si cambia el contexto durante la creación', async () => {
    let resolve!: (response: Response) => void
    const mock = mockApi(undefined, undefined, (_url, init) => init?.method === 'POST' ? new Promise(done => { resolve = done }) : undefined)
    render(<Harness initialNode="1" />); const modal = await newModal('equipo')
    fireEvent.change(modal.getByLabelText(/^Nombre/), { target: { value: 'Nuevo' } }); const form = modal.getByRole('form', { name: 'Crear equipo de distribución' })
    fireEvent.submit(form); fireEvent.submit(form)
    await waitFor(() => expect(postCalls(mock)).toHaveLength(1)); expect(modal.getByLabelText(/^Nombre/)).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Nodo de prueba'), { target: { value: '2' } }); expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await act(async () => resolve(jsonResponse(device(11, 1, 'Nuevo'), 201)))
    expect(screen.getByLabelText('Asociaciones')).toHaveTextContent('- / -'); expect(postCalls(mock)[0][1]?.signal?.aborted).toBe(true)
  })
  it('comprueba de nuevo los duplicados tras una respuesta de red incierta, sin reintento automático', async () => {
    const devices = [device()]
    const mock = mockApi(devices, [], (_url, init) => {
      if (init?.method !== 'POST') return
      devices.push(device(11, 1, 'Creado')); return Promise.reject(new Error('respuesta perdida'))
    })
    render(<Harness initialNode="1" />); const modal = await newModal('equipo'); fireEvent.change(modal.getByLabelText(/^Nombre/), { target: { value: 'Creado' } }); fireEvent.click(modal.getByRole('button', { name: 'Crear' }))
    expect(await modal.findByText(/No se pudo conectar/)).toBeInTheDocument(); expect(postCalls(mock)).toHaveLength(1)
    fireEvent.click(modal.getByRole('button', { name: 'Crear' })); expect(await modal.findByText(/Ya existe un equipo/)).toBeInTheDocument(); expect(postCalls(mock)).toHaveLength(1)
  })
  it('valida nombres vacíos y límites del backend antes de enviar', async () => {
    const mock = mockApi(); render(<Harness initialNode="1" />); const modal = await newModal('equipo')
    fireEvent.click(modal.getByRole('button', { name: 'Crear' })); expect(await modal.findByText(/hasta 255 caracteres/)).toBeInTheDocument()
    fireEvent.change(modal.getByLabelText(/^Nombre/), { target: { value: 'x'.repeat(256) } }); fireEvent.click(modal.getByRole('button', { name: 'Crear' })); expect(postCalls(mock)).toHaveLength(0)
    fireEvent.change(modal.getByLabelText(/^Nombre/), { target: { value: 'Válido' } }); fireEvent.change(modal.getByLabelText('Descripción (opcional)'), { target: { value: 'x'.repeat(10001) } }); fireEvent.click(modal.getByRole('button', { name: 'Crear' })); expect(postCalls(mock)).toHaveLength(0)
  })
})

describe('capacidades de sesión', () => {
  it.each(['Superadministrador', 'Administrador', 'Operador'])('%s selecciona y crea con los permisos del módulo', async () => {
    mockApi(); render(<PermissionProvider permissions={permissions}><Harness initialNode="1" /></PermissionProvider>)
    await waitFor(() => expect(equipment()).toBeEnabled()); expect(screen.getByRole('button', { name: 'Nuevo equipo de distribución' })).toBeEnabled()
    await choose('Equipo de distribución', 'Equipo A'); await waitFor(() => expect(connector()).toBeEnabled()); expect(screen.getByRole('button', { name: 'Nuevo puerto de distribución' })).toBeEnabled()
  })
  it('Auditor conserva lectura y no ejecuta consultas de selección ni crea asociaciones', () => {
    const mock = mockApi(); render(<PermissionProvider permissions={['circuits.view', 'distribution_devices.lookup', 'distribution_ports.lookup']}><Harness initialNode="1" original={historical} /></PermissionProvider>)
    expect(equipment()).toBeDisabled(); expect(equipment()).toHaveValue('Equipo A'); expect(connector()).toBeDisabled(); expect(connector()).toHaveValue('sfp+1')
    expect(screen.getByRole('button', { name: 'Nuevo equipo de distribución' })).toBeDisabled(); expect(mock).not.toHaveBeenCalled()
  })
  it('un rol personalizado con consulta puede seleccionar pero no crear y responde a la revocación de permisos', async () => {
    const mock = mockApi(); const allowed = ['circuits.edit', 'distribution_devices.lookup', 'distribution_ports.lookup']
    const view = render(<PermissionProvider permissions={allowed}><Harness initialNode="1" /></PermissionProvider>)
    await waitFor(() => expect(equipment()).toBeEnabled()); expect(screen.getByRole('button', { name: 'Nuevo equipo de distribución' })).toBeDisabled()
    const calls = mock.mock.calls.length
    view.rerender(<PermissionProvider permissions={['circuits.edit']}><Harness initialNode="1" /></PermissionProvider>)
    expect(equipment()).toBeDisabled(); expect(screen.getByText('Sin permiso para consultar equipos.')).toBeInTheDocument(); expect(mock.mock.calls.length).toBe(calls)
  })
})
