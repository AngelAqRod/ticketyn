import type { ReactNode } from 'react'

export function MetricStrip({ items, variant = 'dark' }: { items: { label: string; value: ReactNode; tone?: 'primary' | 'muted'; icon?: ReactNode; iconTone?: 'warning' | 'success' }[]; variant?: 'dark' | 'light' }) {
  return <dl className={`metric-strip${variant === 'light' ? ' metric-strip-light' : ''}`}>{items.map(({ label, value, tone, icon, iconTone }) => <div key={label} className="metric-item" data-tone={tone}>
    <dt>{label}</dt><dd>{value}</dd>
    {icon && <span className="icon-surface icon-surface--metric metric-icon" data-tone={iconTone} aria-hidden="true">{icon}</span>}
  </div>)}</dl>
}
