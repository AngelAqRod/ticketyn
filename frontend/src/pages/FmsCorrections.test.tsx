import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router'
import App from '../App'
import { OperationModal } from '../components/OperationModal'
import { OperationsTable } from '../components/OperationsTable'
import { jsonResponse } from '../test/fixtures'
import type { Circuit, Customer, NamedCatalog } from '../types/catalog'
import type { FmsKind, Operation } from '../types/fms'

const created_at = '2020-01-01T12:00:00Z'
const people: NamedCatalog[] = [{ id: 11, name: 'Operador FMS', active: true, created_at }]
const clients: Customer[] = [1, 2, 3].map((id) => ({ id, customer_code: `C${id}`, name: ['Cliente Alfa', 'Cliente Beta', 'Cliente sin circuitos'][id - 1], active: true, created_at }))
const svc = { id: 1, name: 'Internet dedicado', active: true, created_at }
const base: Circuit = { node_id: 1, node: { id: 1, name: 'Nodo actual', active: true }, sector_id: 1, sector: { id: 1, name: 'Sector actual', active: true }, id: 1, customer_id: 1, circuit_code: 'ALFA-1', description: 'Enlace principal Alfa', active: true, created_at, initial_capacity: '250.000000', initial_capacity_unit: 'Mbps', service_type_id: 1, service_type: svc }
const other: Circuit = { ...base, id: 2, customer_id: 2, circuit_code: 'BETA-2', description: 'Enlace Beta', initial_capacity: '2.500000', initial_capacity_unit: 'Gbps' }
const originalShow = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal'), originalClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close')
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value(this: HTMLDialogElement) { this.setAttribute('open', '') } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value(this: HTMLDialogElement) { this.removeAttribute('open') } })
})
afterAll(() => {
  if (originalShow) Object.defineProperty(HTMLDialogElement.prototype, 'showModal', originalShow); else Reflect.deleteProperty(HTMLDialogElement.prototype, 'showModal')
  if (originalClose) Object.defineProperty(HTMLDialogElement.prototype, 'close', originalClose); else Reflect.deleteProperty(HTMLDialogElement.prototype, 'close')
})
interface Options { nodeMissing?: boolean; sectorMissing?: boolean; detail?: (id: number) => Promise<Response>; deleteConflict?: boolean; emptyInterventions?: boolean; missingDescription?: boolean; serviceInactive?: boolean; reasonInactive?: boolean }
function api(options: Options = {}) {
  let circuits = [{ ...base, ...(options.nodeMissing ? { node_id: null, node: null } : {}), ...(options.sectorMissing ? { sector_id: null, sector: null } : {}), service_type: { ...svc, active: !options.serviceInactive } }, { ...other }], serviceTypes = [{ ...svc, active: !options.serviceInactive }]
  let reasons = [{ id: 1, name: 'Falta de pago', description: 'Inicial', active: !options.reasonInactive, created_at }]
  const activation = () => ({ id: 1, circuit_id: 1, circuit: { ...circuits[0], ...(options.missingDescription ? { description: '' } : {}) }, responsible_id: 11, responsible: people[0], effective_at: created_at, created_at, reference: 'ACT-000001', activation_number: 1 })
  const mock = vi.fn((path: string, init?: RequestInit): Promise<Response> => {
    if (init?.method === 'DELETE') {
      if (options.deleteConflict) return Promise.resolve(jsonResponse({ detail: 'Tiene historial operativo asociado. Puedes desactivarlo en lugar de eliminarlo.' }, 409))
      circuits = circuits.filter((item) => item.id !== Number(path.split('/').at(-1)))
      return Promise.resolve(new Response(null, { status: 204 }))
    }
    if (init?.method === 'POST' || init?.method === 'PATCH') {
      const payload = JSON.parse(String(init.body)), id = init.method === 'POST' ? 9 : Number(path.split('/').at(-1))
      if (path.startsWith('/api/circuits')) {
        const saved: Circuit = { ...base, ...(circuits.find((item) => item.id === id) ?? {}), ...payload, id }
        saved.service_type = serviceTypes.find((item) => item.id === saved.service_type_id) ?? null
        circuits = circuits.some((item) => item.id === id) ? circuits.map((item) => item.id === id ? saved : item) : [...circuits, saved]
        return Promise.resolve(jsonResponse(saved, init.method === 'POST' ? 201 : 200))
      }
      if (path.startsWith('/api/service-types')) {
        const saved = { ...svc, ...(serviceTypes.find((item) => item.id === id) ?? {}), ...payload, id }
        serviceTypes = serviceTypes.some((item) => item.id === id) ? serviceTypes.map((item) => item.id === id ? saved : item) : [...serviceTypes, saved]
        return Promise.resolve(jsonResponse(saved, init.method === 'POST' ? 201 : 200))
      }
      if (path.startsWith('/api/deactivation-reasons')) {
        const saved = { ...(reasons.find((item) => item.id === id) ?? reasons[0]), ...payload, id }
        reasons = reasons.some((item) => item.id === id) ? reasons.map((item) => item.id === id ? saved : item) : [...reasons, saved]
        return Promise.resolve(jsonResponse(saved, init.method === 'POST' ? 201 : 200))
      }
      return Promise.resolve(jsonResponse({ ...activation(), ...payload }, 201))
    }
    if (path.startsWith('/api/nodes')) return Promise.resolve(jsonResponse([{ id: 1, name: 'Nodo disponible', active: true, created_at }]))
    if (path.startsWith('/api/sectors')) return Promise.resolve(jsonResponse([{ id: 1, name: 'Sector actual', active: true, created_at }]))
    if (path === '/health') return Promise.resolve(jsonResponse({ status: 'ok' }))
    if (path.includes('operational-detail')) {
      const id = Number(path.split('/')[3]); if (options.detail) return options.detail(id)
      const circuit = circuits.find((item) => item.id === id)!
      return Promise.resolve(jsonResponse({ circuit, customer: clients.find((item) => item.id === circuit.customer_id), current_capacity: circuit.initial_capacity, current_capacity_unit: circuit.initial_capacity_unit, initial_activation: null }))
    }
    if (path.includes('/interventions')) return Promise.resolve(jsonResponse(options.emptyInterventions ? [] : [{ id: 1, activation_id: 1, responsible: people[0], occurred_at: created_at, created_at, content: 'Intervención' }]))
    if (path === '/api/activations/1') return Promise.resolve(jsonResponse(activation()))
    if (path.startsWith('/api/customers/')) return Promise.resolve(jsonResponse(clients.find((item) => item.id === Number(path.split('/').at(-1)))))
    if (path.includes('/customers?')) return Promise.resolve(jsonResponse(clients))
    if (path.includes('/circuits?')) return Promise.resolve(jsonResponse(circuits))
    if (path.includes('/responsibles?')) return Promise.resolve(jsonResponse(people))
    if (path.includes('/service-types?')) return Promise.resolve(jsonResponse(serviceTypes.filter((item) => path.includes('include_inactive=true') || item.active)))
    if (path.includes('/deactivation-reasons?')) return Promise.resolve(jsonResponse(reasons.filter((item) => path.includes('include_inactive=true') || item.active)))
    return Promise.resolve(jsonResponse([]))
  })
  vi.stubGlobal('fetch', mock)
  return mock
}
async function select(label: string, name: string) { const combo = screen.getByRole('combobox', { name: label }); await waitFor(() => expect(combo).toBeEnabled()); fireEvent.click(combo); fireEvent.click(await screen.findByRole('option', { name })) }
function openRoute(path: string) { render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>) }
const writes = (mock: ReturnType<typeof api>) => mock.mock.calls.filter(([, init]) => init?.method === 'POST' || init?.method === 'PATCH' || init?.method === 'DELETE')

