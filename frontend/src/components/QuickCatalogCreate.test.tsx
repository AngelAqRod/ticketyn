import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import App from '../App'
import { jsonResponse, ticket } from '../test/fixtures'

const customer = { id: 1, customer_code: 'OLD', name: 'Cliente actual', active: true, created_at: ticket.created_at }
const circuit = { id: 1, customer_id: 1, circuit_code: 'OLD.01', description: 'Circuito actual', active: true, created_at: ticket.created_at }
const createdCustomer = { ...customer, id: 9, customer_code: 'NEW', name: 'Nuevo cliente' }
const createdCircuit = { ...circuit, id: 10, circuit_code: 'MANUAL.02', description: 'Nuevo enlace' }
const named = { id: 1, name: 'Clasificación existente', active: true, created_at: ticket.created_at }

// jsdom no implementa el ciclo nativo de dialog. Simulamos solo abrir/cerrar;
// la lógica React de foco, validación, POST y cancelación se ejecuta realmente.
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
function mockApi(write?: (path: string, init: RequestInit) => Promise<Response>) {
  const mock = vi.fn((path: string, init?: RequestInit): Promise<Response> => {
    if (init?.method === 'POST' || init?.method === 'PATCH') {
      if (write) return write(path, init)
      return Promise.resolve(jsonResponse(path === '/api/customers' ? createdCustomer : path === '/api/circuits' ? { ...createdCircuit, customer_id: Number(JSON.parse(String(init.body)).customer_id) } : ticket, 201))
    }
    if (path === '/health') return Promise.resolve(jsonResponse({ status: 'ok' }))
    if (path === '/api/tickets/1') return Promise.resolve(jsonResponse(ticket))
    if (path === '/api/customers/1') return Promise.resolve(jsonResponse(customer))
    if (path === '/api/circuits/1') return Promise.resolve(jsonResponse(circuit))
    if (path.startsWith('/api/customers')) return Promise.resolve(jsonResponse([customer]))
    if (path.startsWith('/api/circuits')) return Promise.resolve(jsonResponse(path.includes('customer_id=1') ? [circuit] : []))
    if (/^\/api\/(sectors|departments|incident-types|nodes|responsibles)\/1$/.test(path)) return Promise.resolve(jsonResponse(named))
    if (/^\/api\/(sectors|departments|incident-types|nodes|responsibles)/.test(path)) return Promise.resolve(jsonResponse([named]))
    return Promise.resolve(jsonResponse([ticket]))
  })
  vi.stubGlobal('fetch', mock)
  return mock
}
function open(edit = false) { render(<MemoryRouter initialEntries={[edit ? '/tickets/1/edit' : '/tickets/new']}><App /></MemoryRouter>) }
async function ready(edit = false) { await waitFor(() => expect(screen.getByRole('button', { name: edit ? 'Guardar cambios' : 'Guardar' })).toBeEnabled()) }
const combo = (label: string) => screen.getByRole('combobox', { name: new RegExp(`^${label}`) })
async function selectExisting() {
  fireEvent.click(combo('Cliente')); fireEvent.click(screen.getByRole('option', { name: 'OLD — Cliente actual' }))
  await waitFor(() => expect(combo('Circuito')).toBeEnabled())
  fireEvent.click(combo('Circuito')); fireEvent.click(screen.getByRole('option', { name: 'OLD.01 — Circuito actual' }))
}
function setTicketValues() {
  fireEvent.change(screen.getByLabelText(/^Título/), { target: { value: 'Título escrito' } })
  fireEvent.change(screen.getByLabelText(/^Descripción/), { target: { value: 'Descripción escrita' } })
  for (const label of ['Sector', 'Departamento', 'Tipo de incidencia']) fireEvent.change(combo(label), { target: { value: '1' } })
  fireEvent.change(screen.getByLabelText(/^Inicio\s*\*?$/), { target: { value: '2026-01-01T10:00' } })
  fireEvent.change(screen.getByLabelText('Fin'), { target: { value: '2026-01-01T11:00' } })
  fireEvent.change(combo('Estado'), { target: { value: 'CLOSED' } })
}
function expectPreserved() {
  const form = within(screen.getByRole('form', { name: /^(Crear|Editar) ticket$/ }))
  expect(form.getByLabelText(/^Título/)).toHaveValue('Título escrito')
  expect(form.getByLabelText(/^Descripción/)).toHaveValue('Descripción escrita')
  for (const label of ['Sector', 'Departamento', 'Tipo de incidencia']) expect(combo(label)).toHaveValue('1')
  expect(form.getByLabelText(/^Inicio\s*\*?$/)).toHaveValue('2026-01-01T10:00')
  expect(form.getByLabelText('Fin')).toHaveValue('2026-01-01T11:00')
  expect(combo('Estado')).toHaveValue('CLOSED')
}
function fillQuick(kind: 'cliente' | 'circuito') {
  const modal = within(screen.getByRole('dialog'))
  fireEvent.change(modal.getByLabelText(new RegExp(`^Código de ${kind}`)), { target: { value: kind === 'cliente' ? 'NEW' : 'MANUAL.02' } })
  fireEvent.change(modal.getByLabelText(kind === 'cliente' ? /^Nombre/ : /^Descripción/), { target: { value: kind === 'cliente' ? 'Nuevo cliente' : 'Nuevo enlace' } })
  return modal
}
const writes = (mock: ReturnType<typeof mockApi>) => mock.mock.calls.filter(([, init]) => init?.method === 'POST' || init?.method === 'PATCH')

