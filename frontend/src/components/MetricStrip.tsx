import type { ReactNode } from 'react'

export function MetricStrip({ items }: { items: { label: string; value: ReactNode; tone?: 'primary' | 'muted' }[] }) {
  return <dl className="metric-strip">{items.map(({ label, value, tone }) => <div key={label} className="metric-item" data-tone={tone}>
    <dt>{label}</dt><dd>{value}</dd>
  </div>)}</dl>
}