it('filtra circuitos por cliente y limpia la selección al cambiarlo', async () => {
  const mock = api(); render(<OperationModal kind="activations" onCancel={vi.fn()} onSaved={vi.fn()} />)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Registrar' })).toBeEnabled())
  expect(screen.getByRole('combobox', { name: 'Circuito' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Nuevo circuito' })).toBeDisabled()
  expect(mock.mock.calls.some(([path]) => path.startsWith('/api/circuits?'))).toBe(false)
  await select('Cliente', 'C1 — Cliente Alfa')
  const combo = screen.getByRole('combobox', { name: 'Circuito' })
  await waitFor(() => expect(combo).toBeEnabled())
  fireEvent.click(combo)
  expect(screen.getByRole('option', { name: 'ALFA-1 — Enlace principal Alfa' })).toBeInTheDocument()
  expect(screen.queryByRole('option', { name: 'BETA-2 — Enlace Beta' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('option', { name: 'ALFA-1 — Enlace principal Alfa' }))
  await select('Cliente', 'C2 — Cliente Beta')
  expect(combo).toHaveValue('')
  await waitFor(() => expect(combo).toBeEnabled())
  fireEvent.click(combo)
  expect(screen.queryByRole('option', { name: 'ALFA-1 — Enlace principal Alfa' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('option', { name: 'BETA-2 — Enlace Beta' }))
  await select('Responsable', 'Operador FMS')
  fireEvent.click(screen.getByRole('button', { name: 'Registrar' }))
  await waitFor(() => expect(writes(mock)).toHaveLength(1))
  expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ customer_id: 2, circuit_id: 2 })
  expect(mock.mock.calls.some(([path]) => path.startsWith('/api/circuits?customer_id=2&'))).toBe(true)
})

it('informa clientes sin circuitos y sitúa Nuevo circuito junto a su selector', async () => {
  api(); render(<OperationModal kind="activations" onCancel={vi.fn()} onSaved={vi.fn()} />)
  await select('Cliente', 'C3 — Cliente sin circuitos')
  const combo = screen.getByRole('combobox', { name: 'Circuito' })
  await waitFor(() => expect(combo).toBeEnabled())
  expect(combo.closest('.flex-wrap')).toContainElement(screen.getByRole('button', { name: 'Nuevo circuito' }))
  const client = screen.getByRole('combobox', { name: 'Cliente' })
  expect(client.closest('.flex-wrap')).toContainElement(screen.getByRole('button', { name: 'Nuevo cliente' }))
  fireEvent.click(combo)
  expect(screen.getByText('Este cliente no tiene circuitos registrados.')).toBeInTheDocument()
})

it('crea circuito con tipo de servicio para el cliente seleccionado desde activaciones', async () => {
  const mock = api(); render(<OperationModal kind="activations" onCancel={vi.fn()} onSaved={vi.fn()} />)
  await select('Cliente', 'C2 — Cliente Beta')
  fireEvent.click(screen.getByRole('button', { name: 'Nuevo circuito' }))
  const form = await screen.findByRole('form', { name: 'Crear circuito rápido' })
  await waitFor(() => expect(within(form).getByRole('combobox', { name: 'Tipo de servicio' })).toBeEnabled())
  fireEvent.change(within(form).getByLabelText(/^Código de circuito/), { target: { value: 'BETA-NUEVO' } })
  fireEvent.change(within(form).getByLabelText(/^Descripción/), { target: { value: 'Nuevo enlace' } })
  await select('Tipo de servicio', 'Internet dedicado')
  if (form.getAttribute('aria-label') === 'Crear circuito rápido') { fireEvent.change(within(form).getByLabelText(/^Sector/), { target: { value: '1' } }); await waitFor(() => expect(within(screen.getByRole('dialog', { name: 'Nuevo circuito' })).getByRole('combobox', { name: 'Nodo' })).toBeEnabled()); fireEvent.click(within(screen.getByRole('dialog', { name: 'Nuevo circuito' })).getByRole('combobox', { name: 'Nodo' })); fireEvent.click(screen.getByRole('listbox', { name: 'Nodo' }).querySelector('[role=option]')!) }
  fireEvent.submit(form)
  await waitFor(() => expect(screen.queryByRole('form', { name: 'Crear circuito rápido' })).not.toBeInTheDocument())
  expect(screen.getByRole('combobox', { name: 'Circuito' })).toHaveValue('BETA-NUEVO — Nuevo enlace')
  expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ customer_id: 2, service_type_id: 1 })
})

it.each([['250.000000', 'Mbps'], ['2.500000', 'Gbps'], [null, null]])('precarga capacidad vigente %s %s, incluyendo desconocida', async (value, unit) => {
  api({ detail: () => Promise.resolve(jsonResponse({ circuit: base, customer: clients[0], current_capacity: value, current_capacity_unit: unit, initial_activation: null })) })
  render(<OperationModal kind="capacity-changes" circuit={base} onCancel={vi.fn()} onSaved={vi.fn()} />)
  await waitFor(() => expect(screen.queryByText('Consultando capacidad vigente...')).not.toBeInTheDocument())
  expect(screen.getByLabelText('Capacidad anterior (opcional)')).toHaveValue(value === null ? null : Number(value))
  expect(screen.getByLabelText('Unidad de capacidad anterior (opcional)')).toHaveValue(unit ?? 'Mbps')
})

it('actualiza sugerencias al cambiar circuito y descarta una respuesta antigua tardía', async () => {
  let first: (value: Response) => void = () => {}
  const pending = new Promise<Response>((resolve) => { first = resolve })
  api({ detail: (id) => id === 1 ? pending : Promise.resolve(jsonResponse({ circuit: other, current_capacity: '2.5', current_capacity_unit: 'Gbps' })) })
  render(<OperationModal kind="capacity-changes" onCancel={vi.fn()} onSaved={vi.fn()} />)
  await select('Cliente', 'C1 — Cliente Alfa'); await select('Circuito', 'ALFA-1 — Enlace principal Alfa'); await select('Cliente', 'C2 — Cliente Beta'); await select('Circuito', 'BETA-2 — Enlace Beta')
  await waitFor(() => expect(screen.getByLabelText('Capacidad anterior (opcional)')).toHaveValue(2.5))
  await act(async () => { first(jsonResponse({ circuit: base, current_capacity: '250', current_capacity_unit: 'Mbps' })) })
  expect(screen.getByLabelText('Capacidad anterior (opcional)')).toHaveValue(2.5)
  expect(screen.getByLabelText('Unidad de capacidad anterior (opcional)')).toHaveValue('Gbps')
})

it('respeta capacidad y unidad manuales aunque la consulta termine después', async () => {
  let finish: (value: Response) => void = () => {}
  api({ detail: () => new Promise<Response>((resolve) => { finish = resolve }) })
  render(<OperationModal kind="capacity-changes" circuit={base} onCancel={vi.fn()} onSaved={vi.fn()} />)
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Responsable' })).toBeEnabled())
  fireEvent.change(screen.getByLabelText('Capacidad anterior (opcional)'), { target: { value: '1.125' } })
  fireEvent.change(screen.getByLabelText('Unidad de capacidad anterior (opcional)'), { target: { value: 'Gbps' } })
  await act(async () => { finish(jsonResponse({ circuit: base, current_capacity: '250', current_capacity_unit: 'Mbps' })) })
  expect(screen.getByLabelText('Capacidad anterior (opcional)')).toHaveValue(1.125)
  expect(screen.getByLabelText('Unidad de capacidad anterior (opcional)')).toHaveValue('Gbps')
})

it('muestra error recuperable de consulta y permite indicar capacidad manual', async () => {
  const mock = api({ detail: () => Promise.resolve(jsonResponse({ detail: 'Consulta no disponible' }, 503)) })
  render(<OperationModal kind="capacity-changes" circuit={base} onCancel={vi.fn()} onSaved={vi.fn()} />)
  await screen.findByText('Consulta no disponible')
  expect(screen.getByRole('button', { name: 'Reintentar capacidad' })).toBeEnabled()
  await select('Responsable', 'Operador FMS')
  fireEvent.change(screen.getByLabelText('Capacidad anterior (opcional)'), { target: { value: '250' } })
  fireEvent.change(screen.getByLabelText(/^Capacidad nueva/), { target: { value: '500' } })
  fireEvent.click(screen.getByRole('button', { name: 'Registrar' }))
  await waitFor(() => expect(writes(mock)).toHaveLength(1))
  expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ previous_capacity: '250', previous_unit: 'Mbps' })
})

it.each(['activations', 'capacity-changes', 'circuit-lifecycle'] as FmsKind[])('muestra descripción en una columna separada en %s', (kind) => {
  const row: Operation = { id: 1, circuit_id: 1, circuit: base, responsible_id: 11, responsible: people[0], effective_at: created_at, created_at }
  render(<MemoryRouter><OperationsTable kind={kind} items={[row, { ...row, id: 2, circuit: { ...base, description: '' } }]} /></MemoryRouter>)
  const headers = screen.getAllByRole('columnheader').map((item) => item.textContent)
  expect(headers.indexOf('Descripción del circuito')).toBe(headers.indexOf('Circuito') + 1)
  const description = screen.getByText('Enlace principal Alfa').closest('td')!
  expect(description).not.toContainElement(screen.getAllByRole('link', { name: 'ALFA-1' })[0])
  expect(screen.getByText('Sin descripción')).toBeInTheDocument()
})

it.each([false, true])('mueve Nueva intervención a la bitácora (vacía=%s) y muestra información del circuito', async (emptyInterventions) => {
  api({ emptyInterventions }); openRoute('/activations/1')
  const log = await screen.findByRole('region', { name: 'Bitácora de activación' })
  const button = within(log).getByRole('button', { name: 'Nueva intervención' })
  expect(button).toBeEnabled(); expect(document.querySelector('.page-heading')).not.toContainElement(button)
  const info = screen.getByRole('region', { name: 'Información de activación' })
  expect(info).toHaveTextContent('Enlace principal Alfa'); expect(info).toHaveTextContent('Cliente Alfa'); expect(info).toHaveTextContent('Fecha efectiva de activación')
  fireEvent.click(button)
  expect(await screen.findByRole('form', { name: 'Registrar intervención de activación' })).toBeInTheDocument()
})

it('muestra Sin descripción en una activación con descripción vacía', async () => {
  api({ missingDescription: true }); openRoute('/activations/1')
  expect(await screen.findByText('Sin descripción')).toBeInTheDocument()
})

it('reutiliza acciones y editor del circuito desde la cabecera', async () => {
  const mock = api(); openRoute('/circuits/1')
  const edit = await screen.findByRole('button', { name: 'Editar ALFA-1' })
  const heading = document.querySelector<HTMLElement>('.page-heading')!
  expect(heading).toContainElement(edit)
  expect(within(heading).getByRole('link', { name: 'Ver tickets de ALFA-1' })).toHaveAttribute('href', '/tickets?circuit_id=1')
  expect(screen.getByText('Internet dedicado')).toBeInTheDocument()
  edit.focus(); fireEvent.click(edit)
  const dialog = await screen.findByRole('dialog', { name: 'Editar circuito ALFA-1' })
  await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Guardar' })).toBeEnabled())
  expect(within(dialog).queryByRole('table')).not.toBeInTheDocument()
  expect(within(dialog).getByRole('combobox', { name: 'Tipo de servicio' })).toHaveValue('Internet dedicado')
  fireEvent.change(within(dialog).getByLabelText(/^Descripción/), { target: { value: 'Descripción corregida' } })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Guardar' }))
  await screen.findByText('Cambios guardados correctamente.')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ description: 'Descripción corregida', service_type_id: 1, initial_capacity: '250.000000' })
})

