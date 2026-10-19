import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { MailNotifications } from './MailNotifications'
import { jsonResponse } from '../test/fixtures'
import type { MailEvent, SmtpConfig } from '../api/mailNotifications'

const base = '/api/mail-notifications', eventKey = 'fms.activation.created'
const defaults: SmtpConfig = { host: null, port: 587, security: 'STARTTLS', allow_unencrypted: false, sender_email: null, sender_name: '', auth_method: 'NONE', provider: null, username: null, password_configured: false, oauth_credentials_configured: false, configured: false }
const initialEvent: MailEvent = { event_key: eventKey, label: 'Registro de activación FMS', mode: 'DISABLED', to: [], cc: [], bcc: [] }
const fields = [
  { id: 'activation.activation_notes', group: 'Activación FMS', label: 'Notas de activación', format: 'multiline', temporality: 'HISTORICAL' },
  { id: 'activation.initial_capacity', group: 'Activación FMS', label: 'Capacidad inicial', format: 'capacity', temporality: 'HISTORICAL' },
  { id: 'circuit.current_capacity', group: 'Circuito', label: 'Capacidad actual', format: 'capacity', temporality: 'CURRENT' },
  { id: 'customer.name', group: 'Cliente', label: 'Cliente', format: 'text', temporality: 'CURRENT' },
]
function setup(options: { smtp?: Partial<SmtpConfig>; failLoad?: boolean; failSave?: boolean; pending?: boolean; templates?: boolean } = {}) {
  let smtp = { ...defaults, ...options.smtp }, event = { ...initialEvent }
  const mock = vi.fn((path: string, init?: RequestInit): Promise<Response> => {
    if (init?.method === 'PATCH') {
      if (options.pending) return new Promise<Response>(() => {})
      if (options.failSave) return Promise.resolve(jsonResponse({ detail: 'No se pudo proteger la credencial.' }, 503))
      const payload = JSON.parse(String(init.body))
      if (path === base + '/smtp') {
        const { smtp_password, clear_password, ...publicChanges } = payload
        smtp = { ...smtp, ...publicChanges, password_configured: smtp_password ? true : clear_password ? false : smtp.password_configured, configured: true }
        return Promise.resolve(jsonResponse(smtp))
      }
      event = { ...event, ...payload }; return Promise.resolve(jsonResponse(event))
    }
    if (options.failLoad) return Promise.resolve(jsonResponse({ detail: 'Configuración no disponible' }, 503))
    if (path.endsWith('/template')) return Promise.resolve(jsonResponse({ version: 1, subject: [], body: [] }))
    if (path.startsWith('/api/activations?')) return Promise.resolve(jsonResponse([]))
    if (path === base + '/oauth') return Promise.resolve(jsonResponse({ client_id: '', tenant_id: '', redirect_uri: null, status: 'UNCONFIGURED', client_secret_configured: false, service_account_configured: false }))
    if (path === base + '/smtp') return Promise.resolve(jsonResponse(smtp))
    if (path === base + '/events') return Promise.resolve(jsonResponse([event]))
    if (path === `${base}/events/${eventKey}/fields`) return Promise.resolve(jsonResponse(fields))
    return Promise.resolve(jsonResponse({ detail: 'Endpoint inesperado' }, 404))
  })
  vi.stubGlobal('fetch', mock)
  render(<MemoryRouter><MailNotifications section={options.templates ? "templates" : "configuration"} /></MemoryRouter>)
  return mock
}
const writes = (mock: ReturnType<typeof setup>) => mock.mock.calls.filter(([, init]) => init?.method === 'PATCH')
async function loaded() { await screen.findByRole('form', { name: 'Configuración SMTP' }) }
function fill() {
  fireEvent.change(screen.getByLabelText(/^Servidor SMTP/), { target: { value: 'smtp.example.com' } })
  fireEvent.change(screen.getByLabelText(/^Dirección del remitente/), { target: { value: 'noc@example.com' } })
}

