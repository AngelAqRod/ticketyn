import type { ReactNode } from 'react'
import { useLocation } from 'react-router'
import { SevenSegmentNumber } from './SevenSegmentNumber'
import { identityFor } from './moduleIdentity'

export type HeadingStatTone = 'accent' | 'open' | 'unassigned' | 'age' | 'muted'

/** `value: null` = sin dato (carga o error); nunca se sustituye por 0. */
export interface HeadingStat {
  label: string
  value: number | null
  tone?: HeadingStatTone
  /** Con `value: null`: true = cargando, false = no disponible. */
  loading?: boolean
}

export interface PageHeadingProps {
  title: string
  description: string
  action?: ReactNode
  badge?: ReactNode
  theme?: 'blue' | 'purple' | 'amber' | 'emerald' | 'slate' | 'cyan'
  telemetry?: ReactNode
  /** Variante B: indicadores informativos con datos reales; sin `stats` es la variante A. */
  stats?: HeadingStat[]
  statsLabel?: string
}

export function PageHeading({
  title,
  description,
  action,
  badge,
  theme,
  telemetry,
  stats,
  statsLabel = 'Resumen',
}: PageHeadingProps) {
  const location = useLocation()
  const identity = identityFor(location.pathname)
  const resolvedTheme = theme ?? identity?.theme ?? 'blue'
  const resolvedBadge = badge ?? identity?.badge

  return (
    <div
      className={`page-heading page-heading--${resolvedTheme}`}
      data-module={identity?.number}
    >
      <div className="flex min-w-0 items-center gap-4">
        {identity && (
          <span
            aria-hidden="true"
            className={`heading-emblem heading-emblem--${resolvedTheme}`}
          >
            <SevenSegmentNumber value={identity.number} />
          </span>
        )}
        <div className="min-w-0 [overflow-wrap:anywhere]">
          {identity && (
            <p className="module-eyebrow">
              <span>{identity.group}</span>
              <span className="text-slate-600" aria-hidden="true">/</span>
              <span>{identity.title.toUpperCase()}</span>
            </p>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="page-title">{title}</h1>
            {resolvedBadge && (
              typeof resolvedBadge === 'string' ? (
                <span className={`module-badge module-badge--${resolvedTheme}`}>
                  {resolvedBadge}
                </span>
              ) : (
                resolvedBadge
              )
            )}
            {telemetry}
          </div>
          <p className="page-description">{description}</p>
        </div>
      </div>
      <div className="heading-actions">{action}</div>
      {stats && stats.length > 0 && (
        <section className="heading-stats-region" aria-label={statsLabel}>
          <ul className="heading-stats">
            {stats.map(stat => (
              <li
                key={stat.label}
                className={`heading-stat heading-stat--${stat.tone ?? 'accent'}${stat.value === null ? ' heading-stat--unknown' : ''}`}
              >
                <span className="heading-stat-label">{stat.label}</span>
                <strong className="heading-stat-value">
                  {stat.value === null ? (
                    <>
                      <span aria-hidden="true">{stat.loading ? '…' : '—'}</span>
                      <span className="sr-only">{stat.loading ? 'Cargando' : 'No disponible'}</span>
                    </>
                  ) : stat.value}
                </strong>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
