import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation, useNavigate } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { Reports } from './Reports'
import App from '../App'
import { jsonResponse, ticket } from '../test/fixtures'
import type { ReportSummary, ReportQuery } from '../types/report'
import { reportExportUrl } from '../api/reports'

vi.mock('../components/ReportCharts', () => ({
  ActivityChart: () => <div role="img" aria-label="Gráfica iniciadas vs cerradas" />,
  DistributionChart: ({ title, rows }: { title: string; rows: { label: string; count: number }[] }) => <div role="img" aria-label={`Gráfica ${title}`} data-values={JSON.stringify(rows)} />,
  TrendChart: ({ trend, granularity, title = 'Evolución de incidencias' }: { trend: ReportSummary['trend']; granularity: string; title?: string }) => <div role="img" aria-label={`Gráfica de ${title.toLocaleLowerCase()}`}>{granularity}: {trend.length} buckets</div>,
  RankingChart: ({ title }: { title: string }) => <div role="img" aria-label={`Gráfica ${title}`} />,
}))
const report: ReportSummary = {
  escalations: { total_tickets: 123, escalated_tickets: 2, events: 3, active: 1, finished: 2, average_duration_seconds: 3600, escalated_percentage: 2 / 123 * 100, granularity: 'day', trend: [], recipients: [] },
  period: { from_at: '2026-10-01T00:00:00Z', to_exclusive: '2026-10-03T00:00:00Z', timezone: 'UTC', granularity: 'day' },
  generated_at: '2026-10-02T12:00:00Z', sector: null,
  kpis: { started: 123, closed: 12, average_duration_seconds: 3600, total_duration_seconds: 86400 },
  trend: [{ start_at: '2026-10-01T00:00:00Z', count: 123 }, { start_at: '2026-10-02T00:00:00Z', count: 0 }],
  nodes: [{ id: 5, label: 'Nodo Central', count: 123, customer_id: null, customer_code: null, customer_name: null }],
  responsibles: [{ id: 6, label: 'Operador asignado', count: 123, customer_id: null, customer_code: null, customer_name: null }],
  activity: [{ start_at: '2026-10-01T00:00:00Z', started: 123, closed: 12 }],
  departments: [{ id: 7, label: 'Departamento histórico', count: 123, customer_id: null, customer_code: null, customer_name: null }],
  department_durations: [{ id: 7, label: 'Departamento histórico', count: 2, average_duration_seconds: 5400 }],
  hours: [], weekdays: [], sector_durations: [],
  sectors: [{ id: 1, label: 'Sector histórico', count: 123, customer_id: null, customer_code: null, customer_name: null }],
  customers: [{ id: 2, label: 'C-2 — Cliente', count: 123, customer_id: null, customer_code: null, customer_name: null }],
  circuits: [{ id: 3, label: 'C-2.003', count: 123, customer_id: 2, customer_code: 'C-2', customer_name: 'Cliente' }],
  incident_types: [{ id: 4, label: 'Incidencia', count: 123, customer_id: null, customer_code: null, customer_name: null }],
}
function Location() { const location = useLocation(); const navigate = useNavigate(); return <><output data-testid="url">{location.pathname}{location.search}</output><button onClick={() => navigate(-1)}>Atrás</button><button onClick={() => navigate(1)}>Adelante</button></> }
function setup(path = '/reports?period=custom&from=2026-10-01&to=2026-10-02', options: { fail?: boolean; empty?: boolean; pending?: boolean; fullPage?: boolean; app?: boolean; exportFail?: boolean; pendingExport?: boolean } = {}) {
  const mock = vi.fn((path: string) => {
    const address = new URL(path, 'http://local')
    if (address.pathname === '/api/escalations/summary') return Promise.resolve(jsonResponse({ total_tickets: 0, escalated_tickets: 0, events: 0, active: 0, finished: 0, average_duration_seconds: null, escalated_percentage: 0, granularity: 'day', trend: [], recipients: [] }))
    if (address.pathname === '/api/escalations/tickets') return Promise.resolve(jsonResponse([]))
    if (address.pathname === '/health') return Promise.resolve(jsonResponse({ status: 'ok' }))
    if (address.pathname.startsWith('/api/reports/export')) {
      if (options.pendingExport) return new Promise<Response>(() => {})
      if (options.exportFail) return Promise.resolve(jsonResponse({ detail: [{ loc: ['query', 'from'], msg: 'Rango inválido' }] }, 422))
      return Promise.resolve(new Response(new Blob(['file'])))
    }
    if (address.pathname === '/api/nodes') return Promise.resolve(jsonResponse([{ id: 5, name: 'Nodo Central', active: false, created_at: ticket.created_at }]))
    if (address.pathname === '/api/responsibles') return Promise.resolve(jsonResponse([{ id: 6, name: 'Operador asignado', active: false, created_at: ticket.created_at }]))
    if (address.pathname === '/api/sectors') return Promise.resolve(jsonResponse([{ id: 1, name: 'Sector histórico', active: false, created_at: ticket.created_at }]))
    if (address.pathname === '/api/reports/summary') {
      if (options.pending) return new Promise<Response>(() => {})
      if (options.fail) return Promise.resolve(jsonResponse({ detail: 'No disponible' }, 503))
      const sector = address.searchParams.get('sector_id')
      const node = address.searchParams.get('node_id'), responsible = address.searchParams.get('responsible_id')
      return Promise.resolve(jsonResponse({ ...report, node: node ? { id: Number(node), name: 'Nodo Central' } : null, responsible: responsible ? { id: Number(responsible), name: 'Operador asignado' } : null, nodes: node || options.empty ? [] : report.nodes, responsibles: responsible || options.empty ? [] : report.responsibles, ...(options.empty ? { kpis: { started: 0, closed: 0, average_duration_seconds: null, total_duration_seconds: 0 }, customers: [], circuits: [], sectors: [], incident_types: [] } : {}), sector: sector ? { id: Number(sector), name: 'Sector histórico' } : null, sectors: sector || options.empty ? [] : report.sectors }))
    }
    if (address.pathname === '/api/tickets') return Promise.resolve(jsonResponse(options.empty ? [] : Array.from({ length: options.fullPage ? 50 : 1 }, (_, id) => ({ ...ticket, id: id + 1, reference: `T-${id}` }))))
    return Promise.resolve(jsonResponse([]))
  })
  vi.stubGlobal('fetch', mock)
  render(<MemoryRouter initialEntries={[path]}>{options.app ? <App /> : <Reports />}<Location /></MemoryRouter>)
  return mock
}
async function loaded() { await screen.findByText('Reporte General', { exact: true }) }

