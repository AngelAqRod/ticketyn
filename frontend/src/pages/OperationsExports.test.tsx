import { fireEvent, render, screen, waitFor } from '../test/render'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { Operations } from './Operations'
import { operationExportUrl } from '../api/fms'
import { operationFilters } from '../lib/fmsFilters'
import type { FmsKind } from '../types/fms'
import { jsonResponse } from '../test/fixtures'
const kinds: FmsKind[] = ['activations', 'capacity-changes', 'circuit-lifecycle']

function setup(kind: FmsKind, search = '', mode?: 'error' | 'pending') {
  vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn(() => 'blob:operation'); static revokeObjectURL = vi.fn() })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const mock = vi.fn((path: string) => {
    if (path.includes('/export/')) {
      if (mode === 'pending') return new Promise<Response>(() => {})
      return Promise.resolve(mode === 'error' ? jsonResponse({ detail: 'No se pudo generar el archivo.' }, 500) : new Response(new Blob(['file'])))
    }
    return Promise.resolve(jsonResponse([]))
  })
  vi.stubGlobal('fetch', mock)
  render(<MemoryRouter initialEntries={[`/${kind}${search}`]}><Operations kind={kind} /></MemoryRouter>)
  return { mock, click }
}

describe('Exportaciones de los listados operativos FMS', () => {
  it.each(kinds.flatMap(kind => (['pdf', 'xlsx'] as const).map(format => [kind, format] as const)))('%s descarga %s desde la cabecera sin paginación', async (kind, format) => {
    const { mock, click } = setup(kind, '?offset=100')
    await screen.findByText('Sin operaciones registradas.')
    const heading = screen.getByRole('heading', { level: 1 }).closest('.page-heading')!
    expect(heading).toContainElement(screen.getByRole('button', { name: 'Exportar PDF' }))
    expect(heading).toContainElement(screen.getByRole('button', { name: 'Exportar Excel' }))
    expect(heading).toContainElement(screen.getByRole('button', { name: 'Nueva operación' }))
    fireEvent.click(screen.getByRole('button', { name: format === 'pdf' ? 'Exportar PDF' : 'Exportar Excel' }))
    await waitFor(() => expect(click).toHaveBeenCalledOnce())
    const path = mock.mock.calls.find(([path]) => path.includes(`/export/${format}`))![0]
    expect(Object.fromEntries(new URL(path, 'http://local').searchParams)).toEqual({ timezone: 'America/Guatemala' })
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:operation')
  })
  it.each(kinds)('%s exporta los mismos filtros efectivos que el listado', async kind => {
    const type = kind === 'capacity-changes' ? 'INCREASE' : kind === 'circuit-lifecycle' ? 'DEACTIVATE' : ''
    const { mock, click } = setup(kind, `?customer_id=8&period=custom&from=2026-10-01&to=2026-10-02&offset=100${type ? '&operation_type=' + type : ''}`)
    await screen.findByText('Sin operaciones registradas.')
    fireEvent.click(screen.getByRole('button', { name: 'Exportar Excel' }))
    await waitFor(() => expect(click).toHaveBeenCalled())
    const exported = new URL(mock.mock.calls.find(([path]) => path.includes('/export/xlsx'))![0], 'http://local').searchParams
    const listed = new URL(mock.mock.calls.find(([path]) => path.startsWith(`/api/${kind}?`))![0], 'http://local').searchParams
    for (const key of ['customer_id', 'from_at', 'to_at', 'operation_type']) expect(exported.get(key)).toBe(listed.get(key))
    expect(exported.get('from_at')).toBe('2026-10-01T06:00:00.000Z')
    expect(exported.get('to_at')).toBe('2026-10-03T06:00:00.000Z')
    expect(exported.has('limit')).toBe(false); expect(exported.has('offset')).toBe(false)
  })
  it.each(kinds)('%s impide descargas duplicadas y muestra progreso', async kind => {
    const { mock } = setup(kind, '', 'pending')
    await screen.findByText('Sin operaciones registradas.')
    const button = screen.getByRole('button', { name: 'Exportar PDF' })
    fireEvent.click(button); fireEvent.click(button)
    expect(await screen.findByText('Generando archivo...')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Exportar Excel' })).toBeDisabled()
    expect(mock.mock.calls.filter(([path]) => path.includes('/export/'))).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Nueva operación' })).toBeEnabled()
  })
  it.each(kinds)('%s informa errores sin abandonar el listado', async kind => {
    setup(kind, '', 'error'); await screen.findByText('Sin operaciones registradas.')
    fireEvent.click(screen.getByRole('button', { name: 'Exportar PDF' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo generar el archivo.')
    expect(screen.getByText('Sin operaciones registradas.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Exportar PDF' })).toBeEnabled()
  })
  it('deshabilita la exportación con período inválido', async () => {
    const { mock } = setup('activations', '?period=custom&from=2026-10-03&to=2026-10-01')
    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: 'Exportar PDF' })).toBeDisabled()
    expect(mock.mock.calls.some(([path]) => path.includes('/export/'))).toBe(false)
  })
  it('elimina paginación y conserva filtros API admitidos', () => {
    const url = operationExportUrl('activations', 'pdf', new URLSearchParams({ circuit_id: '3', limit: '50', offset: '100' }))
    expect(Object.fromEntries(new URL(url, 'http://local').searchParams)).toEqual({ circuit_id: '3', timezone: 'America/Guatemala' })
    expect(Object.fromEntries(operationFilters(new URLSearchParams({ period: 'all', customer_id: '1', offset: '50' })))).toEqual({ customer_id: '1' })
  })
})
