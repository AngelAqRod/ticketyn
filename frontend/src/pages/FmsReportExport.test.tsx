import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, it, expect, vi } from 'vitest'
import { FmsReports } from './FmsReports'
import { jsonResponse } from '../test/fixtures'
import type { FmsKind } from '../types/fms'
vi.mock('../components/ReportCharts', () => ({ TrendChart: () => <div />, ActivityChart: () => <div />, DistributionChart: () => <div />, RankingChart: () => <div /> }))
function setup(kind: FmsKind, view = 'general', mode = '', selected = true) {
  vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn(() => 'blob:report'); static revokeObjectURL = vi.fn() })
  const downloads: string[] = []
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function(this: HTMLAnchorElement) { downloads.push(this.download) })
  const field = view === 'sector' ? 'sector_id' : view === 'node' ? 'node_id' : 'responsible_id'
  const mock = vi.fn((path: string) => {
    if (path.includes('/export/pdf')) return mode === 'pending' ? new Promise<Response>(() => {}) : Promise.resolve(mode === 'error' ? jsonResponse({ detail: 'Reduce el período.' }, 413) : new Response(new Blob(['%PDF'])))
    if (path.includes('/summary')) return Promise.resolve(jsonResponse({ generated_at: '2020-01-01T18:00:00Z', period: { granularity: 'day' }, kpis: { total: 0, increases: 0, decreases: 0, deactivations: 0, reactivations: 0, known_added_mbps: '0', known_reduced_mbps: '0', known_net_mbps: '0' }, trend: [], customers: [], reasons: [], sector: { name: 'Elemento' }, node: { name: 'Elemento' }, responsible: { name: 'Elemento' } }))
    if (path.includes('/details')) return Promise.resolve(jsonResponse([]))
    return Promise.resolve(jsonResponse([{ id: 1, name: 'Elemento', active: false }]))
  })
  vi.stubGlobal('fetch', mock)
  render(<MemoryRouter initialEntries={[`/test?view=${view}&period=custom&from=2020-01-01&to=2020-01-02&offset=50${view !== 'general' && selected ? `&${field}=1` : ''}`]}><FmsReports kind={kind} /></MemoryRouter>)
  return { mock, downloads }
}
const kinds: FmsKind[] = ['activations', 'capacity-changes', 'circuit-lifecycle']
describe('PDF estadístico FMS', () => {
  it.each(kinds.flatMap((kind) => ['general', 'sector', 'node', 'responsible'].map((view) => [kind, view] as const)))('%s exporta la vista %s con los mismos filtros', async (kind, view) => {
    const { mock, downloads } = setup(kind, view)
    const button = screen.getByRole('button', { name: 'Exportar PDF' })
    expect(button).toHaveClass('button-secondary')
    expect(screen.getByRole('heading', { level: 1 }).closest('.page-heading')).toContainElement(button)
    await waitFor(() => expect(button).toBeEnabled())
    fireEvent.click(button)
    await waitFor(() => expect(downloads).toEqual([`ticketyn-analisis-${kind}-${view === 'node' ? 'nodo' : view === 'responsible' ? 'responsable' : view}.pdf`]))
    const exported = new URL(mock.mock.calls.find(([path]) => path.includes('/export/pdf'))![0], 'http://local')
    const summary = new URL(mock.mock.calls.find(([path]) => path.includes('/summary'))![0], 'http://local')
    expect(exported.search).toBe(summary.search)
    expect(exported.searchParams.get('from')).toBe('2020-01-01T06:00:00.000Z')
    expect(exported.searchParams.get('to')).toBe('2020-01-03T06:00:00.000Z')
    expect(exported.searchParams.has('offset')).toBe(false)
    expect(exported.searchParams.has('limit')).toBe(false)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:report')
  })
  it.each(['sector', 'node', 'responsible'])('no exporta %s sin selección', async (view) => {
    const { mock } = setup('activations', view, '', false)
    expect(screen.getByRole('button', { name: 'Exportar PDF' })).toBeDisabled()
    await screen.findByText(/Selecciona un/)
    expect(mock.mock.calls.some(([path]) => path.includes('/export/pdf'))).toBe(false)
  })
  it('muestra progreso y evita solicitudes duplicadas', async () => {
    const { mock } = setup('activations', 'general', 'pending')
    const button = screen.getByRole('button', { name: 'Exportar PDF' })
    await waitFor(() => expect(button).toBeEnabled())
    fireEvent.click(button); fireEvent.click(button)
    expect(button).toBeDisabled()
    expect(screen.getAllByText('Generando PDF...').length).toBeGreaterThan(0)
    expect(mock.mock.calls.filter(([path]) => path.includes('/export/pdf'))).toHaveLength(1)
  })
  it('muestra el error conservando reporte y filtros', async () => {
    setup('activations', 'general', 'error')
    const button = screen.getByRole('button', { name: 'Exportar PDF' })
    await waitFor(() => expect(button).toBeEnabled())
    fireEvent.click(button)
    expect(await screen.findByRole('alert')).toHaveTextContent('Reduce el período.')
    expect(screen.getByText('Reporte General')).toBeInTheDocument()
    expect(screen.getByLabelText('Desde')).toHaveValue('2020-01-01')
    expect(button).toBeEnabled()
  })
})
