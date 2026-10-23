import { MemoryRouter } from 'react-router'
import { useState } from 'react'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '../test/render'
import { PortCreateDialog } from './PortCreateDialog'
import { CircuitDistributionFields } from './CircuitDistributionFields'
import { PortNomenclatureAdmin } from './PortNomenclatureAdmin'
import { Catalogs } from '../pages/Catalogs'
import { PermissionProvider } from '../auth/permissions'
import { jsonResponse } from '../test/fixtures'
import { portGenerationResponse, testNomenclature } from '../test/portGeneration'
import type { DistributionPort } from '../types/distribution'

beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value() { this.setAttribute('open', '') } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value() { this.removeAttribute('open') } })
})
const choose = async (name: string, option: string) => {
  const element = screen.getByRole('combobox', { name })
  await waitFor(() => expect(element).toBeEnabled()); fireEvent.click(element); fireEvent.click(screen.getByRole('option', { name: option }))
}
function api(ports: DistributionPort[] = [], override?: (url: URL, init?: RequestInit) => Promise<Response> | undefined) {
  const mock = vi.fn((path: string, init?: RequestInit) => {
    const url = new URL(path, 'http://localhost')
    const result = override?.(url, init)
    if (result) return result
    const generation = portGenerationResponse(url, init, ports)
    if (generation) return generation
    if (url.pathname === '/api/distribution-ports') return Promise.resolve(jsonResponse(ports))
    if (url.pathname === '/api/distribution-devices') return Promise.resolve(jsonResponse([{ id: 10, node_id: 1, name: 'CORE', active: true }]))
    return Promise.resolve(jsonResponse([]))
  })
  vi.stubGlobal('fetch', mock)
  return mock
}
async function nomenclature() { await choose('Nomenclatura', 'Fibra (sfp+)') }
const confirm = () => screen.getByRole('button', { name: 'Crear puertos' })

