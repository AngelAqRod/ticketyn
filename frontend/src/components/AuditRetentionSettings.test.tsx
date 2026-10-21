import { fireEvent, render, screen, waitFor } from '../test/render'
import { afterEach, expect, it, vi } from 'vitest'
import { AuditRetentionSettings } from './AuditRetentionSettings'
import { PermissionProvider } from '../auth/permissions'

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
function show(permissions = ['audit.view', 'security.configure'], onSaved = vi.fn()) {
  return render(<PermissionProvider permissions={permissions}><AuditRetentionSettings onSaved={onSaved} /></PermissionProvider>)
}
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

it('consulta el valor persistido y guarda sin limpiar ni cambiar otras políticas', async () => {
  const onSaved = vi.fn(), fetcher = vi.fn((_url: string, options?: RequestInit) => Promise.resolve(json({ retention_days: options?.method === 'PATCH' ? 730 : 365 })))
  vi.stubGlobal('fetch', fetcher); show(undefined, onSaved)
  const input = await screen.findByLabelText('Días de conservación')
  await waitFor(() => expect(input).toHaveValue(365))
  expect(input).toHaveAttribute('min', '1'); expect(input).toHaveAttribute('max', '3650')
  fireEvent.change(input, { target: { value: '730' } })
  fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Conservación guardada')
  expect(input).toHaveValue(730)
  expect(JSON.parse(fetcher.mock.calls[1][1]?.body as string)).toEqual({ retention_days: 730, expected_days: 365, confirm_reduction: false })
  expect(fetcher.mock.calls.every(([url]) => url === '/api/security/audit/retention')).toBe(true)
  expect(onSaved).toHaveBeenCalledTimes(1)
})

it('oculta el control sin el permiso exclusivo, incluso con audit.view', () => {
  const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher)
  show(['audit.view'])
  expect(screen.queryByText('Conservación de registros')).not.toBeInTheDocument()
  expect(fetcher).not.toHaveBeenCalled()
})

it('valida el rango y exige confirmación al reducir días, sin borrar en la petición', async () => {
  const fetcher = vi.fn((_url: string, options?: RequestInit) => Promise.resolve(json({ retention_days: options?.method === 'PATCH' ? 30 : 365 })))
  vi.stubGlobal('fetch', fetcher); show()
  const input = await screen.findByLabelText('Días de conservación')
  await waitFor(() => expect(input).toHaveValue(365))
  for (const value of ['0', '3651', '1.5', '']) {
    fireEvent.change(input, { target: { value } })
    fireEvent.submit(screen.getByRole('button', { name: 'Guardar' }).closest('form')!)
    expect(screen.getByRole('alert')).toHaveTextContent('entre 1 y 3650')
  }
  fireEvent.change(input, { target: { value: '30' } })
  fireEvent.submit(screen.getByRole('button', { name: 'Guardar' }).closest('form')!)
  expect(screen.getByRole('alert')).toHaveTextContent('Confirma la reducción')
  expect(fetcher).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
  expect(await screen.findByRole('status')).toHaveTextContent('próxima limpieza automática')
  expect(JSON.parse(fetcher.mock.calls[1][1]?.body as string).confirm_reduction).toBe(true)
})

it('rechaza doble clic y muestra progreso mientras se guarda', async () => {
  let finish!: (response: Response) => void
  const fetcher = vi.fn((_url: string, options?: RequestInit) => options?.method === 'PATCH'
    ? new Promise<Response>(resolve => { finish = resolve }) : Promise.resolve(json({ retention_days: 365 })))
  vi.stubGlobal('fetch', fetcher); show()
  const input = await screen.findByLabelText('Días de conservación')
  await waitFor(() => expect(input).toHaveValue(365))
  fireEvent.change(input, { target: { value: '400' } })
  const button = screen.getByRole('button', { name: 'Guardar' })
  fireEvent.click(button); fireEvent.click(button)
  expect(screen.getByRole('button', { name: 'Guardando…' })).toBeDisabled()
  expect(fetcher).toHaveBeenCalledTimes(2)
  finish(json({ retention_days: 400 }))
  expect(await screen.findByRole('status')).toHaveTextContent('Conservación guardada')
})

it('muestra errores, maneja el conflicto de revisión y permite volver a consultar', async () => {
  let current = 365
  const fetcher = vi.fn((_url: string, options?: RequestInit) => {
    if (options?.method === 'PATCH') { current = 100; return Promise.resolve(json({ detail: 'La conservación cambió. Actualiza el valor antes de guardar' }, 409)) }
    return Promise.resolve(json({ retention_days: current }))
  })
  vi.stubGlobal('fetch', fetcher); show()
  const input = await screen.findByLabelText('Días de conservación')
  await waitFor(() => expect(input).toHaveValue(365))
  fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('La conservación cambió')
  expect(screen.getByRole('button', { name: 'Guardar' })).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Actualizar conservación' }))
  await waitFor(() => expect(screen.getByLabelText('Días de conservación')).toHaveValue(100))
})

it('retira el formulario si se revoca el permiso y cancela peticiones anteriores', async () => {
  const fetcher = vi.fn(() => Promise.resolve(json({ retention_days: 365 })))
  vi.stubGlobal('fetch', fetcher)
  const view = show()
  await waitFor(() => expect(screen.getByLabelText('Días de conservación')).toHaveValue(365))
  view.rerender(<PermissionProvider permissions={['audit.view']}><AuditRetentionSettings onSaved={vi.fn()} /></PermissionProvider>)
  expect(screen.queryByLabelText('Días de conservación')).not.toBeInTheDocument()
  expect(fetcher).toHaveBeenCalledTimes(1)
})
