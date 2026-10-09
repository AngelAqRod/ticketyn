import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { TicketEscalations } from './TicketEscalations'
import { TicketFollowUp } from './TicketFollowUp'
import { jsonResponse } from '../test/fixtures'
import type { Escalation } from '../types/escalation'
const person = { id: 1, name: 'Pedro', active: true, created_at: '2026-10-09T12:00:00Z' }
const recipient = { ...person, id: 2, name: 'Ángel', position: { ...person, name: 'N3' }, department: { ...person, name: 'NOC' } }
const reason = { ...person, id: 3, name: 'Apoyo técnico', description: null }
const escalation: Escalation = { id: 8, ticket_id: 1, requester_id: 1, recipient_id: 2, reason_id: 3, requester: person, recipient, reason, description: 'Ayuda BGP\nSin cambio de asignación', status: 'ACTIVE', created_at: person.created_at, finished_at: null, recipient_level: 'N3' }
const originalShow = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal'), originalClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close')
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value(this: HTMLDialogElement) { this.setAttribute('open', '') } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value(this: HTMLDialogElement) { this.removeAttribute('open') } })
})
afterAll(() => {
  if (originalShow) Object.defineProperty(HTMLDialogElement.prototype, 'showModal', originalShow); else Reflect.deleteProperty(HTMLDialogElement.prototype, 'showModal')
  if (originalClose) Object.defineProperty(HTMLDialogElement.prototype, 'close', originalClose); else Reflect.deleteProperty(HTMLDialogElement.prototype, 'close')
})
function mockApi(rows: Escalation[] = [], options: { failSave?: boolean; failFinish?: boolean; pending?: boolean; failLoad?: boolean } = {}) {
  const mock = vi.fn((url: string, init?: RequestInit) => {
    if (url.includes('/responsibles?')) return Promise.resolve(jsonResponse([person, recipient]))
    if (url.includes('/escalation-reasons?')) return Promise.resolve(jsonResponse([reason]))
    if (url.includes('/updates')) {
      if (init?.method === 'POST') return Promise.resolve(jsonResponse({ id: 9, ...JSON.parse(String(init.body)) }, 201))
      if (url.includes('escalation_id')) return Promise.resolve(jsonResponse([{ id: 1, content: 'Intervención relacionada', occurred_at: person.created_at, responsible: recipient, visibility: 'INTERNAL' }]))
      return Promise.resolve(jsonResponse({ items: [], next_cursor: null }))
    }
    if (url.endsWith('/finish')) return Promise.resolve(jsonResponse(options.failFinish ? { detail: 'No se pudo finalizar.' } : { ...escalation, status: 'FINISHED', finished_at: '2026-10-09T13:00:00Z' }, options.failFinish ? 409 : 200))
    if (init?.method === 'POST') {
      if (options.pending) return new Promise<Response>(() => {})
      if (options.failSave) return Promise.resolve(jsonResponse({ detail: 'No se pudo registrar.' }, 409))
      rows = [escalation]
      return Promise.resolve(jsonResponse(escalation, 201))
    }
    return Promise.resolve(jsonResponse(options.failLoad ? { detail: 'Historial no disponible.' } : rows, options.failLoad ? 503 : 200))
  })
  vi.stubGlobal('fetch', mock)
  return mock
}
async function select(name: string, option: string) {
  fireEvent.click(screen.getByRole('combobox', { name }))
  fireEvent.click(await screen.findByRole('option', { name: option }))
}
async function fill() {
  fireEvent.change(screen.getByLabelText(/Descripción de la solicitud/), { target: { value: 'Ayuda BGP' } })
  expect(screen.queryByRole('combobox', { name: 'Solicitante' })).not.toBeInTheDocument()
  await select('Destinatario', 'Ángel · N3 — NOC'); await select('Motivo', 'Apoyo técnico')
}
async function open() {
  render(<TicketEscalations ticketId={1} />)
  const button = screen.getByRole('button', { name: 'Nuevo escalamiento' }); button.focus(); fireEvent.click(button)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Registrar escalamiento' })).toBeEnabled())
  return button
}
describe('Escalamientos', () => {
  it('crea solicitud explícita sin PATCH del ticket y recarga historial', async () => {
    const mock = mockApi(); await open(); await fill()
    fireEvent.submit(screen.getByRole('form', { name: 'Registrar escalamiento' }))
    expect(await screen.findByText('Escalamiento registrado. La responsabilidad principal no cambia.')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(await screen.findByText('Pedro → Ángel · N3')).toBeInTheDocument()
    const write = mock.mock.calls.find(([, init]) => init?.method === 'POST')!
    expect(JSON.parse(String(write[1]?.body))).toEqual({ recipient_id: 2, reason_id: 3, description: 'Ayuda BGP' })
    expect(mock.mock.calls.some(([, init]) => init?.method === 'PATCH')).toBe(false)
  })
  it('mantiene contenido y modal ante error, y bloquea envíos duplicados', async () => {
    const mock = mockApi([], { pending: true }); await open(); await fill()
    const form = screen.getByRole('form', { name: 'Registrar escalamiento' })
    fireEvent.submit(form); fireEvent.submit(form)
    expect(mock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Registrando...' })).toBeDisabled()
  })
  it('conserva datos cuando falla registro', async () => {
    mockApi([], { failSave: true }); await open(); await fill()
    fireEvent.submit(screen.getByRole('form', { name: 'Registrar escalamiento' }))
    expect(await screen.findByText('No se pudo registrar.')).toBeInTheDocument()
    expect(screen.getByLabelText(/Descripción de la solicitud/)).toHaveValue('Ayuda BGP')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
  it('cancelación devuelve foco y no crea registros', async () => {
    const mock = mockApi(); const button = await open()
    expect(screen.getByLabelText(/Descripción de la solicitud/)).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(button).toHaveFocus(); expect(mock.mock.calls.some(([, init]) => init?.method === 'POST')).toBe(false)
  })
  it('finaliza y conserva historial e intervenciones relacionadas', async () => {
    mockApi([escalation]); render(<TicketEscalations ticketId={1} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Ver intervenciones' }))
    expect(await screen.findByText('Intervención relacionada')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Finalizar escalamiento' }))
    expect(await screen.findByText('Finalizado')).toBeInTheDocument()
    expect(screen.getByText('Pedro → Ángel · N3')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Finalizar escalamiento' })).not.toBeInTheDocument()
  })
  it('ofrece reintento ante error de carga', async () => {
    mockApi([], { failLoad: true }); render(<TicketEscalations ticketId={1} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Historial no disponible.')
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
  })
  it('permite vincular intervención sin duplicar contenido', async () => {
    const mock = mockApi([escalation]); render(<TicketFollowUp ticketId={1} />)
    fireEvent.click(screen.getByRole('button', { name: 'Nueva intervención' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Registrar actualización' })).toBeEnabled())
    fireEvent.change(screen.getByLabelText(/Descripción de la intervención/), { target: { value: 'Intervención única' } })
    await select('Escalamiento relacionado (opcional)', '#8 · Ángel · Apoyo técnico')
    fireEvent.submit(screen.getByRole('form', { name: 'Registrar actualización' }))
    await screen.findByText('Actualización registrada correctamente.')
    const write = mock.mock.calls.find(([url, init]) => url.includes('/updates') && init?.method === 'POST')!
    expect(JSON.parse(String(write[1]?.body))).toMatchObject({ escalation_id: 8, content: 'Intervención única', visibility: 'INTERNAL' })
  })
})

it('muestra snapshots históricos sin inventar solicitante ni usar el puesto actual', async () => {
  mockApi([{ ...escalation, requester_id: null, requester: null, recipient_level: null, recipient_position_name: 'Fusionador anterior', recipient_department_name: 'Red Externa' }])
  render(<TicketEscalations ticketId={1} />)
  expect(await screen.findByText('Ángel · Fusionador anterior — Red Externa')).toBeInTheDocument()
  expect(screen.queryByText(/Pedro →/)).not.toBeInTheDocument()
  expect(screen.queryByText(/N3/)).not.toBeInTheDocument()
})

it('permite destinatario sin puesto configurado', async () => {
  const mock = mockApi(); await open()
  fireEvent.change(screen.getByLabelText(/Descripción de la solicitud/), { target: { value: 'Solicitar colaboración' } })
  await select('Destinatario', 'Pedro'); await select('Motivo', 'Apoyo técnico')
  fireEvent.submit(screen.getByRole('form', { name: 'Registrar escalamiento' }))
  await screen.findByText('Escalamiento registrado. La responsabilidad principal no cambia.')
  const write = mock.mock.calls.find(([, init]) => init?.method === 'POST')!
  expect(JSON.parse(String(write[1]?.body))).toEqual({ recipient_id: 1, reason_id: 3, description: 'Solicitar colaboración' })
})