describe('reportería operativa', () => {
  it('renderiza General, KPIs globales, evolución, rankings y tabla', async () => {
    setup(); await loaded()
    const kpis = screen.getByText('Incidencias iniciadas').parentElement!
    expect(within(kpis).getByText('123')).toBeInTheDocument()
    expect(screen.getByText('Duración promedio').parentElement).toHaveTextContent('1 h')
    expect(screen.getByText('1 d')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Gráfica de evolución de incidencias' })).toHaveTextContent('2 buckets')
    expect(screen.getByRole('img', { name: 'Gráfica Sectores con más incidencias' })).toBeInTheDocument()
    fireEvent.click(within(screen.getByRole('region', { name: 'Clientes con más incidencias' })).getByRole('button', { name: 'Ver ranking completo (1)' }))
    expect(screen.getByRole('table', { name: 'Clientes con más incidencias' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'T-0' })).toHaveAttribute('href', '/tickets/1')
  })
  it.each(['1', '7', '15', '30'])('selecciona período %s, persiste URL y reinicia offset', async (value) => {
    const mock = setup('/reports?period=custom&from=2026-10-01&to=2026-10-02&offset=50'); await loaded()
    fireEvent.click(within(screen.getByRole('group', { name: 'Período del reporte' })).getByRole('button', { name: value === '1' ? 'Hoy' : `${value}D` }))
    expect(screen.getByTestId('url')).toHaveTextContent(`period=${value}`)
    expect(screen.getByTestId('url')).not.toHaveTextContent('offset=')
    await waitFor(() => expect(mock.mock.calls.some(([path]) => path.includes(`granularity=${value === '1' ? 'hour' : 'auto'}`))).toBe(true))
    expect(within(screen.getByRole('group', { name: 'Período del reporte' })).getByRole('button', { name: value === '1' ? 'Hoy' : `${value}D` })).toHaveAttribute('aria-pressed', 'true')
  })
  it('Personalizado restaura fechas de URL y soporta atrás/adelante', async () => {
    setup(); await loaded()
    expect(screen.getByLabelText('Desde')).toHaveValue('2026-10-01')
    expect(screen.getByLabelText('Hasta')).toHaveValue('2026-10-02')
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-09-01' } })
    expect(screen.getByTestId('url')).toHaveTextContent('from=2026-09-01')
    fireEvent.click(screen.getByRole('button', { name: 'Atrás' }))
    await waitFor(() => expect(screen.getByLabelText('Desde')).toHaveValue('2026-10-01'))
    fireEvent.click(screen.getByRole('button', { name: 'Adelante' }))
    await waitFor(() => expect(screen.getByLabelText('Desde')).toHaveValue('2026-09-01'))
    fireEvent.click(screen.getByRole('button', { name: '7D' }))
    fireEvent.click(within(screen.getByRole('group', { name: 'Período del reporte' })).getByRole('button', { name: 'Personalizado' }))
    expect(screen.getByLabelText('Desde')).toBeInTheDocument()
  })
  it('Por sector solicita selección y conserva catálogos históricos', async () => {
    const mock = setup(); await loaded()
    fireEvent.click(screen.getByRole('button', { name: 'Por sector' }))
    expect(screen.getByText('Selecciona un sector para consultar el reporte.')).toBeInTheDocument()
    const selector = screen.getByRole('combobox', { name: 'Sector' })
    await waitFor(() => expect(selector).not.toBeDisabled())
    fireEvent.focus(selector); fireEvent.click(screen.getByRole('option', { name: 'Sector histórico' }))
    await screen.findByText('Reporte por Sector — Sector histórico')
    expect(screen.queryByRole('table', { name: 'Sectores con más incidencias' })).not.toBeInTheDocument()
    expect(mock.mock.calls.some(([path]) => path.startsWith('/api/reports/summary') && path.includes('sector_id=1'))).toBe(true)
    expect(mock.mock.calls.some(([path]) => path.startsWith('/api/tickets?') && path.includes('sector_id=1'))).toBe(true)
    expect(mock).toHaveBeenCalledWith('/api/sectors?include_inactive=true&limit=200&offset=0', expect.any(Object))
  })
  it('abre directamente sector desde URL', async () => {
    setup('/reports?view=sector&sector_id=1&period=7')
    expect(await screen.findByText('Reporte por Sector — Sector histórico')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '7D' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(within(screen.getByRole('region', { name: 'Clientes con más incidencias' })).getByRole('button', { name: 'Ver ranking completo (1)' }))
    const customerLink = new URL(screen.getByRole('link', { name: 'C-2 — Cliente' }).getAttribute('href')!, 'http://local')
    expect(customerLink.searchParams.get('sector_id')).toBe('1')
    expect(customerLink.searchParams.get('customer_id')).toBe('2')
  })
  it('drill-down mantiene período y filtros compatibles', async () => {
    setup(); await loaded()
    for (const button of screen.getAllByRole('button', { name: 'Ver ranking completo (1)' })) fireEvent.click(button)
    for (const [label, field, id] of [['C-2 — Cliente', 'customer_id', 2], ['C-2.003', 'circuit_id', 3], ['Incidencia', 'incident_type_id', 4]] as const) {
      const link = screen.getByRole('link', { name: label })
      expect(link).toHaveAttribute('href', `/tickets?${field}=${id}&from=2026-10-01&to=2026-10-02`)
    }
    const sector = screen.getByRole('link', { name: 'Sector histórico' })
    expect(sector).toHaveAttribute('href', '/reports?view=sector&period=custom&sector_id=1&from=2026-10-01&to=2026-10-02')
    fireEvent.click(sector)
    expect(await screen.findByText('Reporte por Sector — Sector histórico')).toBeInTheDocument()
  })
  it('paginación conserva universo de reporte y exportaciones', async () => {
    const mock = setup(undefined, { fullPage: true }); await loaded()
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
    expect(screen.getByTestId('url')).toHaveTextContent('offset=50')
    await waitFor(() => expect(mock.mock.calls.some(([path]) => path.includes('/api/tickets?limit=50&offset=50') && path.includes('from='))).toBe(true))
  })
  it('muestra loading sin ceros inventados', () => {
    setup(undefined, { pending: true })
    expect(screen.getByText('Cargando reporte...')).toBeInTheDocument()
    expect(screen.queryByText('Incidencias iniciadas')).not.toBeInTheDocument()
  })
  it('muestra vacío y KPIs cero', async () => {
    setup(undefined, { empty: true }); await loaded()
    expect(screen.getByText('No hay incidencias iniciadas en este período.')).toBeInTheDocument()
    expect(screen.getByText('No hay tickets')).toBeInTheDocument()
  })
  it('muestra error de API y reintentar', async () => {
    setup(undefined, { fail: true })
    expect(await screen.findByRole('alert')).toHaveTextContent('No disponible')
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Exportar PDF' })).toBeDisabled()
  })
  it('mantiene fechas editables al validar un período personalizado incompleto', async () => {
    setup(); await loaded()
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '' } })
    expect(screen.getByRole('alert')).toHaveTextContent('Completa Desde y Hasta')
    expect(screen.getByLabelText('Desde')).toHaveValue('')
    expect(screen.getByLabelText('Hasta')).toHaveValue('2026-10-02')
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-10-01' } })
    await loaded()
  })
  it('rechaza rango invertido antes de solicitar reporte', async () => {
    const mock = setup('/reports?period=custom&from=2026-10-03&to=2026-10-01')
    expect(screen.getByRole('alert')).toHaveTextContent('Hasta')
    expect(mock.mock.calls.some(([path]) => path.startsWith('/api/reports/summary'))).toBe(false)
  })
  it.each(['pdf', 'xlsx'] as const)('descarga %s con período/sector completos y sin offset', async (format) => {
    const mock = setup('/reports?view=sector&sector_id=1&period=custom&from=2026-10-01&to=2026-10-02&offset=50')
    vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn(() => 'blob:report'); static revokeObjectURL = vi.fn() })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    await screen.findByText('Reporte por Sector — Sector histórico')
    fireEvent.click(screen.getByRole('button', { name: format === 'pdf' ? 'Exportar PDF' : 'Exportar Excel' }))
    await waitFor(() => expect(click).toHaveBeenCalled())
    const call = mock.mock.calls.find(([path]) => path.startsWith(`/api/reports/export/${format}`))![0]
    const url = new URL(call, 'http://local')
    expect(url.searchParams.get('sector_id')).toBe('1')
    expect(url.searchParams.has('offset')).toBe(false)
    expect(url.searchParams.get('from')).toBe(new Date(2026, 9, 1).toISOString())
    expect(url.searchParams.get('to')).toBe(new Date(2026, 9, 3).toISOString())
    click.mockRestore()
  })
  it('error de exportación estructurado se muestra sin perder el reporte', async () => {
    setup(undefined, { exportFail: true }); await loaded()
    fireEvent.click(screen.getByRole('button', { name: 'Exportar PDF' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Rango inválido')
    expect(screen.queryByText('[object Object]')).not.toBeInTheDocument()
    expect(screen.getByText('Reporte General', { exact: true })).toBeInTheDocument()
  })
  it('deshabilita ambas exportaciones mientras genera el archivo', async () => {
    setup(undefined, { pendingExport: true }); await loaded()
    fireEvent.click(screen.getByRole('button', { name: 'Exportar Excel' }))
    expect(await screen.findByText('Generando archivo...')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Exportar PDF' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Exportar Excel' })).toBeDisabled()
  })
  it('sidebar abre /reports con lazy loading', async () => {
    setup('/customers', { app: true })
    fireEvent.click(screen.getByRole('link', { name: 'Reportería' }))
    expect(await screen.findByRole('heading', { name: 'Reportería', level: 1 })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Reportería' })).toHaveAttribute('aria-current', 'page')
  })
})