describe('creación contextual de catálogos en TicketForm', () => {
  it('botones + son secundarios, type=button, con title y Circuito depende de Cliente', async () => {
    const mock = mockApi(); open(); await ready()
    for (const name of ['Nuevo cliente', 'Nuevo circuito']) {
      const button = screen.getByRole('button', { name })
      expect(button).toHaveAttribute('type', 'button'); expect(button).toHaveAttribute('title', name); expect(button).toHaveTextContent('+')
    }
    expect(screen.getByRole('button', { name: 'Nuevo circuito' })).toBeDisabled()
    await selectExisting()
    expect(screen.getByRole('button', { name: 'Nuevo circuito' })).toBeEnabled()
    expect(writes(mock)).toHaveLength(0)
  })
  it.each(['cliente', 'circuito'] as const)('cancelar %s conserva todos los datos del ticket y retorna el foco', async (kind) => {
    const mock = mockApi(); open(); await ready(); await selectExisting(); setTicketValues()
    const trigger = screen.getByRole('button', { name: `Nuevo ${kind}` })
    trigger.focus(); fireEvent.click(trigger)
    const modal = within(screen.getByRole('dialog', { name: `Nuevo ${kind}` }))
    expect(modal.getByLabelText(new RegExp(`^Código de ${kind}`))).toHaveFocus()
    fireEvent.click(modal.getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus(); expectPreserved()
    expect(combo('Cliente')).toHaveValue('OLD — Cliente actual'); expect(combo('Circuito')).toHaveValue('OLD.01 — Circuito actual')
    expect(writes(mock)).toHaveLength(0)
  })
  it('cancelación nativa de Escape cierra sin enviar ni resetear', async () => {
    const mock = mockApi(); open(); await ready(); setTicketValues()
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' }))
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { bubbles: false, cancelable: true }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument(); expectPreserved(); expect(writes(mock)).toHaveLength(0)
  })
  it('crea cliente activo, lo selecciona, limpia Circuito y preserva el ticket', async () => {
    const mock = mockApi(); open(); await ready(); await selectExisting(); setTicketValues()
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' })); const modal = fillQuick('cliente')
    fireEvent.click(modal.getByRole('button', { name: 'Guardar' }))
    await screen.findByText('Cliente NEW creado y seleccionado.')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument(); expectPreserved()
    expect(combo('Cliente')).toHaveValue('NEW — Nuevo cliente'); expect(combo('Circuito')).toHaveValue('')
    expect(writes(mock)).toHaveLength(1)
    expect(writes(mock)[0][0]).toBe('/api/customers')
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).toEqual({ customer_code: 'NEW', name: 'Nuevo cliente', active: true })
    fireEvent.click(combo('Cliente')); expect(screen.getByRole('option', { name: 'NEW — Nuevo cliente' })).toBeInTheDocument()
    fireEvent.keyDown(combo('Cliente'), { key: 'Escape' })
    await waitFor(() => expect(combo('Circuito')).toBeEnabled())
    expect(mock).toHaveBeenCalledWith('/api/circuits?customer_id=9&include_inactive=false&limit=200&offset=0', expect.any(Object))
  })
  it('crea circuito activo con customer_id contextual, lo selecciona y conserva Cliente', async () => {
    const mock = mockApi(); open(); await ready(); await selectExisting(); setTicketValues()
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo circuito' }))
    expect(within(screen.getByRole('dialog')).getByText('OLD — Cliente actual', { exact: false })).toBeInTheDocument()
    expect(within(screen.getByRole('dialog')).getByRole('combobox', { name: 'Nodo de distribución' })).toBeInTheDocument()
    const modal = fillQuick('circuito'); fireEvent.click(modal.getByRole('button', { name: 'Guardar' }))
    await screen.findByText('Circuito MANUAL.02 creado y seleccionado.')
    expectPreserved(); expect(combo('Cliente')).toHaveValue('OLD — Cliente actual'); expect(combo('Circuito')).toHaveValue('MANUAL.02 — Nuevo enlace')
    expect(writes(mock)).toHaveLength(1); expect(writes(mock)[0][0]).toBe('/api/circuits')
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).toEqual({ customer_id: 1, circuit_code: 'MANUAL.02', description: 'Nuevo enlace', active: true, node_id: null })
    fireEvent.click(combo('Circuito')); expect(screen.getByRole('option', { name: 'MANUAL.02 — Nuevo enlace' })).toBeInTheDocument()
  })
  it.each(['cliente', 'circuito'] as const)('409 de %s mantiene diálogo y valores, permitiendo corregir', async (kind) => {
    const mock = mockApi(async () => jsonResponse({ detail: `Código de ${kind} duplicado` }, 409))
    open(); await ready(); await selectExisting()
    fireEvent.click(screen.getByRole('button', { name: `Nuevo ${kind}` })); const modal = fillQuick(kind)
    fireEvent.click(modal.getByRole('button', { name: 'Guardar' }))
    expect(await modal.findByRole('alert')).toHaveTextContent(`Código de ${kind} duplicado`)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(modal.getByLabelText(new RegExp(`^Código de ${kind}`))).toHaveValue(kind === 'cliente' ? 'NEW' : 'MANUAL.02')
    expect(modal.getByRole('button', { name: 'Guardar' })).toBeEnabled()
    expect(combo('Cliente')).toHaveValue('OLD — Cliente actual'); expect(writes(mock)).toHaveLength(1)
  })
  it.each(['cliente', 'circuito'] as const)('evita doble POST de %s y no marca el ticket como enviándose', async (kind) => {
    let finish: (response: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => { finish = resolve })
    const mock = mockApi(() => pending); open(); await ready(); await selectExisting()
    fireEvent.click(screen.getByRole('button', { name: `Nuevo ${kind}` })); const modal = fillQuick(kind)
    fireEvent.click(modal.getByRole('button', { name: 'Guardar' }))
    expect(modal.getByRole('button', { name: 'Creando...' })).toBeDisabled()
    expect(screen.getByRole('form', { name: 'Crear ticket' })).toHaveAttribute('aria-busy', 'false')
    expect(screen.getByRole('button', { name: 'Guardar' })).toBeEnabled()
    fireEvent.submit(modal.getByRole('form'))
    expect(writes(mock)).toHaveLength(1)
    await act(async () => finish(jsonResponse(kind === 'cliente' ? createdCustomer : createdCircuit, 201)))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })
  it.each(['cliente', 'circuito'] as const)('creación de %s también funciona en edición sin PATCH automático', async (kind) => {
    const mock = mockApi(); open(true); await ready(true); setTicketValues()
    fireEvent.click(screen.getByRole('button', { name: `Nuevo ${kind}` })); const modal = fillQuick(kind)
    fireEvent.click(modal.getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expectPreserved(); expect(screen.getByRole('heading', { name: `Editar ${ticket.reference}` })).toBeInTheDocument()
    expect(combo('Cliente')).toHaveValue(kind === 'cliente' ? 'NEW — Nuevo cliente' : 'OLD — Cliente actual')
    expect(combo('Circuito')).toHaveValue(kind === 'cliente' ? '' : 'MANUAL.02 — Nuevo enlace')
    expect(writes(mock)).toHaveLength(1); expect(writes(mock)[0][1]?.method).toBe('POST')
  })
  it.each([false, true])('tras crear ambos catálogos, el ticket se guarda únicamente al pedirlo (edición=%s)', async (edit) => {
    const mock = mockApi(); open(edit); await ready(edit); setTicketValues()
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' }))
    fireEvent.click(fillQuick('cliente').getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await waitFor(() => expect(screen.getByRole('button', { name: 'Nuevo circuito' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo circuito' }))
    expect(within(screen.getByRole('dialog')).getByText('NEW — Nuevo cliente', { exact: false })).toBeInTheDocument()
    fireEvent.click(fillQuick('circuito').getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expectPreserved()
    expect(writes(mock)).toHaveLength(2)
    expect(JSON.parse(String(writes(mock)[1][1]?.body))).toMatchObject({ customer_id: 9, active: true })
    expect(combo('Cliente')).toHaveValue('NEW — Nuevo cliente'); expect(combo('Circuito')).toHaveValue('MANUAL.02 — Nuevo enlace')
    fireEvent.click(screen.getByRole('button', { name: edit ? 'Guardar cambios' : 'Guardar' }))
    await waitFor(() => expect(writes(mock)).toHaveLength(3))
    const write = writes(mock)[2]
    expect(write[0]).toBe(edit ? '/api/tickets/1' : '/api/tickets')
    expect(write[1]?.method).toBe(edit ? 'PATCH' : 'POST')
    expect(JSON.parse(String(write[1]?.body))).toMatchObject({ customer_id: 9, circuit_id: 10, title: 'Título escrito', description: 'Descripción escrita', sector_id: 1, department_id: 1, incident_type_id: 1, status: 'CLOSED' })
    await screen.findByText(edit ? 'Cambios guardados correctamente.' : `Ticket ${ticket.reference} creado correctamente.`)
  })
  it.each([[422, [{ loc: ['body', 'customer_code'], msg: 'Field required' }], 'Código de cliente: Campo obligatorio'], [500, {}, 'HTTP 500']])('normaliza error %s sin cerrar ni mostrar objetos', async (status, detail, expected) => {
    mockApi(async () => jsonResponse({ detail }, Number(status))); open(); await ready()
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo cliente' })); const modal = fillQuick('cliente')
    fireEvent.click(modal.getByRole('button', { name: 'Guardar' }))
    expect(await modal.findByRole('alert')).toHaveTextContent(String(expected))
    expect(modal.getByRole('form')).toHaveAttribute('aria-describedby', modal.getByRole('alert').id)
    if (status === 422) {
      expect(modal.getByLabelText(/^Código de cliente/)).toHaveAttribute('aria-invalid', 'true')
      expect(modal.getByLabelText(/^Código de cliente/)).toHaveAccessibleDescription(String(expected))
    }
    expect(screen.getByRole('dialog')).toBeInTheDocument(); expect(screen.queryByText('[object Object]')).not.toBeInTheDocument()
  })
})


describe('Nodo y Responsable en el flujo contextual', () => {
  it('asocia errores del Nodo anidado sin marcar inválido el Circuito', async () => {
    const mock = mockApi(); open(); await ready(); await selectExisting()
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo circuito' }))
    const parent = within(screen.getByRole('dialog', { name: 'Nuevo circuito' }))
    fireEvent.click(parent.getByRole('button', { name: 'Nuevo nodo' }))
    const child = within(screen.getByRole('dialog', { name: 'Nuevo nodo' }))
    fireEvent.click(child.getByRole('button', { name: 'Guardar' }))
    const error = child.getByRole('alert')
    expect(child.getByLabelText(/^Nombre/)).toHaveAttribute('aria-invalid', 'true')
    expect(child.getByLabelText(/^Nombre/)).toHaveAttribute('aria-describedby', error.id)
    expect(parent.getByLabelText(/^Código de circuito/)).not.toHaveAttribute('aria-invalid')
    expect(parent.getByRole('form')).not.toHaveAttribute('aria-describedby')
    expect(writes(mock)).toHaveLength(0)
  })
  it.each([false, true])('crea Nodo y Circuito anidados preservando todo el ticket (edición=%s)', async (edit) => {
    const node = { ...named, id: 20, name: 'Nodo nuevo' }
    const mock = mockApi(async (path, init) => {
      if (path === '/api/nodes') return jsonResponse(node, 201)
      if (path === '/api/circuits') return jsonResponse({ ...createdCircuit, node_id: node.id, node }, 201)
      return jsonResponse({ ...ticket, ...JSON.parse(String(init.body)) })
    })
    open(edit); await ready(edit)
    if (!edit) await selectExisting()
    setTicketValues()
    fireEvent.click(combo('Responsable')); fireEvent.click(within(screen.getByRole('listbox', { name: 'Responsable' })).getByRole('option', { name: named.name }))
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo circuito' }))
    const circuitDialog = screen.getByRole('dialog', { name: 'Nuevo circuito' })
    const circuitForm = fillQuick('circuito')
    fireEvent.click(circuitForm.getByRole('button', { name: 'Nuevo nodo' }))
    const nodeDialog = within(screen.getByRole('dialog', { name: 'Nuevo nodo' }))
    expect(nodeDialog.getByLabelText(/^Nombre/)).toHaveFocus()
    fireEvent.change(nodeDialog.getByLabelText(/^Nombre/), { target: { value: 'Nodo nuevo' } })
    fireEvent.click(nodeDialog.getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Nuevo nodo' })).not.toBeInTheDocument())
    expect(circuitDialog).toBeInTheDocument()
    expect(circuitForm.getByLabelText(/^Código de circuito/)).toHaveValue('MANUAL.02')
    expect(circuitForm.getByLabelText(/^Descripción/)).toHaveValue('Nuevo enlace')
    expect(circuitForm.getByRole('combobox', { name: 'Nodo de distribución' })).toHaveValue('Nodo nuevo')
    expectPreserved(); expect(combo('Responsable')).toHaveValue(named.name)
    expect(writes(mock)).toHaveLength(1)
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).toEqual({ name: 'Nodo nuevo', active: true })
    fireEvent.click(circuitForm.getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expectPreserved(); expect(combo('Responsable')).toHaveValue(named.name)
    expect(combo('Circuito')).toHaveValue('MANUAL.02 — Nuevo enlace')
    expect(screen.getByText('Nodo nuevo')).toBeInTheDocument()
    expect(JSON.parse(String(writes(mock)[1][1]?.body))).toMatchObject({ customer_id: 1, node_id: 20 })
    expect(writes(mock).some(([path]) => path.startsWith('/api/tickets'))).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: edit ? 'Guardar cambios' : 'Guardar' }))
    await waitFor(() => expect(writes(mock)).toHaveLength(3))
    expect(JSON.parse(String(writes(mock)[2][1]?.body))).toMatchObject({ responsible_id: 1, circuit_id: 10 })
  })
  it('selecciona Nodo existente sin guardar automáticamente Ticket', async () => {
    const mock = mockApi(); open(); await ready(); await selectExisting()
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo circuito' }))
    const form = fillQuick('circuito'), node = form.getByRole('combobox', { name: 'Nodo de distribución' })
    await waitFor(() => expect(node).toBeEnabled())
    fireEvent.click(node); fireEvent.click(within(screen.getByRole('listbox', { name: 'Nodo de distribución' })).getByRole('option', { name: named.name }))
    fireEvent.click(form.getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ node_id: 1 })
    expect(writes(mock)).toHaveLength(1)
  })
  it('Escape del Nodo vuelve al Circuito sin perder valores', async () => {
    const mock = mockApi(); open(); await ready(); await selectExisting(); setTicketValues()
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo circuito' }))
    const parent = fillQuick('circuito')
    fireEvent.click(parent.getByRole('button', { name: 'Nuevo nodo' }))
    fireEvent(screen.getByRole('dialog', { name: 'Nuevo nodo' }), new Event('cancel', { bubbles: true, cancelable: true }))
    expect(screen.queryByRole('dialog', { name: 'Nuevo nodo' })).not.toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: 'Nuevo circuito' })).toBeInTheDocument()
    expect(parent.getByLabelText(/^Código de circuito/)).toHaveValue('MANUAL.02')
    expectPreserved(); expect(writes(mock)).toHaveLength(0)
  })
  it('409 al crear Nodo conserva ambos formularios y sus valores', async () => {
    const mock = mockApi(async () => jsonResponse({ detail: 'El nodo ya existe' }, 409))
    open(); await ready(); await selectExisting(); setTicketValues()
    fireEvent.click(screen.getByRole('button', { name: 'Nuevo circuito' })); const parent = fillQuick('circuito')
    fireEvent.click(parent.getByRole('button', { name: 'Nuevo nodo' }))
    const child = within(screen.getByRole('dialog', { name: 'Nuevo nodo' }))
    fireEvent.change(child.getByLabelText(/^Nombre/), { target: { value: 'Duplicado' } })
    fireEvent.click(child.getByRole('button', { name: 'Guardar' }))
    expect(await child.findByRole('alert')).toHaveTextContent('El nodo ya existe')
    expect(child.getByLabelText(/^Nombre/)).toHaveValue('Duplicado')
    expect(parent.getByLabelText(/^Código de circuito/)).toHaveValue('MANUAL.02')
    expectPreserved(); expect(writes(mock)).toHaveLength(1)
  })
  it('Responsable es opcional, seleccionable y puede desasignarse', async () => {
    const mock = mockApi(); open(); await ready(); await selectExisting(); setTicketValues()
    fireEvent.click(combo('Responsable')); fireEvent.click(within(screen.getByRole('listbox', { name: 'Responsable' })).getByRole('option', { name: named.name }))
    expect(combo('Responsable')).toHaveValue(named.name)
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar Responsable' }))
    expect(combo('Responsable')).toHaveValue('')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await waitFor(() => expect(writes(mock)).toHaveLength(1))
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ responsible_id: null })
  })
  it('Responsable histórico inactivo sigue visible en edición', async () => {
    const mock = mockApi(), original = mock.getMockImplementation()!
    const historical = { ...named, id: 2, name: 'Asignado histórico', active: false }
    mock.mockImplementation((path, init) => path === '/api/tickets/1' ? Promise.resolve(jsonResponse({ ...ticket, responsible_id: 2 })) : path === '/api/responsibles/2' ? Promise.resolve(jsonResponse(historical)) : original(path, init))
    open(true); await ready(true)
    expect(combo('Responsable')).toHaveValue('Asignado histórico')
    fireEvent.click(combo('Responsable'))
    expect(screen.getByRole('option', { name: /Asignado histórico/ })).toHaveAttribute('aria-disabled', 'true')
  })
})