it('activa/desactiva desde la ficha con confirmación y sin cambios operativos', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValue(true), mock = api()
  openRoute('/circuits/1')
  fireEvent.click(await screen.findByRole('button', { name: 'Desactivar ALFA-1' }))
  expect(writes(mock)).toHaveLength(0)
  fireEvent.click(screen.getByRole('button', { name: 'Desactivar ALFA-1' }))
  await screen.findByRole('button', { name: 'Activar ALFA-1' })
  expect(confirm).toHaveBeenCalledWith(expect.stringContaining('tickets históricos'))
  fireEvent.click(screen.getByRole('button', { name: 'Activar ALFA-1' }))
  await screen.findByRole('button', { name: 'Desactivar ALFA-1' })
  expect(writes(mock).map(([, init]) => JSON.parse(String(init?.body)))).toEqual([{ active: false }, { active: true }])
  confirm.mockRestore()
})

it('mantiene protección de eliminación con historial FMS y permite cancelar', async () => {
  const mock = api({ deleteConflict: true }); openRoute('/circuits/1')
  fireEvent.click(await screen.findByRole('button', { name: 'Eliminar ALFA-1' }))
  const dialog = screen.getByRole('dialog', { name: 'Eliminar circuito' })
  expect(dialog).toHaveTextContent('ALFA-1'); expect(dialog).toHaveTextContent('Enlace principal Alfa')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Eliminar definitivamente' }))
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('historial operativo')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancelar' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(writes(mock).filter(([, init]) => init?.method === 'DELETE')).toHaveLength(1)
})

