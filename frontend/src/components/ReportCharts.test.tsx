import type { ReactNode } from 'react'
import { render, screen } from '../test/render'
import { describe, expect, it, vi } from 'vitest'
import { categoryColor, chartPalette } from './chartTheme'
import { ActivityChart, DistributionChart, RankingChart, TrendChart } from './ReportCharts'

const captured = vi.hoisted(() => ({ charts: [] as Record<string, unknown>[], lines: [] as Record<string, unknown>[], bars: [] as Record<string, unknown>[], yAxes: [] as Record<string, unknown>[] }))
vi.mock('recharts', () => {
  const wrapper = ({ children }: { children?: ReactNode }) => <div>{children}</div>
  const chart = (props: Record<string, unknown> & { children?: ReactNode }) => { captured.charts.push(props); return wrapper(props) }
  return {
    ResponsiveContainer: wrapper, LineChart: chart, BarChart: chart,
    Line: (props: Record<string, unknown>) => { captured.lines.push(props); return null },
    Bar: (props: Record<string, unknown> & { children?: ReactNode }) => { captured.bars.push(props); return wrapper(props) },
    CartesianGrid: () => null, XAxis: () => null, YAxis: (props: Record<string, unknown>) => { captured.yAxes.push(props); return null },
    Tooltip: () => null, LabelList: () => null,
    Cell: ({ fill }: { fill: string }) => <span data-testid="category" data-color={fill} />,
  }
})

describe('Capsule NOC charts', () => {
  it('cycles the official palette by displayed position, independent of category identity', () => {
    expect(Array.from({ length: 13 }, (_, index) => categoryColor(index))).toEqual([...chartPalette, ...chartPalette, chartPalette[0]])
    expect(categoryColor(0)).toBe('#176BDF')
    expect(categoryColor(1)).toBe('#9673D6')
  })
  it('starts two-category distributions in blue/lilac, including after filters and rerenders', () => {
    const rows = [{ id: 42, label: 'Con escalamiento', count: 6 }, { id: 999, label: 'Sin escalamiento', count: 7 }]
    const { rerender } = render(<DistributionChart rows={rows} title="Escalamientos" />)
    const colors = () => screen.getAllByTestId('category').map(el => el.getAttribute('data-color'))
    expect(colors()).toEqual(chartPalette.slice(0, 2))
    rerender(<DistributionChart rows={[rows[1]]} title="Escalamientos" />)
    expect(colors()).toEqual([chartPalette[0]])
    rerender(<DistributionChart rows={rows} title="Escalamientos" />)
    expect(colors()).toEqual(chartPalette.slice(0, 2))
  })
  it('preserves all chronological buckets including zero, and single-series linear interpolation', () => {
    const trend = [{ start_at: '2026-10-14T06:00:00Z', count: 0 }, { start_at: '2026-10-15T06:00:00Z', count: 13 }]
    render(<TrendChart trend={trend} granularity="day" timeZone="America/Guatemala" />)
    expect((captured.charts.at(-1)!.data as { count: number }[]).map(row => row.count)).toEqual([0, 13])
    expect(captured.lines.at(-1)).toMatchObject({ type: 'linear', stroke: chartPalette[0], dataKey: 'count' })
  })
  it('preserves activity values and the green closed-series association', () => {
    const rows = [{ start_at: '2026-10-15T06:00:00Z', started: 13, closed: 7 }]
    render(<ActivityChart rows={rows} />)
    expect(captured.charts.at(-1)!.data).toEqual([expect.objectContaining(rows[0])])
    expect(captured.lines.at(-1)).toMatchObject({ dataKey: 'closed', stroke: '#34d399' })
    render(<ActivityChart rows={rows} secondColor={chartPalette[1]} />)
    expect(captured.lines.at(-1)!.stroke).toBe(chartPalette[1])
  })
  it('keeps Top 10 order, values and compact horizontal bars', () => {
    const rows = Array.from({ length: 12 }, (_, i) => ({ id: 40 + i * 7, label: `Nombre extenso ${i}`, count: 12 - i, customer_id: null, customer_code: null, customer_name: null }))
    render(<RankingChart rows={rows} title="Clientes" />)
    expect(captured.charts.at(-1)!.data).toEqual(rows.slice(0, 10))
    expect(captured.charts.at(-1)!.layout).toBe('vertical')
    expect(captured.bars.at(-1)).toMatchObject({ radius: [0, 4, 4, 0], barSize: 13 })
    expect(screen.getAllByTestId('category').map(el => el.getAttribute('data-color'))).toEqual([...chartPalette, ...chartPalette.slice(0, 4)])
  })
  it('opts into integer count ticks without rounding durations or percentages by default', () => {
    const rows = [{label:'Agendado',count:0},{label:'Finalizado',count:1}]
    const {rerender}=render(<DistributionChart rows={rows} title="Cambios por Estado" integerCounts />)
    expect(captured.yAxes.at(-1)!.allowDecimals).toBe(false)
    expect(captured.charts.at(-1)!.data).toBe(rows)
    const fractional=[{label:'Duración',count:0.25}]
    rerender(<DistributionChart rows={fractional} title="Horas" />)
    expect(captured.yAxes.at(-1)!.allowDecimals).toBe(true)
    expect(captured.charts.at(-1)!.data).toBe(fractional)
  })
  it('allows explicit semantic category colors, including zero-count states', () => {
    const rows=[{label:'Agendado',count:0,color:'#D69A46'},{label:'Finalizado',count:1,color:'#91C9B5'},{label:'En ejecución',count:0,color:'#176BDF'}]
    render(<DistributionChart rows={rows} title="Cambios por Estado" integerCounts />)
    expect(captured.charts.at(-1)!.data).toBe(rows)
    expect(screen.getAllByTestId('category').map(el=>el.getAttribute('data-color'))).toEqual(rows.map(row=>row.color))
  })
  it('retains distribution zeros, precision and input order, including empty results', () => {
    const rows = [{ label: '00', count: 0 }, { label: '01', count: 1.23456 }]
    const { rerender } = render(<DistributionChart rows={rows} title="Horas" />)
    expect(captured.charts.at(-1)!.data).toBe(rows)
    expect(captured.bars.at(-1)!.radius).toEqual([4, 4, 0, 0])
    rerender(<DistributionChart rows={[]} title="Horas" />)
    expect(captured.charts.at(-1)!.data).toEqual([])
    expect(screen.queryByTestId('category')).not.toBeInTheDocument()
  })
})
