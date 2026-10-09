import { ResponsiveContainer, LineChart, Line, BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, LabelList } from 'recharts'
import type { ReportSummary, ReportRanking } from '../types/report'

const tooltipSurface = { backgroundColor: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: '10px 12px', fontSize: 12, boxShadow: 'var(--shadow-raised)' }
const tooltipLabel = { color: 'var(--text-secondary)', fontSize: 11, marginBottom: 4 }
const tooltipValue = { color: 'var(--text-primary)', fontSize: 13, fontWeight: 600 }
const chartTick = { fontSize: 10, fill: 'var(--text-secondary)' }
const chartCursor = { stroke: 'var(--primary-border)', fill: 'var(--primary-soft)' }
const activePoint = { r: 4, stroke: 'var(--surface)', strokeWidth: 2 }

function RelevantPoint({ cx, cy, value, stroke }: { cx?: number; cy?: number; value?: number; stroke?: string }) {
  if (cx === undefined || cy === undefined || !value || value <= 0) return <g />
  return <circle className="report-chart-point" cx={cx} cy={cy} r={2.5} fill={stroke} stroke="var(--surface)" strokeWidth={1} />
}

function RankingAxisTick({ x, y, index, payload }: { x?: number; y?: number; index?: number; payload?: { value: string } }) {
  const label = payload?.value ?? ''
  return <text x={x} y={y} dy={3} textAnchor="end" fill="var(--text-secondary)" fontSize={10}>
    <title>{label}</title><tspan fill="var(--primary)" fontWeight={600}>{String((index ?? 0) + 1).padStart(2, '0')}  </tspan>{label.length > 21 ? `${label.slice(0, 20)}…` : label}
  </text>
}

export function TrendChart({ trend, granularity, title = 'Evolución de incidencias', countLabel = 'Incidencias' }: { title?: string; countLabel?: string; trend: ReportSummary['trend']; granularity: string }) {
  const formatter = new Intl.DateTimeFormat('es', granularity === 'hour' ? { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' } : { day: '2-digit', month: 'short', year: '2-digit' })
  const data = trend.map((bucket) => ({ label: formatter.format(new Date(bucket.start_at)), count: bucket.count }))
  return <div aria-label={`Gráfica de ${title.toLocaleLowerCase()}`} role="img" className="report-chart h-56 w-full min-w-0">
    <ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ left: 0, right: 16, top: 12, bottom: 5 }}><CartesianGrid stroke="var(--border)" strokeOpacity={0.65} strokeDasharray="3 5" vertical={false} /><XAxis dataKey="label" minTickGap={32} tick={chartTick} axisLine={false} tickLine={false} /><YAxis allowDecimals={false} width={35} tick={chartTick} axisLine={false} tickLine={false} /><Tooltip contentStyle={tooltipSurface} labelStyle={tooltipLabel} itemStyle={tooltipValue} cursor={chartCursor} /><Line type="linear" dataKey="count" name={countLabel} stroke="var(--primary)" strokeWidth={2.75} dot={RelevantPoint} activeDot={activePoint} isAnimationActive={false} /></LineChart></ResponsiveContainer>
  </div>
}
export function RankingChart({ rows, title, countLabel = 'Incidencias' }: { rows: ReportRanking[]; title: string; countLabel?: string }) {
  const data = rows.slice(0, 10)
  return <div role="img" aria-label={`Gráfica ${title}`} className="report-chart" style={{ height: Math.max(72, data.length * 28 + 28) }}>
    <ResponsiveContainer width="100%" height="100%"><BarChart data={data} layout="vertical" margin={{ right: 32, left: 0 }}><CartesianGrid stroke="var(--border)" strokeOpacity={0.65} strokeDasharray="3 5" horizontal={false} /><XAxis type="number" allowDecimals={false} tick={chartTick} axisLine={false} tickLine={false} /><YAxis type="category" dataKey="label" interval={0} width={150} tick={<RankingAxisTick />} axisLine={false} tickLine={false} /><Tooltip contentStyle={tooltipSurface} labelStyle={tooltipLabel} itemStyle={tooltipValue} cursor={chartCursor} /><Bar dataKey="count" name={countLabel} fill="var(--primary)" activeBar={{ fill: 'var(--primary-hover)', fillOpacity: 0.9 }} barSize={13} radius={[0, 4, 4, 0]} isAnimationActive={false}><LabelList dataKey="count" position="right" fill="var(--text-primary)" fontSize={11} /></Bar></BarChart></ResponsiveContainer>
  </div>
}

export function ActivityChart({ rows }: { rows: NonNullable<ReportSummary['activity']> }) {
  const data = rows.map((row) => ({ ...row, label: new Intl.DateTimeFormat('es', { day: '2-digit', month: 'short', hour: '2-digit' }).format(new Date(row.start_at)) }))
  return <div role="img" aria-label="Gráfica iniciadas vs cerradas" className="report-chart h-56"><ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ left: 0, right: 16, top: 12, bottom: 5 }}><CartesianGrid stroke="var(--border)" strokeOpacity={0.65} strokeDasharray="3 5" vertical={false} /><XAxis dataKey="label" minTickGap={40} tick={chartTick} axisLine={false} tickLine={false} /><YAxis allowDecimals={false} tick={chartTick} axisLine={false} tickLine={false} /><Tooltip contentStyle={tooltipSurface} labelStyle={tooltipLabel} itemStyle={tooltipValue} cursor={chartCursor} /><Line dataKey="started" name="Iniciadas" stroke="var(--primary)" strokeWidth={2.5} dot={RelevantPoint} activeDot={activePoint} isAnimationActive={false} /><Line dataKey="closed" name="Cerradas" stroke="#64748b" strokeWidth={2.5} dot={RelevantPoint} activeDot={activePoint} isAnimationActive={false} /></LineChart></ResponsiveContainer></div>
}
export function DistributionChart({ rows, title }: { rows: { label: string; count: number }[]; title: string }) {
  return <div role="img" aria-label={`Gráfica ${title}`} className="report-chart h-48"><ResponsiveContainer width="100%" height="100%"><BarChart data={rows} margin={{ left: 0, right: 16, top: 12, bottom: 5 }}><CartesianGrid stroke="var(--border)" strokeOpacity={0.65} strokeDasharray="3 5" vertical={false} /><XAxis dataKey="label" tick={{ ...chartTick, fontSize: 9 }} axisLine={false} tickLine={false} /><YAxis tick={chartTick} axisLine={false} tickLine={false} /><Tooltip contentStyle={tooltipSurface} labelStyle={tooltipLabel} itemStyle={tooltipValue} cursor={chartCursor} /><Bar dataKey="count" name={title} fill="var(--primary)" radius={[4, 4, 0, 0]} activeBar={{ fill: 'var(--primary-hover)', fillOpacity: 0.9 }} isAnimationActive={false} /></BarChart></ResponsiveContainer></div>
}