describe('URLs de exportación', () => {
  it('usa exactamente los filtros de la API de resumen', () => {
    const query: ReportQuery = { from: '2026-10-01T06:00:00Z', to: '2026-10-03T06:00:00Z', timezone: 'Etc/GMT+6', sector_id: 4 }
    for (const format of ['pdf', 'xlsx'] as const) {
      const url = new URL(reportExportUrl(format, query), 'http://local')
      expect(Object.fromEntries(url.searchParams)).toEqual({ ...query, sector_id: '4' })
    }
  })
})


describe('reportes por Nodo y Responsable', () => {
  it.each([['node', 'node_id', 'Nodo', 'Nodo Central', '5'], ['responsible', 'responsible_id', 'Responsable', 'Operador asignado', '6']])('restaura modo %s, mantiene universo en detalle/export y oculta ranking redundante', async (view, field, label, name, id) => {
    const mock = setup(`/reports?view=${view}&${field}=${id}&period=custom&from=2026-10-01&to=2026-10-02&offset=50`)
    expect(await screen.findByText(`Reporte por ${label} — ${name}`)).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: label })).toHaveValue(name)
    expect(mock.mock.calls.some(([path]) => path.startsWith('/api/reports/summary') && path.includes(`${field}=${id}`))).toBe(true)
    expect(mock.mock.calls.some(([path]) => path.startsWith('/api/tickets?') && path.includes(`${field}=${id}`))).toBe(true)
    expect(screen.queryByRole('region', { name: view === 'node' ? 'Nodos de distribución' : 'Responsables' })).not.toBeInTheDocument()
    for (const format of ['pdf', 'xlsx'] as const) {
      const url = new URL(reportExportUrl(format, { from: '2026-10-01T00:00:00Z', to: '2026-10-03T00:00:00Z', timezone: 'UTC', [field]: Number(id) }), 'http://local')
      expect(url.searchParams.get(field)).toBe(id); expect(url.searchParams.has('offset')).toBe(false)
    }
  })
  it('General muestra nuevos rankings y gráficas sin sustituir los existentes', async () => {
    setup(); await loaded()
    for (const name of ['Nodos de distribución', 'Responsables', 'Clientes con más incidencias', 'Circuitos con más incidencias']) expect(screen.getByRole('region', { name })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Gráfica iniciadas vs cerradas' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Gráfica Distribución por hora' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Gráfica Distribución por día' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Gráfica Duración promedio por sector (minutos)' })).toBeInTheDocument()
  })
  it.each([['Por nodo', 'Nodo'], ['Por responsable', 'Responsable']])('solicita selección al cambiar a %s y preserva período', async (button, label) => {
    setup(); await loaded()
    fireEvent.click(screen.getByRole('button', { name: button }))
    expect(screen.getByText(`Selecciona un ${label.toLowerCase()} para consultar el reporte.`)).toBeInTheDocument()
    expect(screen.getByTestId('url')).toHaveTextContent('from=2026-10-01')
    expect(screen.getByRole('combobox', { name: label })).toBeInTheDocument()
  })
})