it('elimina desde la ficha y vuelve al listado con confirmación de éxito', async () => {
  api(); openRoute('/circuits/1')
  fireEvent.click(await screen.findByRole('button', { name: 'Eliminar ALFA-1' }))
  fireEvent.click(screen.getByRole('button', { name: 'Eliminar definitivamente' }))
  expect(await screen.findByText('Circuito ALFA-1 eliminado correctamente.')).toBeInTheDocument()
  expect(await screen.findByRole('table', { name: 'Circuitos' })).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'ALFA-1' })).not.toBeInTheDocument()
})

it.each([['Tipos de servicio', 'tipo de servicio', '/api/service-types'], ['Motivos de baja', 'motivo de baja', '/api/deactivation-reasons']])('administra %s desde Catálogos', async (title, singular, endpoint) => {
  const mock = api(), confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
  openRoute('/catalogs'); fireEvent.click(screen.getByRole('button', { name: title }))
  await screen.findByRole('table', { name: title })
  fireEvent.click(screen.getByRole('button', { name: `Nuevo ${singular}` }))
  fireEvent.change(screen.getByLabelText(/^Nombre/), { target: { value: 'Registro configurable' } })
  fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
  await screen.findByText('Registro creado correctamente.')
  fireEvent.click(screen.getByRole('button', { name: 'Editar Registro configurable' }))
  fireEvent.change(screen.getByLabelText(/^Nombre/), { target: { value: 'Registro corregido' } })
  fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
  await screen.findByText('Cambios guardados correctamente.')
  fireEvent.click(screen.getByRole('button', { name: 'Desactivar Registro corregido' }))
  await screen.findByRole('button', { name: 'Activar Registro corregido' })
  fireEvent.click(screen.getByRole('button', { name: 'Activar Registro corregido' }))
  await screen.findByRole('button', { name: 'Desactivar Registro corregido' })
  expect(writes(mock).map(([path]) => path)).toEqual([endpoint, `${endpoint}/9`, `${endpoint}/9`, `${endpoint}/9`])
  confirm.mockRestore()
})