describe('formulario central de puertos', () => {
  it('presenta los 24 nombres de la vista previa en secuencia numérica sin ordenarlos alfabéticamente', async () => {
    api()
    render(<PortCreateDialog deviceId={10} deviceName="CORE" initialMode="complete" onCreated={vi.fn()} onClose={vi.fn()} />)
    await nomenclature(); await waitFor(() => expect(confirm()).toBeEnabled())
    const names = within(screen.getByRole('list', { name: 'Nombres generados' })).getAllByRole('listitem').map(row => row.querySelector('code')?.textContent)
    expect(names).toEqual(Array.from({ length: 24 }, (_, index) => `sfp+${index + 1}`))
  })
  it.each([['N', [], 'sfp+0'], ['X/Y', ['2'], 'sfp+2/0'], ['X/Y/Z', ['1', '0'], 'sfp+1/0/0'], ['W/X/Y/Z', ['1', '2', '3'], 'sfp+1/2/3/0']])('muestra %s desde el backend y confirma un puerto sin nombre manual', async (format, positions, name) => {
    const mock = api(), onCreated = vi.fn()
    render(<PortCreateDialog deviceId={10} deviceName="CORE" onCreated={onCreated} onClose={vi.fn()} />)
    await nomenclature(); fireEvent.change(screen.getByLabelText(/^Formato numérico/), { target: { value: format } })
    for (let index = 0; index < positions.length; index++) fireEvent.change(screen.getByLabelText(`Posición ${format.split('/')[index]}`, { exact: false }), { target: { value: positions[index] } })
    fireEvent.change(screen.getByLabelText(/^Número del puerto/), { target: { value: '0' } })
    await waitFor(() => expect(confirm()).toBeEnabled())
    expect(screen.getByText(name)).toBeInTheDocument(); expect(screen.queryByLabelText('Nombre del puerto')).not.toBeInTheDocument()
    fireEvent.click(confirm()); await waitFor(() => expect(onCreated).toHaveBeenCalledOnce())
    expect(onCreated.mock.calls[0][0][0].name).toBe(name)
    expect(mock.mock.calls.filter(([path, init]) => path === '/api/distribution-ports' && init?.method === 'POST')).toHaveLength(1)
  })
  it('bloquea rango completo con conflictos y conserva existentes al completar faltantes', async () => {
    const ports = [{ id: 1, distribution_device_id: 10, name: 'SFP+2', active: false, description: null, circuit_count: 2, created_at: '' }]
    api(ports); const onCreated = vi.fn()
    render(<PortCreateDialog deviceId={10} deviceName="CORE" initialMode="complete" onCreated={onCreated} onClose={vi.fn()} />)
    await nomenclature(); fireEvent.change(screen.getByLabelText(/^Número final/), { target: { value: '3' } })
    expect(await screen.findByText(/El rango completo está bloqueado/)).toBeInTheDocument(); expect(confirm()).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Modalidad de creación'), { target: { value: 'missing' } })
    expect(await screen.findByText('Se conservarán 1 puertos existentes y se crearán 2 puertos faltantes.')).toBeInTheDocument()
    await waitFor(() => expect(confirm()).toBeEnabled()); fireEvent.click(confirm())
    await waitFor(() => expect(onCreated).toHaveBeenCalledOnce()); expect(onCreated.mock.calls[0][0].map((row: DistributionPort) => row.name)).toEqual(['sfp+1', 'sfp+3'])
    expect(ports[0].active).toBe(false)
  })
  it('rechaza más de 256 nombres antes de consultar y no ejecuta rangos completos', async () => {
    const mock = api()
    render(<PortCreateDialog deviceId={10} deviceName="CORE" initialMode="missing" onCreated={vi.fn()} onClose={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/^Número inicial/), { target: { value: '0' } }); fireEvent.change(screen.getByLabelText(/^Número final/), { target: { value: '256' } })
    await nomenclature()
    expect(screen.getByText(/hasta 256 nombres solicitados/)).toBeInTheDocument(); expect(confirm()).toBeDisabled()
    expect(mock.mock.calls.some(([path]) => path.endsWith('/preview'))).toBe(false)
  })
  it('no crea si el rango ya existe y muestra que está completo', async () => {
    const onCreated = vi.fn(); api([{ id: 1, name: 'sfp+1', distribution_device_id: 10, active: true, description: null, circuit_count: 0, created_at: '' }])
    render(<PortCreateDialog deviceId={10} deviceName="CORE" initialMode="missing" onCreated={onCreated} onClose={vi.fn()} />)
    fireEvent.change(screen.getByLabelText(/^Número final/), { target: { value: '1' } }); await nomenclature()
    expect(await screen.findByText(/El rango ya está completo/)).toBeInTheDocument(); expect(confirm()).toBeDisabled(); expect(onCreated).not.toHaveBeenCalled()
  })
  it('bloquea doble envío y exige revisar tras un conflicto concurrente', async () => {
    let resolve!: (response: Response) => void
    const mock = api([], (url, init) => url.pathname === '/api/distribution-ports' && init?.method === 'POST' ? new Promise(done => { resolve = done }) : undefined)
    render(<PortCreateDialog deviceId={10} deviceName="CORE" onCreated={vi.fn()} onClose={vi.fn()} />)
    await nomenclature(); await waitFor(() => expect(confirm()).toBeEnabled())
    fireEvent.submit(screen.getByRole('form')); fireEvent.submit(screen.getByRole('form'))
    await waitFor(() => expect(mock.mock.calls.filter(([path]) => path === '/api/distribution-ports')).toHaveLength(1))
    resolve(jsonResponse({ detail: 'La información cambió. Revisa la nueva vista previa.' }, 409))
    expect(await screen.findByText(/La información cambió/)).toBeInTheDocument()
    expect(mock.mock.calls.filter(([path]) => path === '/api/distribution-ports')).toHaveLength(1)
    expect(screen.getByLabelText(/^Número del puerto/)).toHaveValue(1)
  })
  it('Auditor no envía consultas ni creaciones y permite cerrar por teclado', () => {
    const mock = api(), onClose = vi.fn()
    render(<PermissionProvider permissions={['distribution_ports.view']}><PortCreateDialog deviceId={10} deviceName="CORE" onCreated={vi.fn()} onClose={onClose} /></PermissionProvider>)
    expect(confirm()).toBeDisabled(); expect(mock).not.toHaveBeenCalled()
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { bubbles: true, cancelable: true })); expect(onClose).toHaveBeenCalledOnce()
  })
})

