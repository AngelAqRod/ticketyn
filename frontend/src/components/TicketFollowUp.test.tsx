import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeAll, afterAll, afterEach, describe, expect, it, vi } from 'vitest'
import { TicketFollowUp } from './TicketFollowUp'
import { jsonResponse } from '../test/fixtures'
import { localDateTimeValue } from '../lib/datetime'
import type { TicketUpdate } from '../types/ticketUpdate'

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
const pageResponse = (items: TicketUpdate[], next_cursor: string | null = null) => jsonResponse({ items, next_cursor })
const entry: TicketUpdate = { id: 1, ticket_id: 27, content: 'Intervención histórica', occurred_at: '2010-01-01T12:00:00Z', created_at: '2026-10-07T12:00:00Z', visibility: 'INTERNAL', responsible_id: 2, responsible: { id: 2, name: 'Responsable histórico', active: false } }
const responsible = { id: 3, name: 'Operador activo', active: true, created_at: entry.created_at }
function mockApi(updates: TicketUpdate[] = [], save?: (body: Record<string, unknown>) => Promise<Response>) {
  const mock = vi.fn((path: string, options?: RequestInit) => {
    if (path.includes('/escalations?')) return Promise.resolve(jsonResponse([]))
    if (path.startsWith('/api/responsibles?')) return Promise.resolve(jsonResponse([responsible]))
    if (path.startsWith('/api/tickets/27/updates')) {
      if (options?.method === 'POST') {
        const body = JSON.parse(String(options.body))
        if (save) return save(body)
        const created = { ...entry, ...body, id: 9, responsible: body.responsible_id ? responsible : null } as TicketUpdate
        updates = [...updates, created].sort((a, b) => Date.parse(b.occurred_at) - Date.parse(a.occurred_at) || b.id - a.id)
        return Promise.resolve(jsonResponse(created))
      }
      return Promise.resolve(pageResponse(updates))
    }
    return Promise.resolve(jsonResponse({ detail: 'No encontrado' }, 404))
  })
  vi.stubGlobal('fetch', mock)
  return mock
}
async function open() {
  render(<TicketFollowUp ticketId={27} />)
  fireEvent.click(screen.getByRole('button', { name: 'Nueva intervención' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Registrar actualización' })).toBeEnabled())
}
const submit = () => fireEvent.submit(screen.getByRole('form', { name: 'Registrar actualización' }))
const content = () => screen.getByLabelText(/Descripción de la intervención/)
afterEach(() => vi.useRealTimers())

describe('seguimiento', () => {
  it('inicia con fecha y hora locales actuales y visibilidad interna, y muestra vacío', async () => {
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date(2026, 9, 7, 10, 20))
    mockApi(); await open()
    expect(screen.getByLabelText(/Fecha de intervención/)).toHaveValue('2026-10-07')
    expect(screen.getByLabelText(/Hora de intervención/)).toHaveValue('10:20')
    expect(screen.getByLabelText('Visibilidad')).toHaveValue('INTERNAL')
    expect(screen.getByRole('combobox', { name: 'Responsable de la intervención' })).toHaveValue('')
    expect(screen.getByText('Sin actualizaciones')).toBeInTheDocument()
  })
  it('muestra fecha de intervención y responsables históricos sin exponer created_at', async () => {
    mockApi([entry, { ...entry, id: 2, content: 'Contenido público', visibility: 'PUBLIC', responsible: null }]); await open()
    const history = screen.getByRole('list', { name: 'Historial de seguimiento' })
    expect(within(history).getByText('Responsable histórico')).toBeInTheDocument()
    expect(within(history).getByText('Sin asignar')).toBeInTheDocument()
    expect(within(history).getByText('Interna')).toBeInTheDocument()
    expect(within(history).getByText('Pública')).toBeInTheDocument()
    expect(history.querySelector('time')).toHaveAttribute('datetime', entry.occurred_at)
    expect(history.innerHTML).not.toContain(entry.created_at)
    expect(screen.queryByRole('button', { name: /eliminar/i })).not.toBeInTheDocument()
  })
  it('envía fechas retroactivas como UTC, conserva el responsable y no cambia el ticket', async () => {
    const mock = mockApi(); await open()
    fireEvent.change(content(), { target: { value: 'Trabajo retroactivo\nCompletado' } })
    fireEvent.change(screen.getByLabelText(/Fecha de intervención/), { target: { value: '2010-01-02' } })
    fireEvent.change(screen.getByLabelText(/Hora de intervención/), { target: { value: '09:45' } })
    fireEvent.change(screen.getByLabelText('Visibilidad'), { target: { value: 'PUBLIC' } })
    fireEvent.click(screen.getByRole('combobox', { name: 'Responsable de la intervención' }))
    fireEvent.click(screen.getByRole('option', { name: 'Operador activo' }))
    submit()
    expect(await screen.findByText('Actualización registrada correctamente.')).toBeInTheDocument()
    const calls = mock.mock.calls.filter(([, options]) => options?.method === 'POST')
    expect(calls).toHaveLength(1)
    expect(calls[0][0]).toBe('/api/tickets/27/updates')
    expect(JSON.parse(String(calls[0][1]?.body))).toEqual({ content: 'Trabajo retroactivo\nCompletado', occurred_at: new Date(2010, 0, 2, 9, 45).toISOString(), responsible_id: 3, visibility: 'PUBLIC' })
    expect(mock.mock.calls.some(([, options]) => options?.method === 'PATCH')).toBe(false)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
  it('reconsulta el orden canónico tras registrar una entrada retroactiva', async () => {
    mockApi([{ ...entry, id: 1, content: 'Posterior', occurred_at: '2020-01-01T00:00:00Z' }]); await open()
    fireEvent.change(content(), { target: { value: 'Anterior' } })
    fireEvent.change(screen.getByLabelText(/Fecha de intervención/), { target: { value: '2010-01-01' } })
    submit(); await screen.findByText('Actualización registrada correctamente.')
    const history = await screen.findByRole('list', { name: 'Historial de seguimiento' })
    expect(within(history).getAllByRole('listitem')[0]).toHaveTextContent('Posterior')
  })
  it('valida contenido y fecha sin enviar solicitudes y asocia errores', async () => {
    const mock = mockApi(); await open(); submit()
    expect(screen.getByRole('alert')).toHaveTextContent('Escribe la descripción')
    expect(content()).toHaveAttribute('aria-invalid', 'true')
    expect(content()).toHaveAttribute('aria-describedby', 'follow-up-27-error')
    fireEvent.change(content(), { target: { value: 'x' } })
    fireEvent.change(screen.getByLabelText(/Fecha de intervención/), { target: { value: '' } })
    submit()
    expect(screen.getByLabelText(/Fecha de intervención/)).toHaveAttribute('aria-invalid', 'true')
    expect(mock.mock.calls.some(([, options]) => options?.method === 'POST')).toBe(false)
  })
  it('evita doble envío y conserva el contenido ante fallo', async () => {
    let finish!: (response: Response) => void
    const pending = new Promise<Response>((resolve) => { finish = resolve })
    const mock = mockApi([], () => pending); await open()
    fireEvent.change(content(), { target: { value: 'No perder' } })
    submit(); submit()
    expect(screen.getByRole('button', { name: 'Registrando...' })).toBeDisabled()
    expect(mock.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1)
    await act(async () => finish(jsonResponse({ detail: 'Error al registrar' }, 500)))
    expect(await screen.findByRole('alert')).toHaveTextContent('Error al registrar')
    expect(content()).toHaveValue('No perder')
    expect(screen.getByRole('button', { name: 'Registrar actualización' })).toBeEnabled()
  })
  it('muestra loading y permite reintentar el historial sin perder formulario', async () => {
    const mock = mockApi()
    const normal = mock.getMockImplementation()!
    let fail = true
    mock.mockImplementation((path, options) => path.startsWith('/api/tickets/27/updates') && fail ? Promise.resolve(jsonResponse({ detail: 'Historial no disponible' }, 503)) : normal(path, options))
    render(<TicketFollowUp ticketId={27} />)
    expect(screen.getByText('Cargando seguimiento...')).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toHaveTextContent('Historial no disponible')
    fireEvent.click(screen.getByRole('button', { name: 'Nueva intervención' }))
    fireEvent.change(content(), { target: { value: 'Conservar borrador' } })
    fail = false; fireEvent.click(screen.getByRole('button', { name: 'Reintentar seguimiento' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Registrar actualización' })).toBeEnabled())
    expect(content()).toHaveValue('Conservar borrador')
  })
  it('permite reintentar responsables sin bloquear la lectura del historial', async () => {
    const mock = mockApi([entry]); const normal = mock.getMockImplementation()!
    let fail = true
    mock.mockImplementation((path, options) => path.startsWith('/api/responsibles?') && fail ? Promise.resolve(jsonResponse({ detail: 'Responsables no disponibles' }, 503)) : normal(path, options))
    render(<TicketFollowUp ticketId={27} />)
    fireEvent.click(screen.getByRole('button', { name: 'Nueva intervención' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Responsables no disponibles')
    expect(screen.getByText(entry.content)).toBeInTheDocument()
    fail = false; fireEvent.click(screen.getByRole('button', { name: 'Reintentar responsables' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Registrar actualización' })).toBeEnabled())
  })
  it('limpia las solicitudes al desmontar y conserva fecha actual como instante local', async () => {
    const mock = mockApi(); const rendered = render(<TicketFollowUp ticketId={27} />)
    fireEvent.click(screen.getByRole('button', { name: 'Nueva intervención' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Registrar actualización' })).toBeEnabled())
    expect(screen.getByLabelText(/Fecha de intervención/)).toHaveValue(localDateTimeValue().split('T')[0])
    const signals = mock.mock.calls.map(([, options]) => options?.signal).filter(Boolean)
    rendered.unmount()
    expect(signals.every((signal) => signal?.aborted)).toBe(true)
  })
  it('respeta el orden del servidor incluso en empates de milisegundos', async () => {
    let posted = false
    const later = { ...entry, content: 'Microsegundo posterior', occurred_at: '2026-10-07T10:00:00.000001Z' }
    const earlier = { ...entry, id: 9, content: 'Instante anterior', occurred_at: '2026-10-07T10:00:00.000000Z' }
    vi.stubGlobal('fetch', vi.fn((path: string, options?: RequestInit) => {
      if (path.includes('/escalations?')) return Promise.resolve(jsonResponse([]))
    if (path.startsWith('/api/responsibles?')) return Promise.resolve(jsonResponse([]))
      if (options?.method === 'POST') { posted = true; return Promise.resolve(jsonResponse(earlier)) }
      return Promise.resolve(pageResponse(posted ? [later, earlier] : [later]))
    }))
    await open()
    fireEvent.change(content(), { target: { value: earlier.content } }); submit()
    await screen.findByText('Actualización registrada correctamente.')
    const history = await screen.findByRole('list', { name: 'Historial de seguimiento' })
    expect(within(history).getAllByRole('listitem')[0]).toHaveTextContent(later.content)
  })
  it('un GET fallido después del POST no convierte un registro confirmado en error de guardado', async () => {
    let gets = 0
    const mock = vi.fn((path: string, options?: RequestInit) => {
      if (path.includes('/escalations?')) return Promise.resolve(jsonResponse([]))
    if (path.startsWith('/api/responsibles?')) return Promise.resolve(jsonResponse([]))
      if (options?.method === 'POST') return Promise.resolve(jsonResponse(entry))
      gets += 1
      return Promise.resolve(gets === 2 ? jsonResponse({ detail: 'Recarga no disponible' }, 503) : pageResponse(gets === 1 ? [] : [entry]))
    })
    vi.stubGlobal('fetch', mock); await open()
    fireEvent.change(content(), { target: { value: 'Registrada' } }); submit()
    expect(await screen.findByText('Actualización registrada correctamente.')).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toHaveTextContent('Recarga no disponible')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar seguimiento' }))
    await screen.findByText(entry.content)
    expect(mock.mock.calls.filter(([, options]) => options?.method === 'POST')).toHaveLength(1)
  })

})


describe('modal y páginas de seguimiento', () => {
  it('no muestra un formulario permanente; enfoca descripción y devuelve foco al cancelar o Escape', async () => {
    mockApi()
    render(<TicketFollowUp ticketId={27} />)
    const trigger = screen.getByRole('button', { name: 'Nueva intervención' })
    expect(screen.queryByRole('form')).not.toBeInTheDocument()
    trigger.focus(); fireEvent.click(trigger)
    expect(screen.getByRole('dialog', { name: 'Nueva intervención' })).toHaveAttribute('open')
    expect(content()).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(trigger).toHaveFocus()
    fireEvent.click(trigger)
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { bubbles: false, cancelable: true }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('conserva el modal durante envío y restaura el foco después del éxito', async () => {
    let finish!: (response: Response) => void
    mockApi([], () => new Promise<Response>((resolve) => { finish = resolve }))
    render(<TicketFollowUp ticketId={27} />)
    const trigger = screen.getByRole('button', { name: 'Nueva intervención' })
    trigger.focus(); fireEvent.click(trigger)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Registrar actualización' })).toBeEnabled())
    fireEvent.change(content(), { target: { value: 'Guardando' } }); submit()
    fireEvent(screen.getByRole('dialog'), new Event('cancel', { cancelable: true }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeDisabled()
    await act(async () => finish(jsonResponse(entry)))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('carga diez por página, conserva registros ante fallo y reintenta el mismo cursor sin duplicados', async () => {
    const first = Array.from({ length: 10 }, (_, i) => ({ ...entry, id: 30 - i, content: `Entrada ${30 - i}` }))
    const second = Array.from({ length: 10 }, (_, i) => ({ ...entry, id: 20 - i, content: `Entrada ${20 - i}` }))
    let fail = true
    const mock = vi.fn((path: string) => {
      const query = new URL(path, 'http://test').searchParams
      expect(query.get('limit')).toBe('10')
      if (query.get('cursor')) return Promise.resolve(fail ? jsonResponse({ detail: 'Página no disponible' }, 503) : pageResponse(second))
      return Promise.resolve(pageResponse(first, 'opaque/+='))
    })
    vi.stubGlobal('fetch', mock)
    render(<TicketFollowUp ticketId={27} />)
    await screen.findByText('Entrada 30')
    expect(screen.getAllByRole('listitem')).toHaveLength(10)
    fireEvent.click(screen.getByRole('button', { name: 'Cargar más' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Página no disponible')
    expect(screen.getAllByRole('listitem')).toHaveLength(10)
    fail = false; fireEvent.click(screen.getByRole('button', { name: 'Reintentar más intervenciones' }))
    await screen.findByText('Entrada 11')
    expect(screen.getAllByRole('listitem')).toHaveLength(20)
    expect(screen.queryByRole('button', { name: 'Cargar más' })).not.toBeInTheDocument()
    expect(mock.mock.calls[1][0]).toBe(mock.mock.calls[2][0])
    expect(new URL(mock.mock.calls[2][0], 'http://test').searchParams.get('cursor')).toBe('opaque/+=')
  })

  it('al registrar reinicia la paginación y mantiene textos extensos con saltos de línea', async () => {
    let posted = false
    const long = 'Texto'.repeat(400) + '\nSegunda línea'
    const mock = vi.fn((path: string, options?: RequestInit) => {
      if (path.includes('/escalations?')) return Promise.resolve(jsonResponse([]))
      if (path.startsWith('/api/responsibles')) return Promise.resolve(jsonResponse([]))
      if (options?.method === 'POST') { posted = true; return Promise.resolve(jsonResponse(entry)) }
      if (path.includes('cursor=')) return Promise.resolve(pageResponse([{ ...entry, id: 2, content: 'Antigua página' }]))
      return Promise.resolve(pageResponse([{ ...entry, content: long }], posted ? null : 'next'))
    })
    vi.stubGlobal('fetch', mock)
    render(<TicketFollowUp ticketId={27} />)
    await screen.findByRole('list')
    expect(screen.getByRole('listitem').querySelector('p')).toHaveClass('whitespace-pre-wrap', '[overflow-wrap:anywhere]')
    expect(screen.getByRole('listitem').textContent).toContain(long)
    fireEvent.click(screen.getByRole('button', { name: 'Cargar más' }))
    await screen.findByText('Antigua página')
    fireEvent.click(screen.getByRole('button', { name: 'Nueva intervención' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Registrar actualización' })).toBeEnabled())
    fireEvent.change(content(), { target: { value: 'Nueva' } }); submit()
    await screen.findByText('Actualización registrada correctamente.')
    await waitFor(() => expect(screen.queryByText('Antigua página')).not.toBeInTheDocument())
    const lastGet = mock.mock.calls.filter(([, options]) => !options?.method).at(-1)!
    expect(lastGet[0]).toBe('/api/tickets/27/updates?limit=10')
  })
})


it('Escape cierra primero el selector abierto y después el modal, conservando la navegación por teclado', async () => {
  mockApi(); await open()
  const selector = screen.getByRole('combobox', { name: 'Responsable de la intervención' })
  selector.focus()
  fireEvent.keyDown(selector, { key: 'ArrowDown' })
  expect(selector).toHaveAttribute('aria-expanded', 'true')
  fireEvent.keyDown(selector, { key: 'Enter' })
  expect(selector).toHaveValue('Operador activo')
  fireEvent.keyDown(selector, { key: 'ArrowDown' })
  fireEvent.keyDown(selector, { key: 'Escape' })
  expect(selector).toHaveAttribute('aria-expanded', 'false')
  expect(screen.getByRole('dialog')).toBeInTheDocument()
  fireEvent.keyDown(selector, { key: 'Escape' })
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})
