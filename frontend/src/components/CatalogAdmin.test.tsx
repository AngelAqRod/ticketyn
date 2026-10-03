import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { jsonResponse } from '../test/fixtures'
import type { CatalogKind } from '../types/catalog'

const created_at = '2026-01-01T12:00:00Z'
const customer = { id: 1, customer_code: 'CUS-A', name: 'Empresa Alfa', active: true, created_at }
const inactiveCustomer = { id: 2, customer_code: 'CUS-B', name: 'Empresa Beta', active: false, created_at }
const circuit = { id: 1, customer_id: 2, circuit_code: 'LINK-A', description: 'Internet principal', active: true, created_at }
const named = { id: 1, name: 'Nombre inicial', active: true, created_at }
type Row = typeof customer | typeof circuit | typeof named
interface Options { empty?: boolean; fail?: boolean; write?: (path: string, options: RequestInit) => Promise<Response> }
function mockApi(options: Options = {}) {
  const rows: Record<CatalogKind, Row[]> = {
    nodes: [named, { ...named, id: 2, name: 'Nombre inactivo', active: false }], responsibles: [named, { ...named, id: 2, name: 'Nombre inactivo', active: false }],
    customers: [customer, inactiveCustomer],
    circuits: [circuit, { ...circuit, id: 2, circuit_code: 'LINK-B', description: 'Enlace secundario', active: false }],
    sectors: [named, { ...named, id: 2, name: 'Nombre inactivo', active: false }],
    departments: [named, { ...named, id: 2, name: 'Nombre inactivo', active: false }],
    'incident-types': [named, { ...named, id: 2, name: 'Nombre inactivo', active: false }],
  }
  const mock = vi.fn((path: string, init?: RequestInit): Promise<Response> => {
    if (path === '/health') return Promise.resolve(jsonResponse({ status: 'ok' }))
    const resource = path.split('/')[2]?.split('?')[0] as CatalogKind
    if (!(resource in rows)) return Promise.resolve(jsonResponse([]))
    if (init?.method === 'POST' || init?.method === 'PATCH') {
      if (options.write) return options.write(path, init)
      const payload: unknown = JSON.parse(String(init.body))
      if (!payload || typeof payload !== 'object') throw new Error('Invalid test payload')
      const id = init.method === 'POST' ? 3 : Number(path.split('/')[3])
      const existing = rows[resource].find((row) => row.id === id)
      const saved = { ...existing, ...payload, id, created_at } as Row
      rows[resource] = existing ? rows[resource].map((row) => row.id === id ? saved : row) : [...rows[resource], saved]
      return Promise.resolve(jsonResponse(saved, init.method === 'POST' ? 201 : 200))
    }
    return Promise.resolve(options.fail ? jsonResponse({ detail: 'No disponible' }, 503) : jsonResponse(options.empty ? [] : rows[resource]))
  })
  vi.stubGlobal('fetch', mock)
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  return mock
}
const settings = [
  ['customers', '/customers', 'cliente', 'Clientes', 'CUS-A'],
  ['circuits', '/circuits', 'circuito', 'Circuitos', 'LINK-A'],
  ['sectors', '/catalogs', 'sector', 'Sectores', 'Nombre inicial'],
  ['departments', '/catalogs', 'departamento', 'Departamentos', 'Nombre inicial'],
  ['nodes', '/catalogs', 'nodo', 'Nodos', 'Nombre inicial'],
  ['responsibles', '/catalogs', 'responsable', 'Responsables', 'Nombre inicial'],
  ['incident-types', '/catalogs', 'tipo de incidencia', 'Tipos de incidencia', 'Nombre inicial'],
] as const
function open(path: string) { render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>) }
async function selectCatalog(title: string) {
  if (['Departamentos', 'Tipos de incidencia', 'Nodos', 'Responsables'].includes(title)) fireEvent.click(screen.getByRole('button', { name: title }))
  await screen.findByRole('table', { name: title })
}
const field = (label: string) => screen.getByLabelText(new RegExp(`^${label}\\s*\\*?$`))
function writes(mock: ReturnType<typeof mockApi>) { return mock.mock.calls.filter(([, init]) => init?.method === 'POST' || init?.method === 'PATCH') }
afterEach(() => vi.restoreAllMocks())