function CircuitHarness() {
  const [device, setDevice] = useState('10'), [port, setPort] = useState(''), [open, setOpen] = useState(false)
  return <form onSubmit={event => { event.preventDefault(); throw Error('No debe enviar circuito') }}>
    <input aria-label="Descripción padre" defaultValue="Datos conservados" /><output aria-label="Selección">{port || 'Sin selección'}</output>
    <CircuitDistributionFields nodeId="1" nodeName="Nodo" deviceId={device} portId={port} onModalChange={setOpen} onChange={(d, p) => { setDevice(d); setPort(p) }} />
    <button type="submit" disabled={open}>Guardar circuito</button>
  </form>
}
it('creación masiva desde circuitos actualiza opciones sin elegir arbitrariamente ni perder datos', async () => {
  api(); render(<CircuitHarness />)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Nuevo puerto de distribución' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Nuevo puerto de distribución' }))
  expect(screen.getByRole('button', { name: 'Guardar circuito' })).toBeDisabled()
  expect(screen.getByText(/permanecen registrados aunque canceles el circuito/)).toBeInTheDocument()
  await nomenclature(); fireEvent.change(screen.getByLabelText('Modalidad de creación'), { target: { value: 'complete' } })
  fireEvent.change(screen.getByLabelText(/^Número final/), { target: { value: '3' } })
  await waitFor(() => expect(confirm()).toBeEnabled()); fireEvent.click(confirm())
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(screen.getByLabelText('Selección')).toHaveTextContent('Sin selección'); expect(screen.getByLabelText('Descripción padre')).toHaveValue('Datos conservados')
  const selector = screen.getByRole('combobox', { name: 'Puerto de distribución' })
  await waitFor(() => expect(selector).toBeEnabled()); fireEvent.click(selector)
  expect(screen.getByRole('option', { name: 'sfp+3' })).toBeInTheDocument()
})

it('catálogo guarda el prefijo exacto y varios formatos sin editar puertos', async () => {
  const mock = vi.fn((path: string, init?: RequestInit) => Promise.resolve(jsonResponse(init?.method === 'POST' ? testNomenclature : [])))
  vi.stubGlobal('fetch', mock); render(<MemoryRouter><PortNomenclatureAdmin /></MemoryRouter>)
  fireEvent.click(screen.getByRole('button', { name: 'Nueva nomenclatura' }))
  fireEvent.change(screen.getByLabelText(/^Nombre descriptivo/), { target: { value: 'Interfaces' } }); fireEvent.change(screen.getByLabelText(/^Prefijo/), { target: { value: 'SFP+/' } })
  fireEvent.click(screen.getByRole('checkbox', { name: 'X/Y/Z' })); fireEvent.click(screen.getByRole('button', { name: 'Guardar nomenclatura' }))
  await waitFor(() => expect(mock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(true))
  expect(JSON.parse(String(mock.mock.calls.find(([, init]) => init?.method === 'POST')![1]?.body))).toMatchObject({ prefix: 'SFP+/', formats: ['N', 'X/Y/Z'] })
})

it('Auditor consulta el catálogo desde Administración sin acciones de escritura', async () => {
  api(); render(<PermissionProvider permissions={['catalogs.port_nomenclatures.view']}><MemoryRouter><Catalogs /></MemoryRouter></PermissionProvider>)
  expect(await screen.findByRole('heading', { name: 'Nomenclaturas de puertos de distribución' })).toBeInTheDocument()
  expect(await screen.findByText('Fibra')).toBeInTheDocument(); expect(screen.queryByRole('button', { name: 'Nueva nomenclatura' })).not.toBeInTheDocument()
  expect(within(screen.getByRole('table')).queryByRole('button')).not.toBeInTheDocument()
})