describe('Notificaciones por correo: solo configuración', () => {
  it('explica las modalidades vigentes sin textos de etapas anteriores', async () => {
    setup(); await loaded()
    expect(screen.getByText(/Automático solicita el envío al registrar una activación/)).toBeInTheDocument()
    expect(screen.getByText(/Manual requiere solicitarlo desde el detalle/)).toBeInTheDocument()
    expect(screen.queryByText(/todavía no|se almacena para etapas posteriores/)).not.toBeInTheDocument()
  })
  it('muestra formularios y campos amigables sin advertencia de acceso ni acciones de envío', async () => {
    const mock = setup({ templates: true }); await screen.findByRole('region', { name: 'Campos dinámicos disponibles' })
    expect(screen.getByRole('heading', { name: 'Plantillas de correo' })).toBeInTheDocument()
    expect(screen.queryByText(/cualquier persona con acceso/)).not.toBeInTheDocument()
    const registry = screen.getByRole('region', { name: 'Campos dinámicos disponibles' })
    for (const group of ['Activación FMS', 'Circuito', 'Cliente']) expect(within(registry).getByRole('heading', { name: group })).toBeInTheDocument()
    expect(within(registry).getByText('Notas de activación')).toBeInTheDocument()
    expect(within(registry).queryByText('activation.initial_capacity')).not.toBeInTheDocument()
    expect(within(registry).getByText('Capacidad actual')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /enviar|probar|conectar/i })).not.toBeInTheDocument()
    expect(writes(mock)).toHaveLength(0)
    expect(screen.queryByLabelText('Modalidad')).not.toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Configuración SMTP' })).not.toBeInTheDocument()
    expect(mock.mock.calls.some(([path]) => path === base + '/smtp')).toBe(false)
  })
  it('guarda transporte y contraseña sin mostrarla después', async () => {
    const mock = setup(); await loaded(); fill()
    fireEvent.change(screen.getByLabelText('Método de autenticación'), { target: { value: 'PASSWORD' } })
    fireEvent.change(screen.getByLabelText(/^Usuario SMTP/), { target: { value: 'smtp-user' } })
    fireEvent.change(screen.getByLabelText(/^Contraseña SMTP/), { target: { value: 'synthetic-password' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar configuración SMTP' }))
    expect(await screen.findByText('Configuración SMTP guardada. No se realizó ninguna conexión.')).toBeInTheDocument()
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ host: 'smtp.example.com', sender_email: 'noc@example.com', auth_method: 'PASSWORD', smtp_password: 'synthetic-password' })
    expect(screen.getByLabelText(/^Contraseña SMTP/)).toHaveValue('')
    expect(screen.getByText(/configurada; su contenido no se devuelve/)).toBeInTheDocument()
    expect(screen.queryByText('synthetic-password')).not.toBeInTheDocument()
  })
  it('conserva la credencial guardada al actualizar otros parámetros', async () => {
    const mock = setup({ smtp: { host: 'smtp.example.com', sender_email: 'noc@example.com', auth_method: 'PASSWORD', username: 'user', password_configured: true, configured: true } }); await loaded()
    expect(screen.getByLabelText(/^Contraseña SMTP/)).toHaveValue('')
    fireEvent.change(screen.getByLabelText('Nombre visible del remitente'), { target: { value: 'NOC' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar configuración SMTP' }))
    await screen.findByText('Configuración SMTP guardada. No se realizó ninguna conexión.')
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).toEqual({ sender_name: 'NOC' })
  })
  it.each(['OAUTH2_DELEGATED', 'OAUTH2_APPLICATION'])('guarda perfil %s sin pedir secretos OAuth2', async method => {
    const mock = setup(); await loaded(); fill()
    fireEvent.change(screen.getByLabelText('Método de autenticación'), { target: { value: method } })
    expect(screen.getByText(/Guarda primero el perfil SMTP/)).toBeInTheDocument()
    expect(screen.queryByLabelText(/^Contraseña SMTP/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/token|secreto de cliente/i)).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/^Proveedor OAuth2/), { target: { value: 'MICROSOFT_365' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar configuración SMTP' }))
    await screen.findByText('Configuración SMTP guardada. No se realizó ninguna conexión.')
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ auth_method: method, provider: 'MICROSOFT_365' })
  })
  it('requiere autorización explícita para guardar sin cifrado', async () => {
    const mock = setup(); await loaded(); fill()
    fireEvent.change(screen.getByLabelText('Seguridad de conexión'), { target: { value: 'NONE' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar configuración SMTP' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('autorizar expresamente')
    expect(writes(mock)).toHaveLength(0)
    fireEvent.click(screen.getByLabelText('Autorizo un relé local o confiable sin cifrado'))
    fireEvent.click(screen.getByRole('button', { name: 'Guardar configuración SMTP' }))
    await screen.findByText('Configuración SMTP guardada. No se realizó ninguna conexión.')
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).toMatchObject({ security: 'NONE', allow_unencrypted: true })
  })
  it('guarda modalidad y destinatarios independientes', async () => {
    const mock = setup(); await loaded()
    fireEvent.change(screen.getByLabelText('Modalidad'), { target: { value: 'AUTOMATIC' } })
    fireEvent.change(screen.getByLabelText('Para'), { target: { value: 'one@example.com\ntwo@example.com' } })
    fireEvent.change(screen.getByLabelText('CC'), { target: { value: 'cc@example.com; other@example.com' } })
    fireEvent.change(screen.getByLabelText('CCO'), { target: { value: 'hidden@example.com' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar evento' }))
    expect(await screen.findByText('Modalidad y destinatarios guardados.')).toBeInTheDocument()
    expect(writes(mock)[0][0]).toBe(`${base}/events/${eventKey}`)
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).toEqual({ mode: 'AUTOMATIC', to: ['one@example.com', 'two@example.com'], cc: ['cc@example.com', 'other@example.com'], bcc: ['hidden@example.com'] })
  })
  it('conserva el formulario al mostrar un error de guardado', async () => {
    const mock = setup({ failSave: true }); await loaded(); fill()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar configuración SMTP' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo proteger la credencial.')
    expect(screen.getByLabelText(/^Servidor SMTP/)).toHaveValue('smtp.example.com')
    expect(screen.getByRole('button', { name: 'Guardar configuración SMTP' })).toBeEnabled()
    expect(writes(mock)).toHaveLength(1)
  })
  it('evita doble envío del formulario y muestra progreso', async () => {
    const mock = setup({ pending: true }); await loaded(); fill()
    const form = screen.getByRole('form', { name: 'Configuración SMTP' })
    fireEvent.submit(form); fireEvent.submit(form)
    expect(writes(mock)).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Guardando...' })).toBeDisabled()
    expect(screen.getByLabelText(/^Servidor SMTP/)).toBeDisabled()
  })
  it('muestra error de carga sin formularios incompletos', async () => {
    setup({ failLoad: true })
    expect(await screen.findByText('Configuración no disponible')).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Configuración SMTP' })).not.toBeInTheDocument()
  })
})

it('mantiene SMTP, modalidad y destinatarios fuera del editor de plantillas', async () => {
  const mock = setup(); await loaded()
  expect(screen.getByRole('heading', { name: 'Configuración de correo' })).toBeInTheDocument()
  expect(screen.getByLabelText('Modalidad')).toHaveValue('DISABLED')
  expect(screen.queryByRole('heading', { name: 'Plantilla del correo' })).not.toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'Campos dinámicos disponibles' })).not.toBeInTheDocument()
  expect(mock.mock.calls.some(([path]) => path.endsWith('/template') || path.endsWith('/fields') || path.startsWith('/api/activations'))).toBe(false)
})