describe('administración de catálogos', () => {
  it.each(settings)('%s lista activos/inactivos, crea, edita, desactiva y activa', async (resource, path, singular, title, identifier) => {
    const mock = mockApi(); open(path); await selectCatalog(title)
    expect(screen.getByRole('heading', { name: title, level: 1 })).toBeInTheDocument()
    if (resource === 'customers') {
      expect(screen.getByRole('link', { name: 'Ver circuitos de CUS-A' })).toHaveAttribute('href', '/circuits?customer_id=1')
      expect(screen.getByRole('link', { name: 'Ver tickets de CUS-A' })).toHaveAttribute('href', '/tickets?customer_id=1')
    }
    expect(screen.getByText('Activo', { exact: true })).toBeInTheDocument()
    expect(screen.getByText('Inactivo', { exact: true })).toBeInTheDocument()
    expect(mock).toHaveBeenCalledWith(`/api/${resource}?include_inactive=true&limit=200&offset=0`, expect.any(Object))
    fireEvent.click(screen.getByRole('button', { name: `Nuevo ${singular}` }))
    if (resource === 'customers' || resource === 'circuits') fireEvent.change(field(resource === 'customers' ? 'Código de cliente' : 'Código de circuito'), { target: { value: 'MANUAL-NEW' } })
    if (resource === 'circuits') fireEvent.change(field('Cliente'), { target: { value: '2' } })
    fireEvent.change(field(resource === 'circuits' ? 'Descripción' : 'Nombre'), { target: { value: 'Nuevo registro' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await screen.findByText('Registro creado correctamente.')
    const created = writes(mock)[0]
    expect(created[0]).toBe(`/api/${resource}`)
    const expected = resource === 'customers' ? { customer_code: 'MANUAL-NEW', name: 'Nuevo registro', active: true } : resource === 'circuits' ? { circuit_code: 'MANUAL-NEW', description: 'Nuevo registro', customer_id: 2, active: true, node_id: null } : { name: 'Nuevo registro', active: true }
    expect(JSON.parse(String(created[1]?.body))).toEqual(expected)
    fireEvent.click(screen.getByRole('button', { name: `Editar ${identifier}` }))
    expect(field(resource === 'circuits' ? 'Descripción' : 'Nombre')).toHaveValue(resource === 'customers' ? customer.name : resource === 'circuits' ? circuit.description : named.name)
    fireEvent.change(field(resource === 'circuits' ? 'Descripción' : 'Nombre'), { target: { value: 'Corregido' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await screen.findByText('Cambios guardados correctamente.')
    expect(writes(mock)[1][0]).toBe(`/api/${resource}/1`)
    const editedIdentifier = resource === 'customers' || resource === 'circuits' ? identifier : 'Corregido'
    fireEvent.click(screen.getByRole('button', { name: `Desactivar ${editedIdentifier}` }))
    await screen.findByText('Registro desactivado. Los tickets históricos conservan su referencia.')
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('tickets históricos'))
    expect(JSON.parse(String(writes(mock)[2][1]?.body))).toEqual({ active: false })
    fireEvent.click(screen.getByRole('button', { name: `Activar ${editedIdentifier}` }))
    await screen.findByText('Registro activado correctamente.')
    expect(JSON.parse(String(writes(mock)[3][1]?.body))).toEqual({ active: true })
    expect(mock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)
  })
  it.each(['cus-a', 'empresa alfa'])('busca clientes por código o nombre: %s', async (search) => {
    mockApi(); open('/customers'); await screen.findByRole('table')
    fireEvent.change(screen.getByLabelText('Buscar clientes'), { target: { value: search } })
    expect(screen.getByText('CUS-A')).toBeInTheDocument()
    expect(screen.queryByText('CUS-B')).not.toBeInTheDocument()
  })
  it.each(['link-a', 'internet principal', 'empresa beta'])('busca circuitos por código, descripción o cliente: %s', async (search) => {
    const mock = mockApi(); open('/circuits'); await screen.findByRole('table')
    expect(screen.getAllByText('CUS-B — Empresa Beta')).toHaveLength(2)
    expect(mock).toHaveBeenCalledWith('/api/customers?include_inactive=true&limit=200&offset=0', expect.any(Object))
    if (search === 'empresa beta') {
      fireEvent.focus(screen.getByRole('combobox', { name: 'Filtrar por cliente' }))
      fireEvent.change(screen.getByRole('combobox', { name: 'Filtrar por cliente' }), { target: { value: search } })
      fireEvent.click(screen.getByRole('option', { name: 'CUS-B — Empresa Beta' }))
    } else fireEvent.change(screen.getByLabelText('Buscar circuitos'), { target: { value: search } })
    expect(await screen.findByText('LINK-A')).toBeInTheDocument()
    if (search !== 'empresa beta') expect(screen.queryByText('LINK-B')).not.toBeInTheDocument()
  })
  it('rechazar confirmación no envía PATCH ni cambia el registro', async () => {
    const mock = mockApi(); vi.mocked(window.confirm).mockReturnValue(false)
    open('/customers'); await screen.findByRole('table')
    fireEvent.click(screen.getByRole('button', { name: 'Desactivar CUS-A' }))
    expect(writes(mock)).toHaveLength(0)
    expect(screen.getByRole('button', { name: 'Desactivar CUS-A' })).toBeEnabled()
  })
  it('crear inactivo envía active=false en un solo POST confirmado', async () => {
    const mock = mockApi(); open('/customers'); await screen.findByRole('table')
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' }))
    fireEvent.change(field('Código de cliente'), { target: { value: 'INACTIVE-MANUAL' } })
    fireEvent.change(field('Nombre'), { target: { value: 'Cliente inactivo' } })
    fireEvent.click(screen.getByLabelText('Activo', { exact: true }))
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await screen.findByText('Registro creado correctamente.')
    expect(writes(mock)).toHaveLength(1)
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ active: false })
    expect(window.confirm).toHaveBeenCalledTimes(1)
  })
  it.each([
    [409, 'Ya existe un cliente con ese código.', 'Ya existe un cliente con ese código.'],
    [422, [{ loc: ['body', 'name'], msg: 'Field required' }], 'Nombre: Campo obligatorio'],
    [404, 'Cliente no encontrado', 'Cliente no encontrado'],
    [500, { unexpected: true }, 'HTTP 500'],
  ])('muestra error %s comprensible y conserva formulario', async (status, detail, text) => {
    mockApi({ write: async () => jsonResponse({ detail }, status) }); open('/customers'); await screen.findByRole('table')
    fireEvent.click(screen.getByRole('button', { name: 'Editar CUS-A' }))
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(String(text))
    expect(screen.queryByText('[object Object]')).not.toBeInTheDocument()
    expect(field('Código de cliente')).toHaveValue('CUS-A')
    expect(screen.getByRole('button', { name: 'Guardar' })).toBeEnabled()
  })
  it('evita doble POST y deshabilita controles mientras crea', async () => {
    let finish: (response: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => { finish = resolve })
    const mock = mockApi({ write: () => pending }); open('/customers'); await screen.findByRole('table')
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' }))
    fireEvent.change(field('Código de cliente'), { target: { value: 'NEW' } }); fireEvent.change(field('Nombre'), { target: { value: 'Nuevo' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(screen.getByRole('button', { name: 'Creando...' })).toBeDisabled()
    expect(field('Nombre')).toBeDisabled()
    fireEvent.submit(screen.getByRole('form', { name: 'Crear cliente' }))
    expect(writes(mock)).toHaveLength(1)
    await act(async () => finish(jsonResponse({ ...customer, id: 3, customer_code: 'NEW', name: 'Nuevo' }, 201)))
    await screen.findByText('Registro creado correctamente.')
  })
  it('deshabilita Guardar durante PATCH', async () => {
    let finish: (response: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => { finish = resolve })
    const mock = mockApi({ write: () => pending }); open('/circuits'); await screen.findByRole('table')
    fireEvent.click(screen.getByRole('button', { name: 'Editar LINK-A' }))
    expect(field('Cliente')).toHaveValue('2')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(screen.getByRole('button', { name: 'Guardando...' })).toBeDisabled()
    fireEvent.submit(screen.getByRole('form', { name: 'Editar circuito' }))
    expect(writes(mock)).toHaveLength(1)
    await act(async () => finish(jsonResponse(circuit)))
    await screen.findByText('Cambios guardados correctamente.')
  })
  it.each(settings)('%s muestra estado vacío', async (_resource, path, _singular, title) => {
    mockApi({ empty: true }); open(path)
    if (['Departamentos', 'Tipos de incidencia', 'Nodos', 'Responsables'].includes(title)) fireEvent.click(screen.getByRole('button', { name: title }))
    expect(await screen.findByText(/^No hay .+ registrados\.$/)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
  it('muestra carga, fallo y recuperación del listado', async () => {
    const options = { fail: true }
    mockApi(options); open('/customers')
    expect(screen.getByText('Cargando clientes...')).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toHaveTextContent('No disponible')
    options.fail = false
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await screen.findByRole('table')
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument())
  })
  it('cancelar no guarda y buscar sin coincidencias informa', async () => {
    const mock = mockApi(); open('/customers'); await screen.findByRole('table')
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByRole('form')).not.toBeInTheDocument(); expect(writes(mock)).toHaveLength(0)
    fireEvent.change(screen.getByLabelText('Buscar clientes'), { target: { value: 'no-match' } })
    expect(screen.getByText('No hay coincidencias con la búsqueda.')).toBeInTheDocument()
  })
})

describe('Nodo en administración de Circuitos', () => {
  it('asigna y quita Nodo usando PATCH y permite NULL', async () => {
    const mock = mockApi(); open('/circuits'); await screen.findByRole('table')
    fireEvent.click(screen.getByRole('button', { name: 'Editar LINK-A' }))
    const selector = screen.getByRole('combobox', { name: 'Nodo de distribución' })
    fireEvent.click(selector); fireEvent.click(screen.getByRole('option', { name: 'Nombre inicial' }))
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await screen.findByText('Cambios guardados correctamente.')
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ node_id: 1 })
    fireEvent.click(screen.getByRole('button', { name: 'Editar LINK-A' }))
    expect(screen.getByRole('combobox', { name: 'Nodo de distribución' })).toHaveValue('Nombre inicial')
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar Nodo de distribución' }))
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await screen.findByText('Cambios guardados correctamente.')
    expect(JSON.parse(String(writes(mock)[1][1]?.body))).toMatchObject({ node_id: null })
  })
})

it('crea Nodo desde CircuitForm sin guardar Circuito ni perder sus datos', async () => {
  const show = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal')
  const close = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close')
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value(this: HTMLDialogElement) { this.setAttribute('open', '') } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value(this: HTMLDialogElement) { this.removeAttribute('open') } })
  try {
    const mock = mockApi(); open('/circuits'); await screen.findByRole('table')
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo circuito' }))
    fireEvent.change(field('Código de circuito'), { target: { value: 'MANUAL' } })
    fireEvent.change(field('Descripción'), { target: { value: 'Escrito antes del nodo' } })
    fireEvent.change(field('Cliente'), { target: { value: '1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo nodo' }))
    fireEvent.change(screen.getByLabelText(/^Nombre/), { target: { value: 'Nodo creado' } })
    const form = screen.getByRole('form', { name: 'Crear nodo rápido' })
    fireEvent.submit(form)
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(field('Código de circuito')).toHaveValue('MANUAL')
    expect(field('Descripción')).toHaveValue('Escrito antes del nodo')
    expect(field('Cliente')).toHaveValue('1')
    expect(screen.getByRole('combobox', { name: 'Nodo de distribución' })).toHaveValue('Nodo creado')
    expect(writes(mock)).toHaveLength(1)
    expect(writes(mock)[0][0]).toBe('/api/nodes')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await screen.findByText('Registro creado correctamente.')
    expect(JSON.parse(String(writes(mock)[1][1]?.body))).toMatchObject({ node_id: 3 })
  } finally {
    if (show) Object.defineProperty(HTMLDialogElement.prototype, 'showModal', show)
    else Reflect.deleteProperty(HTMLDialogElement.prototype, 'showModal')
    if (close) Object.defineProperty(HTMLDialogElement.prototype, 'close', close)
    else Reflect.deleteProperty(HTMLDialogElement.prototype, 'close')
  }
})
