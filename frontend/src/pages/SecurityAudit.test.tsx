import { fireEvent, render, screen, waitFor, within } from '../test/render'
import { MemoryRouter } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'
import { SecurityAudit } from './SecurityAudit'
import { PermissionProvider, routeAllowed } from '../auth/permissions'
import { Layout } from '../components/Layout'
import type { AuditEntry, AuditPage } from '../api/securityAudit'

const row: AuditEntry = {
  id: 1, occurred_at: '2026-10-20T18:00:00Z', actor: { id: 3, name: 'Ángel NOC', username: 'noc' },
  target: { id: 4, name: 'Ingeniería', username: 'ingenieria' }, identifier: null,
  event: 'PASSWORD_RESET', event_label: 'Restablecimiento de contraseña', source: 'Aplicación', success: true,
  details: [{ label: 'Acción', value: 'Credencial modificada sin conservar su contenido.' }],
}
const events = [{ code: 'PASSWORD_RESET', label: 'Restablecimiento de contraseña' }, { code: 'LOGIN_FAILED_GROUP', label: 'Inicio de sesión incorrecto (grupo)' }]
const page = (items: AuditEntry[] = [row], extra: Partial<AuditPage> = {}): AuditPage => ({ items, total: items.length, limit: 50, offset: 0, events, ...extra })
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function show(permissions = ['audit.view'], path = '/security-audit') {
  return render(<MemoryRouter initialEntries={[path]}><PermissionProvider permissions={permissions}><SecurityAudit /></PermissionProvider></MemoryRouter>)
}
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('muestra auditoría de solo lectura con fecha Ticketyn, actor y afectado separados', async () => {
  const fetcher = vi.fn(() => Promise.resolve(json(page())))
  vi.stubGlobal('fetch', fetcher)
  show()
  expect(await screen.findByRole('table', { name: 'Registros de auditoría de seguridad' })).toHaveClass('operation-table')
  expect(screen.getByLabelText('Usuario o responsable')).toHaveClass('form-input')
  expect(screen.getByText('2026-10-20 12:00:00')).toBeVisible()
  expect(screen.getByText('Ángel NOC')).toBeVisible()
  expect(screen.getByText(/Ingeniería · #4/)).toBeVisible()
  expect(screen.getByText('Credencial modificada sin conservar su contenido.')).toBeVisible()
  expect(screen.queryByRole('button', { name: /Exportar|Eliminar|Editar|Guardar|Limpiar auditoría/ })).not.toBeInTheDocument()
  expect(screen.queryByLabelText(/Retención|Duración de sesión|Máximo de sesiones/)).not.toBeInTheDocument()
  expect(fetcher.mock.calls).toHaveLength(1)
})

it('aplica filtros combinados y transforma las fechas con America/Guatemala', async () => {
  const fetcher = vi.fn((_path: string) => Promise.resolve(json(page())))
  vi.stubGlobal('fetch', fetcher)
  show()
  await screen.findByText('Ángel NOC')
  fireEvent.change(screen.getByLabelText('Usuario o responsable'), { target: { value: 'Ángel' } })
  fireEvent.change(screen.getByLabelText(/^Desde/), { target: { value: '2026-10-20T12:00' } })
  fireEvent.change(screen.getByLabelText(/^Hasta/), { target: { value: '2026-10-20T13:00' } })
  fireEvent.change(screen.getByLabelText('Tipo de evento'), { target: { value: 'PASSWORD_RESET' } })
  fireEvent.change(screen.getByLabelText('Resultado'), { target: { value: 'SUCCESS' } })
  fireEvent.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2))
  const query = new URL(String(fetcher.mock.calls[1][0]), 'http://localhost').searchParams
  expect(Object.fromEntries(query)).toEqual({ username: 'Ángel', from_at: '2026-10-20T18:00:00.000Z', to_at: '2026-10-20T19:00:00.000Z', event: 'PASSWORD_RESET', result: 'SUCCESS', limit: '50' })
})

