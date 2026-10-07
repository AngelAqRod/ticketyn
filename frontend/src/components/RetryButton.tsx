import type { ReactNode } from 'react'
import { RefreshCw } from 'lucide-react'

export function RetryButton({ onClick, children = 'Reintentar', className = '' }: {
  onClick: () => void; children?: ReactNode; className?: string
}) {
  return <button type="button" className={`button-ghost retry-button ${className}`} onClick={onClick}><RefreshCw size={13} aria-hidden="true" />{children}</button>
}
