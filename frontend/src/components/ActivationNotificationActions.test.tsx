import { act, fireEvent, render, screen, waitFor } from '../test/render'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ActivationNotificationActions } from './ActivationNotificationActions'
import type { ActivationNotificationStatus, NotificationState } from '../api/mailNotifications'
import { jsonResponse } from '../test/fixtures'

afterEach(() => { vi.useRealTimers() })

function status(state: NotificationState | null = null, extra: Partial<ActivationNotificationStatus> = {}): ActivationNotificationStatus {
  return { activation_id: 42, mode: 'MANUAL', state, revision: state ? 7 : 0,
    processor_paused: false, can_request: !['PENDING', 'PREPARING', 'SENDING'].includes(state ?? ''),
    configuration_error: null, message: null, ...extra }
}

function setup(initial = status(), post?: () => Promise<Response>) {
  let current = initial
  const mock = vi.fn((path: string, init?: RequestInit): Promise<Response> => {
    expect(path).toBe('/api/activations/42/notification')
    if (init?.method === 'POST') {
      if (post) return post()
      current = status('PENDING', { ...current, state: 'PENDING', revision: current.revision + 1,
        can_request: false, message: current.processor_paused
          ? 'Notificación solicitada. El procesador está pausado.'
          : 'Notificación solicitada. El envío se procesará en segundo plano.' })
    }
    return Promise.resolve(jsonResponse(current, init?.method === 'POST' ? 202 : 200))
  })
  vi.stubGlobal('fetch', mock)
  render(<ActivationNotificationActions activationId={42} />)
  return { mock, setStatus: (value: ActivationNotificationStatus) => { current = value },
    posts: () => mock.mock.calls.filter(([, init]) => init?.method === 'POST'),
    reads: () => mock.mock.calls.filter(([, init]) => init?.method !== 'POST') }
}

