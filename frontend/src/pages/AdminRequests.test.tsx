import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { PermissionProvider, routeAllowed } from '../auth/permissions'
import { AdminRequests } from './AdminRequests'
import { AdminRequestDetail } from './AdminRequestDetail'
import { AdminRequestForm } from './AdminRequestForm'
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const person = { id: 7, name: 'Marta Solicitante', active: true }
const request = {
  id: 3, reference: 'SOL-0000003', request_date: '2026-11-10', requester_id: 7, customer_id: null, circuit_id: null, type_id: 2, description: 'Asignar IP pública', notes: null, status: 'REGISTERED', application_start: null, application_end: null,
  created_by: 1, created_at: '2026-11-16T12:00:00Z', updated_at: '2026-11-16T12:00:00Z', requester: { id: 7, name: 'Marta Solicitante' }, registered_by: { id: 1, name: 'Admin' },
  customer: null, circuit: null, type: { id: 2, name: 'Asignación de IP pública' },
  links: { tickets: [{ id: 9, link_id: 1, reference: 'TCK-0000009', title: 'Fuera de ventana', date: '2025-01-01T10:00:00Z' }], internal_tickets: [], changes: [] }, events: [],
}
const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } }))
function stub(handler: (path: string, init?: RequestInit) => unknown) {
  const fetcher = vi.fn((path: string, init?: RequestInit) => json(handler(path, init)))
  vi.stubGlobal('fetch', fetcher)
  return fetcher
}
const catalogs = (path: string) => path.includes('/responsibles') ? [person] : path.includes('admin-request-types') ? [{ id: 2, name: 'Asignación de IP pública', active: true }] : path.includes('/customers') || path.includes('/circuits') ? [] : undefined

it('lists requests with registration date apart from request date and hides creation without permission', async () => {
  stub(path => catalogs(path) ?? { total: 1, items: [request] })
  render(<PermissionProvider permissions={['admin_requests.view']}><MemoryRouter><AdminRequests /></MemoryRouter></PermissionProvider>)
  expect(await screen.findByRole('link', { name: 'SOL-0000003' })).toBeVisible()
  expect(screen.getByText('10/11/2026')).toBeVisible()
  expect(screen.queryByRole('link', { name: 'Registrar solicitud' })).not.toBeInTheDocument()
})

function detail(permissions: string[], onFetch?: (path: string, init?: RequestInit) => unknown) {
  const fetcher = stub((path, init) => onFetch?.(path, init) ?? (path.includes('/candidates/') ? { total: 1, items: [{ id: 11, reference: 'TCK-0000011', title: 'Dentro', date: '2026-11-12T10:00:00Z' }] } : request))
  render(<PermissionProvider permissions={permissions}><MemoryRouter initialEntries={['/admin-requests/3']}><Routes><Route path="/admin-requests/:id" element={<AdminRequestDetail />} /></Routes></MemoryRouter></PermissionProvider>)
  return fetcher
}