it('presenta departamentos con ranking completo, drill-down y resolución', async () => {
  setup(); await loaded()
  const ranking = within(screen.getByRole('region', { name: 'Tickets por departamento' }))
  expect(ranking.getByRole('img', { name: 'Gráfica Tickets por departamento' })).toBeInTheDocument()
  fireEvent.click(ranking.getByRole('button', { name: 'Ver ranking completo (1)' }))
  expect(ranking.getByRole('link', { name: 'Departamento histórico' })).toHaveAttribute('href', '/tickets?department_id=7&from=2026-10-01&to=2026-10-02')
  expect(screen.getByRole('img', { name: 'Gráfica Tiempo de resolución por departamento (minutos)' })).toHaveAttribute('data-values', JSON.stringify([{ label: 'Departamento histórico', count: 90 }]))
})

it('comparte un único período con escalamientos, destinatario y exportaciones', async () => {
  const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const mock = setup(); await loaded()
  expect(screen.getAllByRole('group', { name: /Período/ })).toHaveLength(1)
  const group = screen.getByRole('group', { name: 'Período del reporte' })
  for (const name of ['Hoy', 'Ayer', '7D', '15D', '30D', 'Personalizado', 'Todos']) {
    fireEvent.click(within(group).getByRole('button', { name }))
    await waitFor(() => expect(mock.mock.calls.some(([url]) => url.includes('/api/reports/summary') && (name === 'Todos' ? !new URL(url, 'http://local').searchParams.has('from') : new URL(url, 'http://local').searchParams.has('from')))).toBe(true))
    await loaded()
    const reports = mock.mock.calls.filter(([url]) => url.includes('/api/reports/summary')).at(-1)![0]
    const escalations = mock.mock.calls.filter(([url]) => url.includes('/api/escalations/tickets')).at(-1)![0]
    const a = new URL(reports, 'http://local').searchParams, b = new URL(escalations, 'http://local').searchParams
    expect(b.get('from')).toBe(a.get('from')); expect(b.get('to')).toBe(a.get('to'))
  }
  fireEvent.click(screen.getByRole('combobox', { name: 'Escalamientos recibidos por' }))
  fireEvent.click(screen.getByRole('option', { name: 'Operador asignado' }))
  await waitFor(() => expect(mock.mock.calls.some(([url]) => url.includes('/api/reports/summary') && url.includes('recipient_id=6'))).toBe(true))
  await loaded()
  fireEvent.click(screen.getByRole('button', { name: 'Exportar PDF' }))
  await waitFor(() => expect(mock.mock.calls.some(([url]) => url.includes('/api/reports/export/pdf') && url.includes('recipient_id=6'))).toBe(true))
  expect(mock.mock.calls.some(([url]) => url.includes('/api/escalations/summary'))).toBe(false)
  anchorClick.mockRestore()
})