it('pagina de 50 en 50 y conserva los filtros', async () => {
  const fetcher = vi.fn((path: string) => {
    const offset = Number(new URL(path, 'http://localhost').searchParams.get('offset') ?? 0)
    return Promise.resolve(json(page([{ ...row, id: offset + 1 }], { total: 51, offset })))
  })
  vi.stubGlobal('fetch', fetcher)
  show(['audit.view'], '/security-audit?username=noc')
  await screen.findByText('Ángel NOC')
  expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2))
  await screen.findByText('Ángel NOC')
  expect(fetcher.mock.calls[1][0]).toContain('username=noc&offset=50&limit=50')
  expect(screen.getByLabelText('Página 2')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Anterior' }))
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3))
  await screen.findByText('Ángel NOC')
  expect(screen.getByLabelText('Página 1')).toBeVisible()
})

it('rechaza períodos inválidos antes de consultar y permite limpiar borradores de filtro', async () => {
  const fetcher = vi.fn(() => Promise.resolve(json(page())))
  vi.stubGlobal('fetch', fetcher)
  show()
  await screen.findByText('Ángel NOC')
  fireEvent.change(screen.getByLabelText(/^Desde/), { target: { value: '2026-10-21T12:00' } })
  fireEvent.change(screen.getByLabelText(/^Hasta/), { target: { value: '2026-10-20T12:00' } })
  fireEvent.click(screen.getByRole('button', { name: 'Aplicar filtros' }))
  expect(screen.getByRole('alert')).toHaveTextContent('El inicio del período debe ser anterior al final.')
  expect(fetcher).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
  expect(screen.getByLabelText(/^Desde/)).toHaveValue('')
  expect(screen.getByLabelText(/^Hasta/)).toHaveValue('')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('presenta fallos históricos desconocidos sin inventar identidades o cantidades y escapa texto', async () => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(json(page([{ ...row, actor: null, target: null, identifier: null, success: false,
    event: 'LOGIN_FAILED_GROUP', event_label: 'Inicio de sesión incorrecto (grupo)',
    details: [{ label: 'Información del grupo', value: 'Registro histórico; cantidad de intentos no disponible.' }, { label: 'Texto', value: '<img src=x onerror=alert(1)>' }],
  }])))))
  show()
  await screen.findByText('Usuario no identificado')
  expect(screen.getByText('Registro histórico; cantidad de intentos no disponible.')).toBeVisible()
  expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeVisible()
  expect(document.querySelector('img')).toBeNull()
  expect(within(screen.getByRole('table')).getByText('Fallido')).toBeVisible()
})

it('maneja respuesta vacía, fallo de consulta y reintento', async () => {
  let fail = true
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(fail ? json({ detail: 'No tienes permiso para realizar esta operación' }, 403) : json(page([])))))
  show()
  expect(await screen.findByRole('alert')).toHaveTextContent('No tienes permiso')
  fail = false
  fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
  expect(await screen.findByText('Sin eventos de seguridad')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
})

it('no consulta sin permiso y conserva el acceso denegado al invocar la página directamente', () => {
  const fetcher = vi.fn()
  vi.stubGlobal('fetch', fetcher)
  show(['tickets.view'])
  expect(screen.getByRole('alert')).toHaveTextContent('Acceso denegado')
  expect(fetcher).not.toHaveBeenCalled()
  expect(routeAllowed('/security-audit', { permissions: [], can: () => false, any: () => false })).toBe(false)
})

it('integra Auditoría de seguridad en Administración sin conceder otras opciones', async () => {
  vi.stubGlobal('fetch', vi.fn((path: string) => Promise.resolve(json(path === '/health' ? { status: 'ok' } : { version: __TICKETYN_FRONTEND_VERSION__ }))))
  render(<MemoryRouter initialEntries={['/security-audit']}><PermissionProvider permissions={['audit.view']}><Layout /></PermissionProvider></MemoryRouter>)
  const nav = screen.getByRole('navigation')
  expect(within(nav).getByRole('link', { name: 'Auditoría de seguridad' })).toHaveAttribute('href', '/security-audit')
  expect(within(nav).queryByRole('link', { name: 'Responsables' })).not.toBeInTheDocument()
  expect(within(nav).queryByRole('link', { name: 'Roles y permisos' })).not.toBeInTheDocument()
  expect(within(nav).queryByRole('link', { name: 'Seguridad' })).not.toBeInTheDocument()
  await screen.findByText(`Ticketyn v${__TICKETYN_FRONTEND_VERSION__}`)
})