it('no borra capacidad manual al volver a seleccionar el mismo circuito', async () => {
  api(); render(<OperationModal kind="capacity-changes" onCancel={vi.fn()} onSaved={vi.fn()} />)
  await select('Cliente', 'C1 — Cliente Alfa')
  await select('Circuito', 'ALFA-1 — Enlace principal Alfa')
  await waitFor(() => expect(screen.getByLabelText('Capacidad anterior (opcional)')).toHaveValue(250))
  fireEvent.change(screen.getByLabelText('Capacidad anterior (opcional)'), { target: { value: '300' } })
  await select('Circuito', 'ALFA-1 — Enlace principal Alfa')
  expect(screen.getByLabelText('Capacidad anterior (opcional)')).toHaveValue(300)
})

it('no borra circuito al volver a seleccionar el mismo cliente', async () => {
  api(); render(<OperationModal kind="activations" onCancel={vi.fn()} onSaved={vi.fn()} />)
  await select('Cliente', 'C1 — Cliente Alfa'); await select('Circuito', 'ALFA-1 — Enlace principal Alfa')
  await select('Cliente', 'C1 — Cliente Alfa')
  expect(screen.getByRole('combobox', { name: 'Circuito' })).toHaveValue('ALFA-1 — Enlace principal Alfa')
})

it('conserva el tipo de servicio histórico inactivo al editar y permite desasignarlo', async () => {
  const mock = api({ serviceInactive: true }); openRoute('/circuits/1')
  fireEvent.click(await screen.findByRole('button', { name: 'Editar ALFA-1' }))
  const form = screen.getByRole('form', { name: 'Editar circuito' })
  await waitFor(() => expect(within(form).getByRole('button', { name: 'Guardar' })).toBeEnabled())
  const combo = within(form).getByRole('combobox', { name: 'Tipo de servicio' })
  expect(combo).toHaveValue('Internet dedicado')
  fireEvent.click(combo)
  expect(screen.getByRole('option', { name: /Internet dedicado.*Inactivo/ })).toHaveAttribute('aria-disabled', 'true')
  fireEvent.keyDown(combo, { key: 'Escape' })
  fireEvent.click(within(form).getByRole('button', { name: 'Limpiar Tipo de servicio' }))
  fireEvent.click(within(form).getByRole('button', { name: 'Guardar' }))
  await screen.findByText('Cambios guardados correctamente.')
  expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ service_type_id: null })
})

it('no ofrece motivos inactivos para nuevas bajas, pero permite reactivar sin motivo', async () => {
  const mock = api({ reasonInactive: true }); render(<OperationModal kind="circuit-lifecycle" circuit={base} onCancel={vi.fn()} onSaved={vi.fn()} />)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Registrar' })).toBeEnabled())
  fireEvent.click(screen.getByRole('combobox', { name: 'Motivo de baja' }))
  expect(screen.queryByRole('option', { name: 'Falta de pago' })).not.toBeInTheDocument()
  fireEvent.keyDown(screen.getByRole('combobox', { name: 'Motivo de baja' }), { key: 'Escape' })
  fireEvent.change(screen.getByLabelText('Tipo de operación'), { target: { value: 'REACTIVATE' } })
  await select('Responsable', 'Operador FMS')
  fireEvent.click(screen.getByRole('button', { name: 'Registrar' }))
  await waitFor(() => expect(writes(mock)).toHaveLength(1))
  expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ operation_type: 'REACTIVATE', reason_id: null })
})


