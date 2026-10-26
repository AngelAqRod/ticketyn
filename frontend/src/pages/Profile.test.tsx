import { fireEvent, render, screen, waitFor, within } from '../test/render'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { Profile } from './Profile'
import { AuthContext, type Identity } from '../auth/context'
import { PermissionProvider } from '../auth/permissions'
import { jsonResponse } from '../test/fixtures'

const identity: Identity = { responsible_id: 1, name: 'Ana López', username: 'ana', role: 'OPERATOR', password_change_required: false,
  operational_access: true, permissions: ['tickets.view'], expires_in: 1800, warning_seconds: 120, role_revision: 1 }
const person = { id: 1, name: 'Ana López', username: 'ana', department: { name: 'NOC' }, position: { name: 'Ingeniería N2' }, role_name: 'Operador',
  effective_access: true, preferences: { home_page: 'DASHBOARD' }, active: true, access_granted: true }
function setup(options: { failLoad?: boolean; failSave?: boolean; failPassword?: boolean; pending?: boolean; identity?: Identity; person?: typeof person } = {}) {
  const currentIdentity = options.identity ?? identity
  const currentPerson = options.person ?? person
  const fetcher = vi.fn((url: string, init?: RequestInit) => {
    if (url === '/api/auth/profile') return Promise.resolve(jsonResponse(options.failLoad ? { detail: 'Perfil no disponible' } : currentPerson, options.failLoad ? 503 : 200))
    if (url === '/api/auth/sessions') return Promise.resolve(jsonResponse([]))
    if (url === '/api/auth/profile/preferences') {
      if (options.pending) return new Promise<Response>(() => {})
      const body = init?.body ? JSON.parse(String(init.body)) : {}
      return Promise.resolve(jsonResponse(options.failSave ? { detail: 'No se pudo guardar' } : { home_page: body.home_page ?? 'DASHBOARD' }, options.failSave ? 503 : 200))
    }
    if (url === '/api/my-tickets/summary') return Promise.resolve(jsonResponse({ assigned_count: 3, participated_count: 5, escalations_count: 2, to_verify_count: 1 }))
    if (url === '/api/auth/password') return Promise.resolve(jsonResponse(options.failPassword ? { detail: 'Contraseña actual incorrecta' } : currentIdentity, options.failPassword ? 400 : 200))
    return Promise.resolve(jsonResponse({ detail: 'Ruta inesperada' }, 404))
  })
  vi.stubGlobal('fetch', fetcher)
  const accept = vi.fn()
  render(
    <MemoryRouter>
      <AuthContext.Provider value={{ identity: currentIdentity, busy: false, accept, logout: vi.fn(async () => {}), refresh: vi.fn(async () => {}) }}>
        <PermissionProvider permissions={currentIdentity.permissions}>
          <Profile />
        </PermissionProvider>
      </AuthContext.Provider>
    </MemoryRouter>
  )
  return { fetcher, accept }
}
beforeEach(() => { vi.clearAllMocks() })

