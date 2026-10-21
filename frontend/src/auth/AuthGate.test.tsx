import { act, fireEvent, render, screen, waitFor } from '../test/render'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { UserControls } from '../components/UserControls'
import { AuthGate } from './AuthGate'
import { getJson, downloadFile } from '../api/client'
import { sessionToken, setSessionToken } from './session'

const identity = { responsible_id: 7, name: 'Responsable autenticado', username: 'noc', role: 'SUPERADMIN', operational_access: true, password_change_required: false, role_revision: 0, permissions: ['dashboard.view', 'tickets.view'], expires_in: 1800, warning_seconds: 120 }
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
const show = () => render(<MemoryRouter><AuthGate><UserControls /><h1>Módulo operativo</h1><input aria-label="Borrador" /></AuthGate></MemoryRouter>)

beforeEach(() => { sessionStorage.clear(); localStorage.clear() })
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); sessionStorage.clear() })

describe('autenticación y sesiones', () => {
  it('muestra login sin consultar módulos ni enviar actividad automática', () => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher)
    show()
    expect(screen.getByRole('heading', { name: 'Iniciar sesión en Ticketyn' })).toBeInTheDocument()
    expect(screen.queryByText('Módulo operativo')).not.toBeInTheDocument()
    expect(fetcher).not.toHaveBeenCalled()
  })
  it('inicia sesión y conserva el token exclusivamente en sessionStorage', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(response({ ...identity, token: 'opaque-test-token' }))))
    show()
    fireEvent.change(screen.getByLabelText('Usuario'), { target: { value: 'noc' } })
    fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: '  literal secret  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Iniciar sesión' }))
    expect(await screen.findByText('Módulo operativo')).toBeVisible()
    expect(sessionToken()).toBe('opaque-test-token')
    expect(localStorage.length).toBe(0)
    const options = vi.mocked(fetch).mock.calls[0][1]!
    expect(JSON.parse(String(options.body)).password).toBe('  literal secret  ')
  })
  it('exige cambiar contraseña temporal antes de mostrar operaciones', async () => {
    setSessionToken('token')
    vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(response(url.endsWith('/password') ? identity : { ...identity, password_change_required: true, operational_access: false }))))
    show()
    expect(await screen.findByRole('heading', { name: 'Cambiar contraseña temporal' })).toBeInTheDocument()
    expect(screen.queryByText('Módulo operativo')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Contraseña actual'), { target: { value: 'temporary' } })
    fireEvent.change(screen.getByLabelText('Nueva contraseña'), { target: { value: 'x' } })
    fireEvent.change(screen.getByLabelText('Confirmar contraseña'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Cambiar contraseña' }))
    expect(await screen.findByText('Módulo operativo')).toBeVisible()
  })
  it('comprueba permisos cada 15 segundos sin renovar actividad y advierte a dos minutos', async () => {
    setSessionToken('token')
    const fetcher = vi.fn((_path: string, _options?: RequestInit) => Promise.resolve(response({ ...identity, expires_in: 119 })))
    vi.stubGlobal('fetch', fetcher)
    vi.useFakeTimers()
    show()
    await act(async () => {})
    expect(screen.getByText(/Tu sesión está por vencer/)).toBeVisible()
    await act(async () => { await vi.advanceTimersByTimeAsync(15000) })
    expect(fetcher.mock.calls.length).toBeGreaterThanOrEqual(2)
    expect(fetcher.mock.calls.every(([path]) => path === '/api/auth/me')).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Continuar sesión' }))
    await act(async () => {})
    expect(fetcher).toHaveBeenCalledWith('/api/auth/activity', expect.any(Object))
  })
  it('oculta operaciones si cambia el permiso o la sesión vence', async () => {
    setSessionToken('token')
    let current = identity
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(response(current))))
    show()
    expect(await screen.findByText('Módulo operativo')).toBeVisible()
    current = { ...identity, role: 'OPERATOR', operational_access: false }
    fireEvent(window, new Event('focus'))
    expect(await screen.findByText(/no tiene permisos sobre los módulos/)).toBeVisible()
    expect(screen.getByText('Módulo operativo')).not.toBeVisible()
    vi.stubGlobal('fetch', vi.fn((_path: string, _options?: RequestInit) => Promise.resolve(response({ detail: 'Sesión vencida' }, 401))))
    fireEvent(window, new Event('focus'))
    expect(await screen.findByRole('heading', { name: 'Iniciar sesión en Ticketyn' })).toBeVisible()
    expect(sessionToken()).toBe(null)
  })
  it('adjunta Authorization a consultas y descargas y limpia la sesión ante 401', async () => {
    setSessionToken('opaque')
    const fetcher = vi.fn((_path: string, _options?: RequestInit) => Promise.resolve(response({ detail: 'Sesión vencida' }, 401)))
    vi.stubGlobal('fetch', fetcher)
    await expect(getJson('/api/private')).rejects.toThrow('Sesión vencida')
    expect(new Headers(fetcher.mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer opaque')
    expect(sessionToken()).toBe(null)
    setSessionToken('other')
    await expect(downloadFile('/api/export', 'export.pdf')).rejects.toThrow('Sesión vencida')
    expect(new Headers(fetcher.mock.calls[1][1]?.headers).get('Authorization')).toBe('Bearer other')
    expect(sessionToken()).toBe(null)
  })
  it('cierra sesión y elimina el borrador del usuario anterior', async () => {
    setSessionToken('token')
    vi.stubGlobal('fetch', vi.fn((path: string) => Promise.resolve(response(path.endsWith('/logout') ? { closed: true } : identity))))
    show()
    expect(await screen.findByText('Módulo operativo')).toBeVisible()
    fireEvent.change(screen.getByLabelText('Borrador'), { target: { value: 'dato privado' } })
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    await waitFor(() => expect(sessionToken()).toBe(null))
    expect(screen.queryByLabelText('Borrador')).not.toBeInTheDocument()
  })
})


it('una respuesta 401 antigua no elimina una sesión nueva', async () => {
  setSessionToken('old')
  let respond!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { respond = resolve })))
  const pending = getJson('/api/private')
  setSessionToken('new')
  respond(response({ detail: 'Sesión antigua vencida' }, 401))
  await expect(pending).rejects.toThrow('Sesión antigua vencida')
  expect(sessionToken()).toBe('new')
})

it('impide solicitudes duplicadas por doble clic en login', async () => {
  let respond!: (response: Response) => void
  const fetcher = vi.fn(() => new Promise<Response>((resolve) => { respond = resolve }))
  vi.stubGlobal('fetch', fetcher)
  show()
  fireEvent.change(screen.getByLabelText('Usuario'), { target: { value: 'noc' } })
  fireEvent.change(screen.getByLabelText('Contraseña'), { target: { value: 'x' } })
  const button = screen.getByRole('button', { name: 'Iniciar sesión' })
  fireEvent.click(button); fireEvent.click(button)
  expect(fetcher).toHaveBeenCalledTimes(1)
  expect(button).toBeDisabled()
  await act(async () => { respond(response({ ...identity, token: 'opaque' })) })
  expect(screen.getByText('Módulo operativo')).toBeVisible()
})

it('la aplicación completa inicia protegida sin consultas operativas anónimas', async () => {
  const { default: App } = await import('../App')
  const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher)
  render(<MemoryRouter initialEntries={['/tickets']}><App /></MemoryRouter>)
  expect(screen.getByRole('heading', { name: 'Iniciar sesión en Ticketyn' })).toBeVisible()
  expect(fetcher).not.toHaveBeenCalled()
})
