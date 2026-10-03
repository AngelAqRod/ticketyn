import { ResponsiveContainer, LineChart, Line, BarChart, Bar, CartesianGrid, XAxis, YAxis, Tooltip, LabelList } from 'recharts'
import type { ReportSummary, ReportRanking } from '../types/report'

function RankingAxisTick({ x, y, index, payload }: { x?: number; y?: number; index?: number; payload?: { value: string } }) {
  const label = payload?.value ?? ''
  return <text x={x} y={y} dy={3} textAnchor="end" fill="var(--text-secondary)" fontSize={10}>
    <title>{label}</title><tspan fill="var(--primary)" fontWeight={600}>{String((index ?? 0) + 1).padStart(2, '0')}  </tspan>{label.length > 21 ? `${label.slice(0, 20)}…` : label}
  </text>
}

export function TrendChart({ trend, granularity }: { trend: ReportSummary['trend']; granularity: string }) {
  const formatter = new Intl.DateTimeFormat('es', granularity === 'hour' ? { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', timeZoneName: 'short' } : { day: '2-digit', month: 'short', year: '2-digit' })
  const data = trend.map((bucket) => ({ label: formatter.format(new Date(bucket.start_at)), count: bucket.count }))
  return <div aria-label="Gráfica de evolución de incidencias" role="img" className="h-56 w-full min-w-0">
    <ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ left: 0, right: 16, top: 12, bottom: 5 }}><CartesianGrid stroke="var(--border)" vertical={false} /><XAxis dataKey="label" minTickGap={32} tick={{ fontSize: 10, fill: 'var(--text-secondary)' }} axisLine={false} tickLine={false} /><YAxis allowDecimals={false} width={35} tick={{ fontSize: 10, fill: 'var(--text-secondary)' }} axisLine={false} tickLine={false} /><Tooltip contentStyle={{ border: '1px solid var(--primary-border)', borderRadius: 10, fontSize: 12, boxShadow: 'var(--shadow-raised)' }} labelStyle={{ color: 'var(--text-primary)', fontWeight: 600 }} cursor={{ stroke: 'var(--primary-border)', fill: 'var(--primary-soft)' }} /><Line type="linear" dataKey="count" name="Incidencias" stroke="var(--primary)" strokeWidth={2.5} dot={false} isAnimationActive={false} /></LineChart></ResponsiveContainer>
  </div>
}
export function RankingChart({ rows, title }: { rows: ReportRanking[]; title: string }) {
  const data = rows.slice(0, 10)
  return <div role="img" aria-label={`Gráfica ${title}`} style={{ height: Math.max(72, data.length * 28 + 28) }}>
    <ResponsiveContainer width="100%" height="100%"><BarChart data={data} layout="vertical" margin={{ right: 32, left: 0 }}><CartesianGrid stroke="var(--border)" horizontal={false} /><XAxis type="number" allowDecimals={false} tick={{ fontSize: 10, fill: 'var(--text-secondary)' }} axisLine={false} tickLine={false} /><YAxis type="category" dataKey="label" interval={0} width={150} tick={<RankingAxisTick />} axisLine={false} tickLine={false} /><Tooltip contentStyle={{ border: '1px solid var(--primary-border)', borderRadius: 10, fontSize: 12, boxShadow: 'var(--shadow-raised)' }} labelStyle={{ color: 'var(--text-primary)', fontWeight: 600 }} cursor={{ stroke: 'var(--primary-border)', fill: 'var(--primary-soft)' }} /><Bar dataKey="count" name="Incidencias" fill="var(--primary)" barSize={13} radius={[0, 4, 4, 0]} isAnimationActive={false}><LabelList dataKey="count" position="right" fill="var(--text-primary)" fontSize={11} /></Bar></BarChart></ResponsiveContainer>
  </div>
}

export function ActivityChart({ rows }: { rows: NonNullable<ReportSummary['activity']> }) {
  const data = rows.map((row) => ({ ...row, label: new Intl.DateTimeFormat('es', { day: '2-digit', month: 'short', hour: '2-digit' }).format(new Date(row.start_at)) }))
  return <div role="img" aria-label="Gráfica iniciadas vs cerradas" className="h-56"><ResponsiveContainer width="100%" height="100%"><LineChart data={data}><CartesianGrid stroke="var(--border)" vertical={false} /><XAxis dataKey="label" minTickGap={40} tick={{ fontSize: 10 }} /><YAxis allowDecimals={false} /><Tooltip /><Line dataKey="started" name="Iniciadas" stroke="var(--primary)" dot={false} isAnimationActive={false} /><Line dataKey="closed" name="Cerradas" stroke="#64748b" dot={false} isAnimationActive={false} /></LineChart></ResponsiveContainer></div>
}
export function DistributionChart({ rows, title }: { rows: { label: string; count: number }[]; title: string }) {
  return <div role="img" aria-label={`Gráfica ${title}`} className="h-48"><ResponsiveContainer width="100%" height="100%"><BarChart data={rows}><CartesianGrid stroke="var(--border)" vertical={false} /><XAxis dataKey="label" tick={{ fontSize: 9 }} /><YAxis /><Tooltip /><Bar dataKey="count" name={title} fill="var(--primary)" isAnimationActive={false} /></BarChart></ResponsiveContainer></div>
}
