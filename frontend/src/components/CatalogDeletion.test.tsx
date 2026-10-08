import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { CatalogAdmin } from './CatalogAdmin'
import { jsonResponse } from '../test/fixtures'

const created_at = '2026-01-01T12:00:00Z'
const customer = { id: 1, customer_code: 'CUS-ERROR', name: 'Cliente creado por error', active: true, created_at }
const circuit = { id: 1, customer_id: 1, circuit_code: 'CIR-ERROR', description: 'Circuito creado por error', active: true, created_at }
const cases = [['customers', 'CUS-ERROR', customer.name], ['circuits', 'CIR-ERROR', circuit.description]] as const
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

function setup(kind: 'customers' | 'circuits', remove: () => Promise<Response> = async () => new Response(null, { status: 204 })) {
  const mock = vi.fn((path: string, options?: RequestInit) => {
    if (options?.method === 'DELETE') return remove()
    if (path.startsWith('/api/customers')) return Promise.resolve(jsonResponse([customer]))
    if (path.startsWith('/api/circuits')) return Promise.resolve(jsonResponse([circuit]))
    return Promise.resolve(jsonResponse([]))
  })
  vi.stubGlobal('fetch', mock)
  render(<MemoryRouter initialEntries={[`/${kind}`]}><CatalogAdmin kind={kind} /></MemoryRouter>)
  return mock
}
const deletes = (mock: ReturnType<typeof setup>) => mock.mock.calls.filter(([, options]) => options?.method === 'DELETE')

describe('eliminación definitiva de clientes y circuitos', () => {
  it.each(cases)('%s confirma identidad, cancela y devuelve foco sin solicitudes', async (kind, code, description) => {
    const mock = setup(kind)
    const trigger = await screen.findByRole('button', { name: `Eliminar ${code}` })
    trigger.focus(); fireEvent.click(trigger)
    const modal = screen.getByRole('dialog')
    expect(within(modal).getByText(code)).toBeInTheDocument()
    expect(within(modal).getByText(description)).toBeInTheDocument()
    expect(within(modal).getByRole('button', { name: 'Cancelar' })).toHaveFocus()
    expect(deletes(mock)).toHaveLength(0)
    fireEvent.click(within(modal).getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
    expect(deletes(mock)).toHaveLength(0)
  })
  it.each(cases)('%s elimina con DELETE/204 y actualiza listado', async (kind, code) => {
    const response = new Response(null, { status: 204 })
    const json = vi.spyOn(response, 'json')
    const mock = setup(kind, async () => response)
    fireEvent.click(await screen.findByRole('button', { name: `Eliminar ${code}` }))
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar definitivamente' }))
    expect((await screen.findByText('Registro eliminado correctamente.')).closest('[role="status"]')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByText(code)).not.toBeInTheDocument()
    expect(deletes(mock)).toHaveLength(1)
    expect(deletes(mock)[0][0]).toBe(`/api/${kind}/1`)
    expect(json).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: /Nuevo/ })).toBeEnabled()
    expect(screen.getByRole('button', { name: /Nuevo/ })).toHaveFocus()
  })
  it.each([409, 404, 500])('error HTTP %s conserva registro/modal y permite reintento', async (status) => {
    const mock = setup('customers', async () => jsonResponse({ detail: status === 409 ? 'Tiene circuitos asociados.' : 'No se pudo eliminar.' }, status))
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar CUS-ERROR' }))
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar definitivamente' }))
    const alert = await screen.findByRole('alert')
    if (status === 409) expect(alert).toHaveTextContent('Puedes desactivar el registro')
    else expect(alert).toHaveTextContent('No se pudo eliminar.')
    expect(within(screen.getByRole('table')).getByText('CUS-ERROR')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Eliminar definitivamente' })).toBeEnabled()
    expect(deletes(mock)).toHaveLength(1)
  })
  it('fallo de conexión conserva el registro y muestra error recuperable', async () => {
    setup('circuits', async () => { throw new TypeError('Network failure') })
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar CIR-ERROR' }))
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar definitivamente' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo conectar')
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
  it('evita solicitudes duplicadas y bloquea cancelación/Escape mientras elimina', async () => {
    let finish!: (response: Response) => void
    const mock = setup('customers', () => new Promise((resolve) => { finish = resolve }))
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar CUS-ERROR' }))
    const confirm = screen.getByRole('button', { name: 'Eliminar definitivamente' })
    fireEvent.click(confirm); fireEvent.click(confirm)
    expect(screen.getByRole('button', { name: 'Eliminando...' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeDisabled()
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { cancelable: true }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(deletes(mock)).toHaveLength(1)
    await act(async () => finish(new Response(null, { status: 204 })))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Nuevo cliente' })).toBeEnabled()
  })
  it('Escape antes de confirmar cancela sin enviar DELETE', async () => {
    const mock = setup('customers')
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar CUS-ERROR' }))
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { cancelable: true }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(deletes(mock)).toHaveLength(0)
  })
})
