import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest'
import { PermissionProvider } from '../auth/permissions'
import { TicketQuickClose } from './TicketQuickClose'
import { jsonResponse } from '../test/fixtures'

const show = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal')
const close = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close')
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value(this: HTMLDialogElement) { this.setAttribute('open', '') } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value(this: HTMLDialogElement) { this.removeAttribute('open') } })
})
afterAll(() => {
  for (const [name, descriptor] of [['showModal', show], ['close', close]] as const) {
    if (descriptor) Object.defineProperty(HTMLDialogElement.prototype, name, descriptor)
    else Reflect.deleteProperty(HTMLDialogElement.prototype, name)
  }
})
const ticket = { id: 4, reference: 'TEST-4', start_at: '2020-01-01T12:00:00Z', updated_at: '2026-10-25T15:00:00.123456Z',
  status: 'OPEN', resolution: 'Diagnóstico previo', customer_resolution: 'Texto autorizado' }
function setup(internal = false, extra: Partial<typeof ticket> = {}, permissions?: string[], pending = false) {
  const fetcher = vi.fn((_url: string, _options?: RequestInit): Promise<Response> => pending ? new Promise(() => {}) : Promise.resolve(jsonResponse({ ...ticket, ...extra, status: 'CLOSED' })))
  vi.stubGlobal('fetch', fetcher)
  const onClosed = vi.fn()
  const props = { ticket: { ...ticket, ...extra }, internal, onClosed }
  const ui = <TicketQuickClose {...props} />
  const rendered = render(ui, { wrapper: ({ children }) => <PermissionProvider permissions={permissions ?? ['tickets.close', 'tickets.edit', 'internal_tickets.close']}>{children}</PermissionProvider> })
  return { fetcher, onClosed, ...rendered }
}
function open() { fireEvent.click(screen.getByRole('button', { name: 'Cerrar ticket' })); return screen.getByRole('dialog') }
function submit() { fireEvent.submit(screen.getByRole('form', { name: 'Cierre rápido de ticket' })) }

for (const internal of [false, true]) describe(internal ? 'Cierre interno' : 'Cierre de cliente', () => {
  it('precarga resoluciones y confirma ahora sin reenviar contenido intacto', async () => {
    const { fetcher, onClosed } = setup(internal)
    const dialog = open()
    expect(dialog).toHaveAccessibleName(internal ? 'Cerrar ticket interno' : 'Cerrar ticket de cliente')
    expect(screen.getByRole('radio', { name: 'Cerrar ahora' })).toBeChecked()
    expect(screen.getByLabelText('Resolución interna — Opcional')).toHaveValue(ticket.resolution)
    if (internal) expect(screen.queryByLabelText('Resolución para el cliente — Opcional')).not.toBeInTheDocument()
    else expect(screen.getByLabelText('Resolución para el cliente — Opcional')).toHaveValue(ticket.customer_resolution)
    submit()
    await waitFor(() => expect(onClosed).toHaveBeenCalledOnce())
    expect(fetcher.mock.calls[0][0]).toBe(`/api/${internal ? 'internal-tickets' : 'tickets'}/4/close`)
    expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body))).toEqual({ expected_updated_at: ticket.updated_at, end_at: null })
  })
  it('permite cerrar sin ninguna resolución', async () => {
    const { fetcher, onClosed } = setup(internal, { resolution: '', customer_resolution: '' })
    open(); submit()
    await waitFor(() => expect(onClosed).toHaveBeenCalled())
    expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body))).not.toHaveProperty('resolution')
  })
  it('envía ediciones voluntarias y null cuando se borra un contenido', async () => {
    const { fetcher, onClosed } = setup(internal)
    open(); fireEvent.change(screen.getByLabelText('Resolución interna — Opcional'), { target: { value: '' } })
    if (!internal) fireEvent.change(screen.getByLabelText('Resolución para el cliente — Opcional'), { target: { value: 'Restablecido\n<estable> & verificado' } })
    submit(); await waitFor(() => expect(onClosed).toHaveBeenCalled())
    const body = JSON.parse(String(fetcher.mock.calls[0][1]?.body))
    expect(body.resolution).toBeNull()
    if (!internal) expect(body.customer_resolution).toBe('Restablecido\n<estable> & verificado')
  })
  it('convierte fecha manual desde America/Guatemala explícitamente', async () => {
    const { fetcher, onClosed } = setup(internal)
    open(); fireEvent.click(screen.getByRole('radio', { name: /específicas/ }))
    expect(screen.getByText(/America\/Guatemala/)).toBeVisible()
    fireEvent.change(screen.getByLabelText(/Fecha y hora de cierre/), { target: { value: '2020-01-01T08:30:00' } })
    submit(); await waitFor(() => expect(onClosed).toHaveBeenCalled())
    expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body)).end_at).toBe('2020-01-01T14:30:00.000Z')
  })
  it.each(['', '2019-01-01T08:00', '2999-01-01T08:00'])('rechaza fecha incompleta o incompatible: %s', async value => {
    const { fetcher } = setup(internal)
    open(); fireEvent.click(screen.getByRole('radio', { name: /específicas/ }))
    fireEvent.change(screen.getByLabelText(/Fecha y hora de cierre/), { target: { value } })
    submit(); expect(await screen.findByRole('alert')).toBeVisible(); expect(fetcher).not.toHaveBeenCalled()
  })
})