it('normaliza ambas capacidades informativas sin cambiar los valores originales', () => {
  const item: Operation = { id: 7, circuit_id: 1, circuit: base, responsible_id: 11, responsible: people[0], effective_at: created_at, created_at, operation_type: 'INCREASE', previous_capacity: '100.000000', previous_unit: 'Mbps', new_capacity: '2000.000000', new_unit: 'Mbps' }
  render(<MemoryRouter><OperationsTable kind="capacity-changes" items={[item]} /></MemoryRouter>)
  expect(screen.getByText('100 Mbps → 2 Gbps')).toBeInTheDocument()
  expect(item.previous_capacity).toBe('100.000000')
  expect(item.new_capacity).toBe('2000.000000')
  expect(item.new_unit).toBe('Mbps')
})

it('normaliza capacidad inicial y vigente en la ficha del circuito', async () => {
  api({ detail: () => Promise.resolve(jsonResponse({ circuit: { ...base, initial_capacity: '2000.000000', initial_capacity_unit: 'Mbps' }, customer: clients[0], current_capacity: '1758.500000', current_capacity_unit: 'Mbps', initial_activation: null })) })
  openRoute('/circuits/1')
  expect(await screen.findByText('2 Gbps')).toBeInTheDocument()
  expect(screen.getByText('1.759 Gbps')).toBeInTheDocument()
})