describe('Notificación desde el detalle de activación', () => {
  it('solicita el primer envío manual, usando la revisión observada y sin afirmar entrega', async () => {
    const backend = setup()
    const button = await screen.findByRole('button', { name: 'Enviar notificación' })
    expect(screen.getByText('Sin envío solicitado.')).toBeInTheDocument()
    fireEvent.click(button)
    expect(await screen.findByText('Notificación solicitada. El envío se procesará en segundo plano.')).toBeInTheDocument()
    expect(screen.getByText('Solicitud pendiente.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Enviar nuevamente' })).toBeDisabled()
    expect(JSON.parse(String(backend.posts()[0][1]?.body))).toEqual({ revision: 0, confirm_uncertain: false })
    expect(screen.queryByText(/El servidor SMTP aceptó/)).not.toBeInTheDocument()
  })

  it.each(['AUTOMATIC', 'MANUAL'] as const)('permite un reenvío tras aceptación en modalidad %s', async mode => {
    const backend = setup(status('ACCEPTED', { mode }))
    fireEvent.click(await screen.findByRole('button', { name: 'Enviar nuevamente' }))
    await screen.findByText('Solicitud pendiente.')
    expect(backend.posts()).toHaveLength(1)
    expect(JSON.parse(String(backend.posts()[0][1]?.body)).revision).toBe(7)
  })

  it('oculta la acción si el evento está desactivado', async () => {
    const backend = setup(status(null, { mode: 'DISABLED', can_request: false }))
    await screen.findByText('Notificaciones desactivadas.')
    expect(screen.queryByRole('button', { name: /Enviar/ })).not.toBeInTheDocument()
    expect(backend.posts()).toHaveLength(0)
  })

  it.each([
    ['PENDING', 'Solicitud pendiente.'], ['PREPARING', 'En preparación.'], ['SENDING', 'Enviando.'],
  ] as const)('impide duplicados durante %s', async (state, label) => {
    const backend = setup(status(state))
    await screen.findByText(label)
    const button = screen.getByRole('button', { name: 'Enviar nuevamente' })
    expect(button).toBeDisabled(); fireEvent.click(button)
    expect(backend.posts()).toHaveLength(0)
  })

  it.each(['FAILED', 'PARTIAL', 'CANCELLED'] as const)('permite un nuevo intento explícito desde %s', async state => {
    const backend = setup(status(state))
    fireEvent.click(await screen.findByRole('button', { name: 'Enviar nuevamente' }))
    await screen.findByText('Solicitud pendiente.')
    expect(backend.posts()).toHaveLength(1)
  })

  it('advierte y exige confirmación de posible duplicado para un resultado incierto', async () => {
    const backend = setup(status('UNCERTAIN'))
    const button = await screen.findByRole('button', { name: 'Enviar nuevamente' })
    expect(screen.getByText(/El resultado del envío anterior es incierto/)).toBeInTheDocument()
    expect(button).toBeDisabled(); fireEvent.click(button)
    expect(backend.posts()).toHaveLength(0)
    fireEvent.click(screen.getByRole('checkbox', { name: 'Confirmo que reenviar puede duplicar el correo.' }))
    expect(button).toBeEnabled(); fireEvent.click(button)
    await screen.findByText('Solicitud pendiente.')
    expect(JSON.parse(String(backend.posts()[0][1]?.body))).toEqual({ revision: 7, confirm_uncertain: true })
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  })

  it('bloquea el doble clic durante la solicitud HTTP', async () => {
    let finish!: (response: Response) => void
    const backend = setup(status(), () => new Promise(resolve => { finish = resolve }))
    const button = await screen.findByRole('button', { name: 'Enviar notificación' })
    fireEvent.click(button); fireEvent.click(button)
    expect(button).toBeDisabled(); expect(button).toHaveTextContent('Solicitando…')
    expect(backend.posts()).toHaveLength(1)
    await act(async () => { finish(jsonResponse(status('PENDING', { can_request: false }), 202)) })
    expect(screen.getByText('Solicitud pendiente.')).toBeInTheDocument()
  })

  it('reconcilia un conflicto de revisión sin reintentar el POST', async () => {
    const backend = setup(status('ACCEPTED'), () => Promise.resolve(jsonResponse({ detail: 'La solicitud cambió; actualiza su estado.' }, 409)))
    await screen.findByRole('button', { name: 'Enviar nuevamente' })
    backend.setStatus(status('SENDING', { revision: 10 }))
    fireEvent.click(screen.getByRole('button', { name: 'Enviar nuevamente' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('La solicitud cambió')
    await screen.findByText('Enviando.')
    expect(screen.getByRole('button', { name: 'Enviar nuevamente' })).toBeDisabled()
    expect(backend.posts()).toHaveLength(1); expect(backend.reads()).toHaveLength(2)
  })

  it('actualiza la modalidad si se desactiva antes de enviar', async () => {
    const backend = setup(status(), () => Promise.resolve(jsonResponse({ detail: 'El evento de notificación está desactivado.' }, 422)))
    const button = await screen.findByRole('button', { name: 'Enviar notificación' })
    backend.setStatus(status(null, { mode: 'DISABLED', can_request: false }))
    fireEvent.click(button)
    await screen.findByText('Notificaciones desactivadas.')
    expect(screen.queryByRole('button', { name: /Enviar/ })).not.toBeInTheDocument()
    expect(backend.posts()).toHaveLength(1)
  })

  it('reconcilia una respuesta perdida sin volver a solicitar el envío', async () => {
    const backend = setup(status(), () => Promise.reject(new TypeError('Failed to fetch')))
    const button = await screen.findByRole('button', { name: 'Enviar notificación' })
    backend.setStatus(status('PENDING'))
    fireEvent.click(button)
    await screen.findByText('Solicitud pendiente.')
    expect(backend.posts()).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Enviar nuevamente' })).toBeDisabled()
  })

  it('permite dejar pendiente una solicitud con el procesador pausado sin reanudarlo', async () => {
    const backend = setup(status(null, { processor_paused: true }))
    fireEvent.click(await screen.findByRole('button', { name: 'Enviar notificación' }))
    await screen.findByText('Notificación solicitada. El procesador está pausado.')
    expect(screen.getByText(/Las solicitudes pendientes esperarán la revisión/)).toBeInTheDocument()
    expect(backend.posts()).toHaveLength(1)
  })

  it('muestra configuración incompleta sin permitir solicitar', async () => {
    const backend = setup(status(null, { can_request: false, configuration_error: 'Configura al menos un destinatario del evento en Administración.' }))
    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: 'Enviar notificación' })).toBeDisabled()
    expect(backend.posts()).toHaveLength(0)
  })

  it('consulta manualmente el estado actualizado y distingue aceptación de entrega', async () => {
    const backend = setup(status('FAILED'))
    await screen.findByRole('button', { name: 'Enviar nuevamente' })
    backend.setStatus(status('ACCEPTED', { revision: 12 }))
    fireEvent.click(screen.getByRole('button', { name: 'Consultar estado' }))
    expect(await screen.findByText(/Esto no confirma su entrega al destinatario/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Enviar nuevamente' })).toBeEnabled()
  })

  it('consulta automáticamente solo mientras el trabajo sigue activo y el procesador está habilitado', async () => {
    vi.useFakeTimers()
    const backend = setup(status('PENDING'))
    await act(async () => {})
    expect(screen.getByText('Solicitud pendiente.')).toBeInTheDocument()
    backend.setStatus(status('ACCEPTED', { revision: 10 }))
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(screen.getByText(/El servidor SMTP aceptó/)).toBeInTheDocument()
    expect(backend.reads()).toHaveLength(2)
    await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
    expect(backend.reads()).toHaveLength(2)
  })

  it('no consulta repetidamente mientras el procesador está pausado', async () => {
    vi.useFakeTimers()
    const backend = setup(status('PENDING', { processor_paused: true }))
    await act(async () => {})
    await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
    expect(backend.reads()).toHaveLength(1)
  })

  it('permite recuperar un fallo de consulta sin habilitar una revisión desconocida', async () => {
    let available = false
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(available ? jsonResponse(status()) : jsonResponse({ detail: 'Servicio temporalmente no disponible.' }, 503))))
    render(<ActivationNotificationActions activationId={42} />)
    await screen.findByRole('alert')
    expect(screen.queryByRole('button', { name: /Enviar/ })).not.toBeInTheDocument()
    available = true
    fireEvent.click(screen.getByRole('button', { name: 'Consultar estado' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Enviar notificación' })).toBeEnabled())
  })
})
