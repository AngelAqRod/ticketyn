import { fireEvent, render, screen, waitFor, within } from '../test/render'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { OperationModal } from '../components/OperationModal'
import { ActivationDetail } from './ActivationDetail'
import { jsonResponse } from '../test/fixtures'
import type { FmsKind } from '../types/fms'

const created_at = '2020-01-01T12:00:00Z'
const person = { id: 1, name: 'Operador', active: true, created_at }
const customer = { ...person, customer_code: 'C-1', name: 'Cliente' }
const circuit = { id: 1, customer_id: 1, circuit_code: 'CIR-1', description: 'Servicio', active: true, created_at, node_id: 1, sector_id: 1 }
const activation = { id: 42, circuit_id: 1, circuit, responsible_id: 1, responsible: person, effective_at: created_at, created_at, reference: 'ACT-000042' }
const oldShow = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal')
const oldClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close')
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
function setup(notes: string | null = null) {
  const mock = vi.fn((path: string, init?: RequestInit): Promise<Response> => {
    if (init?.method === 'POST' || init?.method === 'PATCH') {
      return Promise.resolve(jsonResponse({ ...activation, ...JSON.parse(String(init.body)) }, init.method === 'POST' ? 201 : 200))
    }
    if (path === '/api/activations/42') return Promise.resolve(jsonResponse({ ...activation, activation_notes: notes }))
    if (path === '/api/activations/42/notification') return Promise.resolve(jsonResponse({ activation_id: 42, mode: 'DISABLED', state: null, revision: 0, processor_paused: false, can_request: false }))
    if (path.includes('/interventions')) return Promise.resolve(jsonResponse([{ id: 1, responsible: person, occurred_at: created_at, content: 'Intervención original' }]))
    if (path.includes('/operational-detail')) return Promise.resolve(jsonResponse({ circuit, customer, current_capacity: null, current_capacity_unit: null, initial_activation: activation }))
    if (path.startsWith('/api/customers/1')) return Promise.resolve(jsonResponse(customer))
    if (path.startsWith('/api/customers?')) return Promise.resolve(jsonResponse([customer]))
    if (path.startsWith('/api/circuits?')) return Promise.resolve(jsonResponse([circuit]))
    return Promise.resolve(jsonResponse([person]))
  })
  vi.stubGlobal('fetch', mock)
  return mock
}
const writes = (mock: ReturnType<typeof setup>) => mock.mock.calls.filter(([, init]) => init?.method === 'POST' || init?.method === 'PATCH')
function detail() {
  render(<MemoryRouter initialEntries={['/activations/42']}><Routes><Route path="/activations/:id" element={<ActivationDetail />} /></Routes></MemoryRouter>)
}
async function creation(kind: FmsKind = 'activations', saved = vi.fn()) {
  render(<MemoryRouter><OperationModal kind={kind} circuit={circuit} onCancel={vi.fn()} onSaved={saved} /></MemoryRouter>)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Registrar' })).toBeEnabled())
  fireEvent.click(screen.getByRole('combobox', { name: 'Responsable' }))
  fireEvent.click(await screen.findByRole('option', { name: 'Operador' }))
}

describe('Notas de activación', () => {
  it.each(['', '   ', '  IP pública\nNAT configurado  ', 'x'.repeat(10000)])('guarda notas opcionales en creación (caso %#)', async (notes) => {
    const mock = setup(), saved = vi.fn()
    await creation('activations', saved)
    const input = screen.getByRole('textbox', { name: 'Notas de activación' })
    expect(input).not.toBeRequired(); expect(input).toHaveAttribute('maxlength', '10000')
    fireEvent.change(input, { target: { value: notes } })
    fireEvent.click(screen.getByRole('button', { name: 'Registrar' }))
    await waitFor(() => expect(saved).toHaveBeenCalledOnce())
    expect(writes(mock)).toHaveLength(1)
    expect(writes(mock)[0][0]).toBe('/api/activations')
    expect(JSON.parse(String(writes(mock)[0][1]?.body)).activation_notes).toBe(notes.trim() ? notes : null)
  })
  it('rechaza notas demasiado largas al crear, conservando el texto', async () => {
    const mock = setup(); await creation()
    fireEvent.change(screen.getByRole('textbox', { name: 'Notas de activación' }), { target: { value: 'x'.repeat(10001) } })
    fireEvent.submit(screen.getByRole('form', { name: 'Registrar operación' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('10.000 caracteres')
    expect(writes(mock)).toHaveLength(0)
  })
  it.each(['capacity-changes', 'circuit-lifecycle'] as const)('no muestra notas en %s', async (kind) => {
    setup(); await creation(kind)
    expect(screen.queryByRole('textbox', { name: 'Notas de activación' })).not.toBeInTheDocument()
  })
  it('muestra las notas históricas solo en lectura, conservando espacios y saltos', async () => {
    const notes = '  IP pública\nNAT configurado  ', mock = setup(notes); detail()
    const panel = await screen.findByRole('region', { name: 'Notas de activación' })
    expect(within(panel).getByText(notes, { normalizer: value => value })).toHaveClass('whitespace-pre-wrap')
    expect(within(panel).queryByRole('textbox')).not.toBeInTheDocument()
    expect(within(panel).queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Editar notas de activación' })).not.toBeInTheDocument()
    expect(writes(mock)).toHaveLength(0)
    expect(screen.getByText('Intervención original')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Nueva intervención' }))
    expect(await screen.findByRole('form', { name: 'Registrar intervención de activación' })).toBeInTheDocument()
    expect(within(panel).getByText(notes, { normalizer: value => value })).toBeInTheDocument()
    expect(writes(mock)).toHaveLength(0)
  })
  it('muestra un estado vacío discreto sin controles de edición', async () => {
    const mock = setup(); detail()
    const panel = await screen.findByRole('region', { name: 'Notas de activación' })
    expect(within(panel).getByText('Sin notas de activación.')).toBeInTheDocument()
    expect(within(panel).queryByRole('button')).not.toBeInTheDocument()
    expect(within(panel).queryByRole('textbox')).not.toBeInTheDocument()
    expect(writes(mock)).toHaveLength(0)
  })
})