it('cancela sin guardar y devuelve el foco', () => {
  const { fetcher } = setup()
  const trigger = screen.getByRole('button', { name: 'Cerrar ticket' }); trigger.focus(); open()
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(trigger).toHaveFocus(); expect(fetcher).not.toHaveBeenCalled()
})
it('no ofrece cierre en cerrado ni a lectura o edición sin permiso de cierre', () => {
  const { unmount } = setup(false, { status: 'CLOSED' }); expect(screen.queryByRole('button')).not.toBeInTheDocument(); unmount()
  setup(false, {}, ['tickets.view', 'tickets.edit']); expect(screen.queryByRole('button')).not.toBeInTheDocument()
})
it('respeta el permiso de edición separado para resolución pública', () => {
  setup(false, {}, ['tickets.close']); open()
  expect(screen.getByLabelText('Resolución interna — Opcional')).toBeEnabled()
  expect(screen.getByLabelText('Resolución para el cliente — Opcional')).toBeDisabled()
})
it('conserva textos y muestra errores de conflicto sin confirmar éxito', async () => {
  const { fetcher, onClosed } = setup()
  fetcher.mockResolvedValue(jsonResponse({ detail: 'El ticket cambió. Recarga la ficha.' }, 409))
  open(); submit()
  expect(await screen.findByRole('alert')).toHaveTextContent('Recarga la ficha')
  expect(screen.getByLabelText('Resolución interna — Opcional')).toHaveValue(ticket.resolution)
  expect(screen.getByRole('button', { name: 'Confirmar cierre' })).toBeEnabled()
  expect(onClosed).not.toHaveBeenCalled()
})
it('evita doble envío, impide cancelar mientras guarda y aborta al desmontar', () => {
  const { fetcher, unmount } = setup(false, {}, undefined, true)
  const dialog = open(); submit(); submit()
  expect(fetcher).toHaveBeenCalledOnce()
  expect(screen.getByRole('button', { name: 'Cerrando…' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Cancelar' })).toBeDisabled()
  fireEvent(dialog, new Event('cancel', { cancelable: true }))
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  const signal = fetcher.mock.calls[0][1]?.signal
  unmount(); expect(signal?.aborted).toBe(true)
})
it('mantiene la revisión original ante refresco concurrente con el modal abierto', async () => {
  const { fetcher, rerender, onClosed } = setup()
  open()
  rerender(<TicketQuickClose ticket={{ ...ticket, updated_at: '2026-10-25T16:00:00Z', resolution: 'Cambio remoto' }} onClosed={onClosed} />)
  submit(); await waitFor(() => expect(onClosed).toHaveBeenCalled())
  expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body)).expected_updated_at).toBe(ticket.updated_at)
})

it('muestra fallo de red sin perder resoluciones ni cerrar el diálogo', async () => {
  const { fetcher, onClosed } = setup()
  fetcher.mockRejectedValue(new TypeError('Network failure'))
  open(); submit()
  expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo conectar con la API')
  expect(screen.getByLabelText('Resolución interna — Opcional')).toHaveValue(ticket.resolution)
  expect(screen.getByLabelText('Resolución para el cliente — Opcional')).toHaveValue(ticket.customer_resolution)
  expect(onClosed).not.toHaveBeenCalled()
})
