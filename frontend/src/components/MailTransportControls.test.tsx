import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { MailTransportControls } from './MailTransportControls'
import type { OAuthConfig, SmtpConfig } from '../api/mailNotifications'
import { jsonResponse } from '../test/fixtures'

const config: SmtpConfig = { host: 'smtp.example.com', port: 587, security: 'STARTTLS', allow_unencrypted: false, sender_email: 'noc@example.com', sender_name: 'NOC', auth_method: 'NONE', provider: null, username: null, password_configured: false, oauth_credentials_configured: false, configured: true }
const oauth: OAuthConfig = { client_id: 'example-client', tenant_id: '', redirect_uri: 'http://localhost:5173/api/mail-notifications/oauth/callback', status: 'REQUIRES_AUTHORIZATION', client_secret_configured: true, service_account_configured: false }
function setup(options: { config?: Partial<SmtpConfig>; settings?: Partial<OAuthConfig>; status?: string; pending?: boolean; authFailure?: boolean } = {}) {
  let settings = { ...oauth, ...options.settings }
  const fetch = vi.fn((path: string, init?: RequestInit): Promise<Response> => {
    if (path.endsWith('/smtp/test')) return options.pending ? new Promise(() => {}) : Promise.resolve(jsonResponse({ status: options.status ?? 'ACCEPTED', message: options.status ? 'Error seguro de prueba' : 'Mensaje aceptado por el servidor SMTP. Esto no garantiza la entrega al buzón.' }))
    if (path.endsWith('/oauth/authorize')) return Promise.resolve(jsonResponse({ detail: 'La autorización no pudo iniciarse.' }, 422))
    if (path.endsWith('/oauth/disconnect')) { settings = { ...settings, status: 'REQUIRES_AUTHORIZATION' }; return Promise.resolve(jsonResponse(settings)) }
    if (path.endsWith('/oauth')) {
      if (init?.method === 'PATCH') {
        const payload = JSON.parse(String(init.body))
        settings = { ...settings, client_id: payload.client_id ?? settings.client_id, tenant_id: payload.tenant_id ?? settings.tenant_id, client_secret_configured: !!payload.client_secret || settings.client_secret_configured, service_account_configured: !!payload.service_account || settings.service_account_configured }
      }
      return Promise.resolve(jsonResponse(settings))
    }
    return Promise.resolve(jsonResponse({ detail: 'Unexpected' }, 404))
  })
  vi.stubGlobal('fetch', fetch)
  render(<MailTransportControls config={{ ...config, ...options.config }} />)
  return fetch
}

