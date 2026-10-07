import type { ReactNode } from 'react'
import { Inbox, CircleAlert, LoaderCircle } from 'lucide-react'
import { RetryButton } from './RetryButton'

export function RequestState({ loading = false, error = null, empty = false, onRetry, compact = false,
  loadingText = 'Cargando...', errorTitle = 'Error al cargar tickets', emptyTitle = 'No hay tickets',
  emptyDescription = 'No se encontraron registros en esta página.', retryText = 'Reintentar', children, className = '', id }: {
  loading?: boolean; error?: string | null; empty?: boolean; onRetry?: () => void; compact?: boolean
  loadingText?: string; errorTitle?: string; emptyTitle?: string; emptyDescription?: string
  retryText?: string; children?: ReactNode; className?: string; id?: string
}) {
  if (!loading && !error && !empty) return null
  const Icon = loading ? LoaderCircle : error ? CircleAlert : Inbox
  return <div id={id} role={error && !loading ? 'alert' : 'status'} className={`${compact ? 'request-state-compact' : 'panel p-6 text-center'} ${className}`}>
    <Icon size={compact ? 16 : 24} aria-hidden="true" className={`${compact ? 'mt-0.5 shrink-0' : 'mx-auto mb-3'} ${error && !loading ? 'text-red-600' : 'text-slate-400'}`} />
    <div className="min-w-0 text-sm">
      {loading ? <p className="text-muted">{loadingText}</p> : error ? <>
        {errorTitle && <h2 className="font-semibold text-slate-900">{errorTitle}</h2>}
        <p className={errorTitle ? 'mt-1 text-muted' : 'text-muted'}>{error}</p>
        {onRetry && <RetryButton className="mt-2" onClick={onRetry}>{retryText}</RetryButton>}
      </> : <><h2 className="font-semibold text-slate-900">{emptyTitle}</h2>{emptyDescription && <p className="mt-1 text-muted">{emptyDescription}</p>}</>}
      {children}
    </div>
  </div>
}