it('keeps saved links visible outside the window and states the inclusive ±15 day interval', async () => {
  const fetcher = detail(['admin_requests.view', 'admin_requests.link', 'tickets.view'])
  expect(await screen.findByText('TCK-0000009')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Desvincular TCK-0000009' })).toBeVisible()
  const section = screen.getByRole('region', { name: 'Tickets de cliente' })
  fireEvent.click(within(section).getByRole('button', { name: 'Buscar registros para asociar' }))
  expect(await within(section).findByText(/entre el 26\/10\/2026 y el 25\/11\/2026/)).toBeVisible()
  fireEvent.click(await within(section).findByRole('button', { name: 'Asociar TCK-0000011' }))
  await waitFor(() => expect(fetcher.mock.calls.some(([path, init]) => path.endsWith('/links') && init?.method === 'POST' && String(init.body).includes('"kind":"ticket"'))).toBe(true))
})

it('offers neither search nor unlink without link permission', async () => {
  detail(['admin_requests.view'])
  expect(await screen.findByText('TCK-0000009')).toBeVisible()
  expect(screen.queryByRole('button', { name: /Desvincular|Buscar registros/ })).not.toBeInTheDocument()
})

it('registers a request with optional customer and circuit left empty', async () => {
  const fetcher = stub((path, init) => catalogs(path) ?? (init?.method === 'POST' ? request : {}))
  render(<PermissionProvider permissions={['admin_requests.create']}><MemoryRouter><AdminRequestForm /></MemoryRouter></PermissionProvider>)
  await screen.findByRole('option', { name: 'Marta Solicitante' })
  await screen.findByRole('option', { name: 'Asignación de IP pública' })
  fireEvent.change(screen.getByLabelText('Solicitante'), { target: { value: '7' } })
  fireEvent.change(screen.getByLabelText('Tipo de solicitud'), { target: { value: '2' } })
  fireEvent.change(screen.getByLabelText('Descripción del requerimiento'), { target: { value: ' Asignar IP pública ' } })
  fireEvent.click(screen.getByRole('button', { name: 'Registrar solicitud' }))
  await waitFor(() => expect(fetcher.mock.calls.some(([path, init]) => path === '/api/admin-requests' && init?.method === 'POST')).toBe(true))
  const [, init] = fetcher.mock.calls.find(([path, init]) => path === '/api/admin-requests' && init?.method === 'POST')!
  expect(JSON.parse(String(init?.body))).toMatchObject({ requester_id: 7, type_id: 2, customer_id: null, circuit_id: null, description: 'Asignar IP pública', notes: null })
  expect(JSON.parse(String(init?.body)).request_date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
})

it('guards routes by admin request permissions', () => {
  const only = (...codes: string[]) => ({ can: (...c: string[]) => c.every(x => codes.includes(x)), any: (...c: string[]) => c.some(x => codes.includes(x)), permissions: codes })
  expect(routeAllowed('/admin-requests', only('admin_requests.view'))).toBe(true)
  expect(routeAllowed('/admin-requests/new', only('admin_requests.view'))).toBe(false)
  expect(routeAllowed('/admin-requests/4/edit', only('admin_requests.edit'))).toBe(true)
  expect(routeAllowed('/admin-requests', only())).toBe(false)
})

it('shows status and period, and moves the status manually only with edit permission', async () => {
  const current = { ...request, status: 'IN_PROGRESS', application_start: '2026-11-20', application_end: '2026-11-25' }
  const fetcher = stub((path, init) => path.endsWith('/status') ? { ...current, status: JSON.parse(String(init?.body)).status } : current)
  render(<PermissionProvider permissions={['admin_requests.view', 'admin_requests.edit']}><MemoryRouter initialEntries={['/admin-requests/3']}><Routes><Route path="/admin-requests/:id" element={<AdminRequestDetail />} /></Routes></MemoryRouter></PermissionProvider>)
  expect(await screen.findByText('En ejecución')).toBeVisible()
  expect(screen.getByText('20/11/2026 – 25/11/2026')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Pasar a Completada' }))
  await waitFor(() => expect(fetcher.mock.calls.some(([path, init]) => path === '/api/admin-requests/3/status' && JSON.parse(String(init?.body)).status === 'COMPLETED')).toBe(true))
  expect(await screen.findByText('Completada')).toBeVisible()
  cleanup()
  stub(() => current)
  render(<PermissionProvider permissions={['admin_requests.view']}><MemoryRouter initialEntries={['/admin-requests/3']}><Routes><Route path="/admin-requests/:id" element={<AdminRequestDetail />} /></Routes></MemoryRouter></PermissionProvider>)
  await screen.findByText('En ejecución')
  expect(screen.queryByRole('button', { name: /Pasar a/ })).not.toBeInTheDocument()
})

it('lists the status column, filters by status and validates the period in the form', async () => {
  stub(path => catalogs(path) ?? { total: 1, items: [request] })
  render(<PermissionProvider permissions={['admin_requests.view']}><MemoryRouter><AdminRequests /></MemoryRouter></PermissionProvider>)
  expect(await screen.findByRole('columnheader', { name: 'Estado' })).toBeVisible()
  expect(screen.getByRole('option', { name: 'Cancelada' })).toBeInTheDocument()
  cleanup()
  stub(path => catalogs(path) ?? request)
  render(<PermissionProvider permissions={['admin_requests.create']}><MemoryRouter initialEntries={['/admin-requests/new']}><Routes><Route path="/admin-requests/new" element={<AdminRequestForm />} /></Routes></MemoryRouter></PermissionProvider>)
  fireEvent.change(await screen.findByLabelText('Inicio del período (opcional)'), { target: { value: '2026-11-25' } })
  fireEvent.change(screen.getByLabelText('Fin del período (opcional)'), { target: { value: '2026-11-20' } })
  expect(screen.getByRole('alert')).toHaveTextContent('El fin del período no puede ser anterior a su inicio.')
  expect(screen.getByRole('button', { name: 'Registrar solicitud' })).toBeDisabled()
})
