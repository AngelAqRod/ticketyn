import { fireEvent, render, screen, waitFor, within } from '../test/render'
import { MemoryRouter } from 'react-router'
import { describe, it, expect, vi } from 'vitest'
// Authentication is exercised in auth/AuthGate.test.tsx; these tests isolate operational routing.
vi.mock('../auth/AuthGate', () => ({ AuthGate: ({ children }: { children: React.ReactNode }) => children }))

import App from '../App'
import { FmsReports, fmsReportTitles } from './FmsReports'
import { jsonResponse } from '../test/fixtures'
import type { FmsKind } from '../types/fms'
vi.mock('../components/ReportCharts', () => ({
  TrendChart: ({ title }: { title: string }) => <div role="img" aria-label={title} />,
  ActivityChart: ({ title, firstLabel, secondLabel }: { title: string; firstLabel: string; secondLabel: string }) => <div role="img" aria-label={title}>{firstLabel} / {secondLabel}</div>,
  DistributionChart: ({ title }: { title: string }) => <div role="img" aria-label={title} />,
  RankingChart: ({ title }: { title: string }) => <div role="img" aria-label={title} />,
}))
const kinds: FmsKind[] = ['activations', 'capacity-changes', 'circuit-lifecycle']
function setup(kind: FmsKind, search = '', fail = false) {
  const mock = vi.fn((path: string) => {
    const url = new URL(path, 'http://local')
    if (url.pathname.endsWith('/summary')) return Promise.resolve(jsonResponse(fail ? { detail: 'No disponible' } : {
      generated_at: '2026-10-13T18:00:00Z', period: { granularity: 'day' }, sector: url.searchParams.has('sector_id') ? { id: 1, name: 'Sector histórico' } : null, node: url.searchParams.has('node_id') ? { id: 1, name: 'Nodo histórico' } : null, responsible: url.searchParams.has('responsible_id') ? { id: 1, name: 'Operador' } : null,
      kpis: { total: 3, distinct_customers: 1, distinct_circuits: 2, increases: 2, decreases: 1, known_added_mbps: '1500', known_reduced_mbps: '2000', known_net_mbps: '-500', unknown_variations: 1, deactivations: 2, reactivations: 1, distinct_deactivated_circuits: 1, distinct_reactivated_circuits: 1 },
      trend: [{ start_at: '2026-10-13T06:00:00Z', count: 3, first: 2, second: 1 }], customers: [{ id: 1, label: 'Cliente', count: 2 }], reasons: [{ id: 1, label: 'Solicitud', count: 2 }],
    }, fail ? 503 : 200))
    if (url.pathname.endsWith('/details')) return Promise.resolve(jsonResponse([]))
    return Promise.resolve(jsonResponse([{ id: 1, name: url.pathname.includes('nodes') ? 'Nodo histórico' : url.pathname.includes('responsibles') ? 'Operador' : 'Sector histórico', active: false }]))
  })
  vi.stubGlobal('fetch', mock)
  render(<MemoryRouter initialEntries={[`/test${search}`]}><FmsReports kind={kind} /></MemoryRouter>)
  return mock
}
async function loaded() { await screen.findByText('Reporte General', { exact: true }) }
describe('reporterías FMS homogéneas', () => {
  it.each(kinds)('%s reutiliza filtros de Tickets y cuatro vistas', async (kind) => {
    setup(kind); await loaded()
    expect(screen.getByRole('heading', { name: fmsReportTitles[kind], level: 1 })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Filtros de reportería FMS' })).toHaveClass('filter-toolbar')
    const periods = screen.getByRole('group', { name: 'Período del reporte' })
    expect(periods).toHaveClass('segmented-control', 'flex-wrap')
    for (const name of ['Todos', 'Hoy', 'Ayer', '7D', '15D', '30D', 'Personalizado']) expect(within(periods).getByRole('button', { name })).toHaveClass('segment-button')
    expect(within(periods).getByRole('button', { name: 'Todos' })).toHaveAttribute('aria-pressed', 'true')
    for (const name of ['General', 'Por Sector', 'Por Nodo', 'Por Responsable']) expect(screen.getByRole('button', { name })).toBeInTheDocument()
  })
  it.each(kinds)('%s exige selección individual y actualiza todo el reporte', async (kind) => {
    const mock = setup(kind); await loaded()
    for (const [tab, field, label, option] of [['Por Sector', 'sector_id', 'Sector', 'Sector histórico'], ['Por Nodo', 'node_id', 'Nodo', 'Nodo histórico'], ['Por Responsable', 'responsible_id', 'Responsable', 'Operador']]) {
      fireEvent.click(screen.getByRole('button', { name: tab }))
      await screen.findByText(`Selecciona un ${label.toLowerCase()} para consultar el reporte.`)
      const input = screen.getByRole('combobox', { name: label })
      fireEvent.focus(input)
      fireEvent.click(await screen.findByRole('option', { name: option }))
      await waitFor(() => expect(mock.mock.calls.some(([url]) => url.includes('/summary?') && url.includes(`${field}=1`))).toBe(true))
      await waitFor(() => expect(mock.mock.calls.some(([url]) => url.includes('/details?') && url.includes(`${field}=1`))).toBe(true))
      expect(screen.queryByRole('region', { name: 'Clientes con más circuitos distintos activados' })).not.toBeInTheDocument()
    }
  })
  it('Hoy/Ayer y rangos personalizados actualizan summary y details en Guatemala', async () => {
    vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-13T18:00:00Z'))
    const mock = setup('activations'); await loaded()
    for (const [name, from, to] of [['Hoy', '2026-10-13T06:00:00.000Z', '2026-10-14T06:00:00.000Z'], ['Ayer', '2026-10-12T06:00:00.000Z', '2026-10-13T06:00:00.000Z']]) {
      fireEvent.click(screen.getByRole('button', { name }))
      await waitFor(() => expect(mock.mock.calls.some(([path]) => { const q = new URL(path, 'http://local').searchParams; return q.get('from') === from && q.get('to') === to && q.get('granularity') === 'auto' })).toBe(true))
    }
    fireEvent.click(screen.getByRole('button', { name: 'Personalizado' }))
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-10-01' } })
    fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2026-10-10' } })
    await waitFor(() => expect(mock.mock.calls.some(([path]) => { const q = new URL(path, 'http://local').searchParams; return q.get('from') === '2026-10-01T06:00:00.000Z' && q.get('to') === '2026-10-11T06:00:00.000Z' })).toBe(true))
    vi.useRealTimers()
  })
  it('muestra variaciones conocidas con formato compartido y neta negativa', async () => {
    setup('capacity-changes'); await loaded()
    expect(screen.getByText('Capacidad agregada conocida').parentElement).toHaveTextContent('1.5 Gbps')
    expect(screen.getByText('Variación neta conocida').parentElement).toHaveTextContent('−500 Mbps')
    expect(screen.getByText(/1 operaciones sin capacidad anterior/)).toBeInTheDocument()
  })
  it('Análisis ofrece las cuatro rutas independientes', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ status: 'ok' }))))
    render(<MemoryRouter initialEntries={["/pagina-inexistente"]}><App /></MemoryRouter>)
    const navigation = screen.getByRole('navigation', { name: 'Navegación principal' })
    for (const [name, href] of [['Reportería de tickets', '/reports'], ['Reportería de activaciones', '/activation-reports'], ['Reportería de cambios de capacidad', '/capacity-reports'], ['Reportería de bajas y reactivaciones', '/lifecycle-reports']]) {
      expect(within(navigation).getByRole('link', { name })).toHaveAttribute('href', href)
    }
    await screen.findByText('API conectada')
  })
  it('errores son recuperables', async () => {
    setup('activations', '', true)
    expect(await screen.findByRole('alert')).toHaveTextContent('No disponible')
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
  })
})
