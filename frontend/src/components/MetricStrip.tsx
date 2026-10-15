import type { ReactNode } from 'react'

export type MetricColor = 'lilac' | 'amber' | 'mint' | 'ice' | 'indigo' | 'slate' | 'cyan'

export interface MetricItem {
  label: string; value: ReactNode; tone?: 'primary' | 'muted'; icon?: ReactNode
  iconTone?: 'warning' | 'success'; color?: MetricColor
}

export function MetricStrip({ items, variant = 'dark' }: { items: MetricItem[]; variant?: 'dark' | 'light' }) {
  return <div className="metric-strip-frame"><div className={`metric-strip${variant === 'light' ? ' metric-strip-light' : ''}`} data-count={items.length}>{items.map(({ label, value, tone, icon, iconTone, color }) => <dl key={label} className="metric-slot"><div className="metric-item" data-tone={tone} data-color={color ?? (iconTone === 'warning' ? 'amber' : iconTone === 'success' ? 'mint' : tone === 'muted' ? 'slate' : tone === 'primary' ? 'ice' : 'lilac')}>
    <dt>{label}</dt><dd>{value}</dd>
    {icon && <span className="icon-surface icon-surface--metric metric-icon" data-tone={iconTone} aria-hidden="true">{icon}</span>}
  </div></dl>)}</div></div>
}