it.each(['activations', 'capacity-changes', 'circuit-lifecycle'] as FmsKind[])('asigna Sector pendiente en %s sin modificar otro circuito', async kind => {
  const mock = api({ sectorMissing: true }), saved = vi.fn()
  render(<OperationModal kind={kind} onCancel={vi.fn()} onSaved={saved} />)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Registrar' })).toBeEnabled())
  await select('Cliente', 'C1 — Cliente Alfa')
  await select('Circuito', 'ALFA-1 — Enlace principal Alfa')
  expect(screen.getByLabelText(/^Sector/)).toBeRequired()
  await select('Responsable', 'Operador FMS')
  if (kind === 'capacity-changes') fireEvent.change(screen.getByLabelText(/^Capacidad nueva\s*\*?$/), { target: { value: '500' } })
  if (kind === 'circuit-lifecycle') fireEvent.change(screen.getByLabelText('Tipo de operación'), { target: { value: 'REACTIVATE' } })
  fireEvent.submit(screen.getByRole('form', { name: 'Registrar operación' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Selecciona un Sector')
  expect(writes(mock)).toHaveLength(0)
  fireEvent.change(screen.getByLabelText(/^Sector/), { target: { value: '1' } })
  fireEvent.submit(screen.getByRole('form', { name: 'Registrar operación' }))
  await waitFor(() => expect(writes(mock)).toHaveLength(1))
  expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ circuit_id: 1, sector_id: 1 })
  expect(saved).toHaveBeenCalledOnce()
})


it.each(['activations', 'capacity-changes', 'circuit-lifecycle'] as FmsKind[])('requiere Nodo pendiente en %s y envía su asignación', async kind => {
  const mock = api({ nodeMissing: true }), saved = vi.fn()
  render(<OperationModal kind={kind} onCancel={vi.fn()} onSaved={saved} />)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Registrar' })).toBeEnabled())
  await select('Cliente', 'C1 — Cliente Alfa')
  await select('Circuito', 'ALFA-1 — Enlace principal Alfa'); await select('Responsable', 'Operador FMS')
  if (kind === 'capacity-changes') fireEvent.change(screen.getByLabelText(/^Capacidad nueva\s*\*?$/), { target: { value: '500' } })
  if (kind === 'circuit-lifecycle') fireEvent.change(screen.getByLabelText('Tipo de operación'), { target: { value: 'REACTIVATE' } })
  fireEvent.submit(screen.getByRole('form', { name: 'Registrar operación' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Selecciona un Nodo')
  expect(writes(mock)).toHaveLength(0)
  fireEvent.change(screen.getByLabelText(/^Nodo\s*\*?$/), { target: { value: '1' } })
  fireEvent.submit(screen.getByRole('form', { name: 'Registrar operación' }))
  await waitFor(() => expect(writes(mock)).toHaveLength(1))
  expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ circuit_id: 1, node_id: 1 })
  expect(saved).toHaveBeenCalledOnce()
})

it.each(['capacity-changes', 'circuit-lifecycle'] as FmsKind[])('filtra circuitos por cliente en %s sin ofrecer creación rápida', async kind => {
  const mock = api(); render(<OperationModal kind={kind} onCancel={vi.fn()} onSaved={vi.fn()} />)
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Cliente' })).toBeEnabled())
  expect(screen.getByRole('combobox', { name: 'Cliente' })).toHaveAttribute('aria-required', 'true')
  expect(screen.getByRole('combobox', { name: 'Circuito' })).toBeDisabled()
  expect(screen.getByRole('combobox', { name: 'Circuito' })).toHaveAttribute('placeholder', 'Selecciona un cliente primero')
  expect(mock.mock.calls.some(([path]) => path.startsWith('/api/circuits?'))).toBe(false)
  expect(screen.queryByRole('button', { name: 'Nuevo cliente' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Nuevo circuito' })).not.toBeInTheDocument()
  const labels = Array.from(screen.getByRole('form', { name: 'Registrar operación' }).querySelectorAll('label')).slice(0, 5).map(label => label.textContent)
  expect(labels).toEqual(['Cliente*', 'Circuito*', 'Nodo*', 'Sector*', 'Tipo de operación'])
  await select('Cliente', 'C1 — Cliente Alfa')
  const combo = screen.getByRole('combobox', { name: 'Circuito' })
  await waitFor(() => expect(combo).toBeEnabled()); fireEvent.click(combo)
  expect(screen.getByRole('option', { name: 'ALFA-1 — Enlace principal Alfa' })).toBeInTheDocument()
  expect(screen.queryByRole('option', { name: 'BETA-2 — Enlace Beta' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('option', { name: 'ALFA-1 — Enlace principal Alfa' }))
  expect(screen.getByLabelText(/^Nodo/)).toHaveValue('Nodo actual')
  expect(screen.getByLabelText(/^Sector/)).toHaveValue('Sector actual')
  await select('Cliente', 'C1 — Cliente Alfa')
  expect(combo).toHaveValue('ALFA-1 — Enlace principal Alfa')
  await select('Cliente', 'C2 — Cliente Beta')
  expect(combo).toHaveValue('')
  expect(screen.getByLabelText(/^Nodo/)).toHaveValue('')
  expect(screen.getByLabelText(/^Sector/)).toHaveValue('')
  await waitFor(() => expect(combo).toBeEnabled()); fireEvent.click(combo)
  expect(screen.queryByRole('option', { name: 'ALFA-1 — Enlace principal Alfa' })).not.toBeInTheDocument()
  expect(screen.getByRole('option', { name: 'BETA-2 — Enlace Beta' })).toBeInTheDocument()
  fireEvent.click(screen.getByRole('option', { name: 'BETA-2 — Enlace Beta' }))
  expect(mock.mock.calls.some(([path]) => path.startsWith('/api/circuits?customer_id=2&'))).toBe(true)
  await select('Cliente', 'C3 — Cliente sin circuitos')
  await waitFor(() => expect(combo).toBeEnabled()); fireEvent.click(combo)
  expect(screen.getByText('Este cliente no tiene circuitos registrados.')).toBeInTheDocument()
})

it.each(['capacity-changes', 'circuit-lifecycle'] as FmsKind[])('limpia los datos derivados y conserva el borrador independiente en %s', async kind => {
  api({ nodeMissing: true, sectorMissing: true }); render(<OperationModal kind={kind} onCancel={vi.fn()} onSaved={vi.fn()} />)
  await select('Cliente', 'C1 — Cliente Alfa'); await select('Circuito', 'ALFA-1 — Enlace principal Alfa'); await select('Responsable', 'Operador FMS')
  fireEvent.change(screen.getByLabelText(/^Nodo/), { target: { value: '1' } })
  fireEvent.change(screen.getByLabelText(/^Sector/), { target: { value: '1' } })
  fireEvent.change(screen.getByLabelText(/^Fecha y hora efectiva/), { target: { value: '2020-01-01T08:30' } })
  if (kind === 'capacity-changes') {
    await waitFor(() => expect(screen.getByLabelText('Capacidad anterior (opcional)')).toHaveValue(250))
    fireEvent.change(screen.getByLabelText('Capacidad anterior (opcional)'), { target: { value: '300' } })
    fireEvent.change(screen.getByLabelText(/^Capacidad nueva/), { target: { value: '700' } })
  } else await select('Motivo de baja', 'Falta de pago')
  fireEvent.change(screen.getByLabelText(kind === 'capacity-changes' ? 'Descripción (opcional)' : 'Observaciones (opcional)'), { target: { value: 'Borrador del técnico' } })
  await select('Cliente', 'C2 — Cliente Beta')
  expect(screen.getByRole('combobox', { name: 'Circuito' })).toHaveValue('')
  expect(screen.getByLabelText(/^Nodo/)).toHaveValue('')
  expect(screen.getByLabelText(/^Sector/)).toHaveValue('')
  expect(screen.getByLabelText(/^Fecha y hora efectiva/)).toHaveValue('2020-01-01T08:30')
  expect(screen.getByRole('combobox', { name: 'Responsable' })).toHaveValue('Operador FMS')
  expect(screen.getByLabelText(kind === 'capacity-changes' ? 'Descripción (opcional)' : 'Observaciones (opcional)')).toHaveValue('Borrador del técnico')
  if (kind === 'capacity-changes') {
    expect(screen.getByLabelText('Capacidad anterior (opcional)')).toHaveValue(null)
    expect(screen.getByLabelText(/^Capacidad nueva/)).toHaveValue(700)
    await select('Circuito', 'BETA-2 — Enlace Beta')
    await waitFor(() => expect(screen.getByLabelText('Capacidad anterior (opcional)')).toHaveValue(2.5))
  } else expect(screen.getByRole('combobox', { name: 'Motivo de baja' })).toHaveValue('Falta de pago')
})

it.each(['capacity-changes', 'circuit-lifecycle'] as FmsKind[])('precarga y bloquea Cliente/Circuito cuando %s se abre desde la ficha', async kind => {
  const mock = api(); render(<OperationModal kind={kind} circuit={base} onCancel={vi.fn()} onSaved={vi.fn()} />)
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Cliente' })).toHaveValue('C1 — Cliente Alfa'))
  expect(screen.getByRole('combobox', { name: 'Cliente' })).toBeDisabled()
  expect(screen.getByRole('combobox', { name: 'Circuito' })).toBeDisabled()
  expect(screen.getByRole('combobox', { name: 'Circuito' })).toHaveValue('ALFA-1 — Enlace principal Alfa')
  expect(mock.mock.calls.some(([path]) => path.startsWith('/api/circuits?'))).toBe(false)
})

it.each(['capacity-changes', 'circuit-lifecycle'] as FmsKind[])('descarta circuitos tardíos del cliente anterior en %s', async kind => {
  let finish: (response: Response) => void = () => {}
  const pending = new Promise<Response>(resolve => { finish = resolve })
  const mock = api(), original = mock.getMockImplementation()!
  mock.mockImplementation((path, options) => path.startsWith('/api/circuits?customer_id=1&') ? pending : original(path, options))
  render(<OperationModal kind={kind} onCancel={vi.fn()} onSaved={vi.fn()} />)
  await select('Cliente', 'C1 — Cliente Alfa')
  expect(screen.getByRole('combobox', { name: 'Circuito' })).toBeDisabled()
  await select('Cliente', 'C2 — Cliente Beta')
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Circuito' })).toBeEnabled())
  await act(async () => { finish(jsonResponse([base])) })
  fireEvent.click(screen.getByRole('combobox', { name: 'Circuito' }))
  expect(screen.getByRole('option', { name: 'BETA-2 — Enlace Beta' })).toBeInTheDocument()
  expect(screen.queryByRole('option', { name: 'ALFA-1 — Enlace principal Alfa' })).not.toBeInTheDocument()
})

it.each(['capacity-changes', 'circuit-lifecycle'] as FmsKind[])('permite reintentar circuitos del cliente tras un error en %s', async kind => {
  const mock = api(), original = mock.getMockImplementation()!
  let failed = false
  mock.mockImplementation((path, options) => {
    if (path.startsWith('/api/circuits?customer_id=1&') && !failed) { failed = true; return Promise.resolve(jsonResponse({ detail: 'Circuitos no disponibles' }, 503)) }
    return original(path, options)
  })
  render(<OperationModal kind={kind} onCancel={vi.fn()} onSaved={vi.fn()} />)
  await select('Cliente', 'C1 — Cliente Alfa')
  await screen.findByRole('button', { name: 'Reintentar circuitos' })
  expect(screen.getByRole('combobox', { name: 'Circuito' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Registrar' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Reintentar circuitos' }))
  await select('Circuito', 'ALFA-1 — Enlace principal Alfa')
  expect(screen.getByRole('combobox', { name: 'Circuito' })).toHaveValue('ALFA-1 — Enlace principal Alfa')
})

it.each(['activations', 'capacity-changes', 'circuit-lifecycle'] as FmsKind[])('busca por descripción y conserva código/descripcion seleccionados en %s', async kind => {
  const mock = api(), saved = vi.fn()
  render(<OperationModal kind={kind} onCancel={vi.fn()} onSaved={saved} />)
  await select('Cliente', 'C1 — Cliente Alfa')
  const combo = screen.getByRole('combobox', { name: 'Circuito' })
  await waitFor(() => expect(combo).toBeEnabled())
  fireEvent.click(combo); fireEvent.change(combo, { target: { value: 'principal' } })
  expect(screen.getByRole('option', { name: 'ALFA-1 — Enlace principal Alfa' })).toBeInTheDocument()
  expect(screen.queryByRole('option', { name: 'BETA-2 — Enlace Beta' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('option', { name: 'ALFA-1 — Enlace principal Alfa' }))
  expect(combo).toHaveValue('ALFA-1 — Enlace principal Alfa')
  expect(screen.getByLabelText(/^Nodo/)).toHaveValue('Nodo actual')
  expect(screen.getByLabelText(/^Sector/)).toHaveValue('Sector actual')
  await select('Responsable', 'Operador FMS')
  if (kind === 'capacity-changes') {
    await waitFor(() => expect(screen.getByLabelText('Capacidad anterior (opcional)')).toHaveValue(250))
    fireEvent.change(screen.getByLabelText(/^Capacidad nueva/), { target: { value: '500' } })
  }
  if (kind === 'circuit-lifecycle') fireEvent.change(screen.getByLabelText('Tipo de operación'), { target: { value: 'REACTIVATE' } })
  fireEvent.submit(screen.getByRole('form', { name: 'Registrar operación' }))
  await waitFor(() => expect(writes(mock)).toHaveLength(1))
  expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ circuit_id: 1 })
  expect(saved).toHaveBeenCalledOnce()
})

it.each(['activations', 'capacity-changes', 'circuit-lifecycle'] as FmsKind[])('muestra solo el código cuando el circuito no tiene descripción en %s', async kind => {
  api()
  render(<OperationModal kind={kind} circuit={{ ...base, description: '' }} onCancel={vi.fn()} onSaved={vi.fn()} />)
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Circuito' })).toHaveValue('ALFA-1'))
  expect(screen.getByRole('combobox', { name: 'Circuito' })).toBeDisabled()
})