describe('Mi perfil e identidad LCD', () => {
  it('distingue puesto de rol, muestra acceso y no permite editar identidad administrativa', async () => {
    setup()
    expect(await screen.findByRole('heading', { name: 'Ana López' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Identidad de Ana López: AL' })).toBeInTheDocument()
    expect(screen.getByText('Puesto operativo')).toBeVisible()
    expect(screen.getByText('Rol de seguridad')).toBeVisible()
    expect(screen.getByText('Ingeniería N2')).toBeVisible()
    expect(screen.getByText('Operador')).toBeVisible()
    expect(screen.getByText('Acceso habilitado')).toBeVisible()
    expect(screen.getByText('NOC')).toBeVisible()
    expect(screen.queryByLabelText('Nombre completo')).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.queryByText(/Correo electrónico/)).not.toBeInTheDocument()
  })
  it('permite elegir y guardar la preferencia de inicio para Dashboard o Mis tickets', async () => {
    const { fetcher, accept } = setup()
    const form = await screen.findByRole('form', { name: 'Preferencias personales' })
    const dashRadio = within(form).getByRole('radio', { name: /Dashboard/ })
    const myTicketsRadio = within(form).getByRole('radio', { name: /Mis tickets/ })
    expect(dashRadio).toBeChecked()
    expect(myTicketsRadio).not.toBeChecked()
    expect(myTicketsRadio).toBeEnabled()

    // Submit with Dashboard
    fireEvent.submit(form)
    await screen.findByText('Preferencia guardada: Dashboard / Inicio.')
    let call = fetcher.mock.calls.find(([url]) => url.endsWith('/preferences'))!
    expect(call[1]?.method).toBe('PATCH')
    expect(JSON.parse(String(call[1]?.body))).toEqual({ home_page: 'DASHBOARD' })

    // Change to Mis tickets and submit
    fireEvent.click(myTicketsRadio)
    expect(myTicketsRadio).toBeChecked()
    expect(dashRadio).not.toBeChecked()
    fireEvent.submit(form)
    await screen.findByText('Preferencia guardada: Mis tickets.')
    const patchCalls = fetcher.mock.calls.filter(([url]) => url.endsWith('/preferences'))
    expect(patchCalls).toHaveLength(2)
    expect(JSON.parse(String(patchCalls[1][1]?.body))).toEqual({ home_page: 'MY_TICKETS' })
    expect(accept).toHaveBeenCalledWith(expect.objectContaining({ preferred_home_page: 'MY_TICKETS' }))
  })
  it('muestra accesos a las cuatro vistas en Mi actividad con sus rutas y contadores', async () => {
    setup()
    const activity = await screen.findByRole('region', { name: 'Mi actividad' })
    expect(within(activity).queryByText(/estarán disponibles con Mis tickets/)).not.toBeInTheDocument()

    const links = within(activity).getAllByRole('link')
    expect(links).toHaveLength(4)
    expect(links.map(l => l.getAttribute('href'))).toEqual([
      '/my-tickets?view=assigned',
      '/my-tickets?view=participated',
      '/my-tickets?view=escalations',
      '/my-tickets?view=to_verify',
    ])

    expect(within(activity).getByText('Asignados a mí')).toBeVisible()
    expect(within(activity).getByText('He participado')).toBeVisible()
    expect(within(activity).getByText('Mis escalamientos')).toBeVisible()
    expect(within(activity).getByText('Por verificar')).toBeVisible()

    // Live counts from summary
    expect(await within(activity).findByText('3')).toBeVisible()
    expect(within(activity).getByText('5')).toBeVisible()
    expect(within(activity).getByText('2')).toBeVisible()
    expect(within(activity).getByText('1')).toBeVisible()
  })
  it('muestra aviso adecuado cuando el usuario no tiene permisos de tickets', async () => {
    const { fetcher } = setup({ identity: { ...identity, permissions: [] } })
    const activity = await screen.findByRole('region', { name: 'Mi actividad' })
    expect(within(activity).getByText('No tienes permisos para acceder a las bandejas de Mis tickets.')).toBeVisible()
    expect(within(activity).queryAllByRole('link')).toHaveLength(0)
    expect(fetcher.mock.calls.some(([url]) => url === '/api/my-tickets/summary')).toBe(false)
  })
  it('mantiene errores de preferencias accesibles y permite reintentar', async () => {
    setup({ failSave: true })
    const form = await screen.findByRole('form', { name: 'Preferencias personales' })
    fireEvent.submit(form)
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo guardar')
    expect(screen.getByRole('button', { name: 'Guardar preferencia' })).toBeEnabled()
  })
  it('bloquea el doble envío de preferencias', async () => {
    const { fetcher } = setup({ pending: true })
    const form = await screen.findByRole('form', { name: 'Preferencias personales' })
    fireEvent.submit(form); fireEvent.submit(form)
    expect(fetcher.mock.calls.filter(([url]) => url.endsWith('/preferences'))).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Guardando…' })).toBeDisabled()
  })
  it('reutiliza cambio de contraseña y valida confirmación antes de llamar a la API', async () => {
    const { fetcher, accept } = setup()
    const form = await screen.findByRole('form', { name: 'Cambiar contraseña' })
    fireEvent.change(within(form).getByLabelText('Contraseña actual'), { target: { value: 'actual' } })
    fireEvent.change(within(form).getByLabelText('Nueva contraseña'), { target: { value: 'nueva-ñ' } })
    fireEvent.change(within(form).getByLabelText('Confirmar contraseña'), { target: { value: 'otra' } })
    fireEvent.submit(form)
    expect(await screen.findByRole('alert')).toHaveTextContent('Las contraseñas no coinciden')
    expect(fetcher.mock.calls.some(([url]) => url.endsWith('/password'))).toBe(false)
    fireEvent.change(within(form).getByLabelText('Confirmar contraseña'), { target: { value: 'nueva-ñ' } })
    fireEvent.submit(form)
    await screen.findByText('Contraseña cambiada. Las demás sesiones se cerraron.')
    expect(accept).toHaveBeenCalledWith(identity)
  })
  it('muestra errores del cambio de contraseña sin borrar los campos ajenos', async () => {
    setup({ failPassword: true })
    const form = await screen.findByRole('form', { name: 'Cambiar contraseña' })
    for (const label of ['Contraseña actual', 'Nueva contraseña', 'Confirmar contraseña']) fireEvent.change(within(form).getByLabelText(label), { target: { value: 'test' } })
    fireEvent.submit(form)
    expect(await screen.findByRole('alert')).toHaveTextContent('Contraseña actual incorrecta')
    expect(screen.getByRole('heading', { name: 'Ana López' })).toBeVisible()
  })
  it('muestra error de carga con reintento sin iniciar consultas operativas', async () => {
    const { fetcher } = setup({ failLoad: true })
    expect(await screen.findByRole('alert')).toHaveTextContent('Perfil no disponible')
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await waitFor(() => expect(fetcher.mock.calls.filter(([url]) => url === '/api/auth/profile')).toHaveLength(2))
    expect(fetcher.mock.calls.every(([url]) => url.startsWith('/api/auth/'))).toBe(true)
  })
})