it('envía solo un destinatario temporal y explica la aceptación SMTP', async () => {
  const fetch = setup()
  fireEvent.change(screen.getByLabelText(/Destinatario temporal/), { target: { value: 'temporary@example.com' } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar correo de prueba' }))
  await screen.findByText(/Mensaje aceptado por el servidor SMTP/)
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({ recipient: 'temporary@example.com' })
  expect(screen.getByLabelText(/Destinatario temporal/)).toHaveValue('')
  expect(screen.queryByRole('form', { name: 'Credenciales OAuth2' })).not.toBeInTheDocument()
})

it('no permite enviar sin transporte configurado ni destinatario', () => {
  setup({ config: { configured: false } })
  expect(screen.getByRole('button', { name: 'Enviar correo de prueba' })).toBeDisabled()
  expect(screen.getByLabelText(/Destinatario temporal/)).toBeDisabled()
})

it('impide doble clic mientras una prueba está en curso', async () => {
  const fetch = setup({ pending: true })
  fireEvent.change(screen.getByLabelText(/Destinatario temporal/), { target: { value: 'temporary@example.com' } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar correo de prueba' }))
  fireEvent.click(screen.getByRole('button', { name: 'Procesando correo…' }))
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(screen.getByLabelText(/Destinatario temporal/)).toBeDisabled()
})

it.each(['CONNECTION_ERROR', 'TLS_ERROR', 'AUTH_ERROR', 'RECIPIENT_REJECTED', 'UNCERTAIN'])('muestra %s sin repetir automáticamente la prueba', async status => {
  const fetch = setup({ status })
  fireEvent.change(screen.getByLabelText(/Destinatario temporal/), { target: { value: 'temporary@example.com' } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar correo de prueba' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Error seguro de prueba')
  expect(fetch).toHaveBeenCalledTimes(1)
  if (status === 'AUTH_ERROR') expect(screen.getByText('Estado: Error de autenticación')).toBeInTheDocument()
})

it('conserva secretos al guardar metadatos y permite reemplazarlos sin revelarlos', async () => {
  const fetch = setup({ config: { auth_method: 'OAUTH2_DELEGATED', provider: 'GMAIL', username: 'noc@example.com' } })
  await screen.findByLabelText(/Identificador de aplicación/)
  expect(screen.getByText('Estado: Requiere autorización')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Guardar credenciales OAuth2' }))
  await screen.findByText('Configuración OAuth2 guardada sin revelar credenciales.')
  let writes = fetch.mock.calls.filter(([, init]) => init?.method === 'PATCH')
  expect(JSON.parse(String(writes[0][1]?.body))).toEqual({})
  fireEvent.change(screen.getByLabelText(/Secreto de aplicación/), { target: { value: 'synthetic-secret' } })
  fireEvent.click(screen.getByRole('button', { name: 'Guardar credenciales OAuth2' }))
  await waitFor(() => expect(screen.getByLabelText(/Secreto de aplicación/)).toHaveValue(''))
  writes = fetch.mock.calls.filter(([, init]) => init?.method === 'PATCH')
  expect(JSON.parse(String(writes[1][1]?.body))).toEqual({ client_secret: 'synthetic-secret' })
  expect(screen.queryByText('synthetic-secret')).not.toBeInTheDocument()
})

it('inicia autorización y presenta errores seguros; permite desconectar', async () => {
  const fetch = setup({ config: { auth_method: 'OAUTH2_DELEGATED', provider: 'MICROSOFT_365', username: 'noc@example.com' }, settings: { tenant_id: 'tenant', status: 'CONNECTED' } })
  await screen.findByLabelText(/Identificador de tenant/)
  expect(screen.getByText('Estado: Autorizado')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Autorizar cuenta de correo' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('La autorización no pudo iniciarse.')
  expect(fetch.mock.calls.some(([path]) => path.endsWith('/oauth/authorize'))).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Desconectar cuenta' }))
  await screen.findByText(/Conexión local desconectada/)
  expect(screen.getByText('Estado: Requiere autorización')).toBeInTheDocument()
})

it('muestra solo la cuenta de servicio para Google Workspace de aplicación', async () => {
  const fetch = setup({ config: { auth_method: 'OAUTH2_APPLICATION', provider: 'GOOGLE_WORKSPACE', username: 'noc@example.com' }, settings: { service_account_configured: true, status: 'CONFIGURED' } })
  await screen.findByLabelText(/JSON de cuenta de servicio/)
  expect(screen.queryByLabelText(/Identificador de tenant/)).not.toBeInTheDocument()
  expect(screen.queryByLabelText(/Secreto de aplicación/)).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Autorizar cuenta de correo' })).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText(/JSON de cuenta de servicio/), { target: { value: '{"private_key":"synthetic"}' } })
  fireEvent.click(screen.getByRole('button', { name: 'Guardar credenciales OAuth2' }))
  await screen.findByText('Configuración OAuth2 guardada sin revelar credenciales.')
  expect(screen.getByLabelText(/JSON de cuenta de servicio/)).toHaveValue('')
  const payload = JSON.parse(String(fetch.mock.calls.find(([, init]) => init?.method === 'PATCH')?.[1]?.body))
  expect(payload).toEqual({ service_account: '{"private_key":"synthetic"}' })
})

it('actualiza el estado de aplicación tras una prueba aceptada', async () => {
  setup({ config: { auth_method: 'OAUTH2_APPLICATION', provider: 'MICROSOFT_365', username: 'noc@example.com' }, settings: { status: 'CONFIGURED' } })
  await screen.findByLabelText(/Identificador de tenant/)
  expect(screen.getByText('Estado: Configurado')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText(/Destinatario temporal/), { target: { value: 'temporary@example.com' } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar correo de prueba' }))
  await screen.findByText('Estado: Autorizado')
})

it.each(['save', 'disconnect'] as const)('reemplaza un error previo de autenticación tras %s', async action => {
  setup({ config: { auth_method: 'OAUTH2_DELEGATED', provider: 'GMAIL', username: 'noc@example.com' }, status: 'AUTH_ERROR' })
  await screen.findByLabelText(/Identificador de aplicación/)
  fireEvent.change(screen.getByLabelText(/Destinatario temporal/), { target: { value: 'temporary@example.com' } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar correo de prueba' }))
  await screen.findByText('Estado: Error de autenticación')
  fireEvent.click(screen.getByRole('button', { name: action === 'save' ? 'Guardar credenciales OAuth2' : 'Desconectar cuenta' }))
  await screen.findByText(action === 'save' ? 'Configuración OAuth2 guardada sin revelar credenciales.' : /Conexión local desconectada/)
  expect(screen.getByText('Estado: Requiere autorización')).toBeInTheDocument()
  expect(screen.queryByText('Estado: Error de autenticación')).not.toBeInTheDocument()
})

it('descarta el resultado de una prueba al recibir una configuración SMTP actualizada', async () => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ status: 'AUTH_ERROR', message: 'Credencial anterior rechazada.' }))))
  const passwordConfig = { ...config, auth_method: 'PASSWORD' as const, username: 'noc@example.com', password_configured: true }
  const view = render(<MailTransportControls config={passwordConfig} />)
  fireEvent.change(screen.getByLabelText(/Destinatario temporal/), { target: { value: 'temporary@example.com' } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar correo de prueba' }))
  await screen.findByText('Estado: Error de autenticación')
  view.rerender(<MailTransportControls config={{ ...passwordConfig }} />)
  expect(screen.getByText('Estado: Configurado')).toBeInTheDocument()
  expect(screen.queryByText('Credencial anterior rechazada.')).not.toBeInTheDocument()
})

it.each(['AUTH_ERROR', 'ACCEPTED'])('ignora una respuesta %s tardía de una configuración anterior', async status => {
  let complete!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { complete = resolve })))
  const view = render(<MailTransportControls config={config} />)
  fireEvent.change(screen.getByLabelText(/Destinatario temporal/), { target: { value: 'temporary@example.com' } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar correo de prueba' }))
  view.rerender(<MailTransportControls config={{ ...config, host: 'smtp-new.example.com' }} />)
  await act(async () => { complete(jsonResponse({ status, message: 'Resultado de la configuración anterior.' })) })
  expect(screen.getByText('Estado: Configurado')).toBeInTheDocument()
  expect(screen.queryByText('Resultado de la configuración anterior.')).not.toBeInTheDocument()
})
