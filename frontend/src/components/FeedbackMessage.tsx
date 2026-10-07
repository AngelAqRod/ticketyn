import type { ReactNode } from 'react'
import { CircleAlert, CircleCheck } from 'lucide-react'

export function FeedbackMessage({ variant, children, id, className = '' }: {
  variant: 'success' | 'error'; children: ReactNode; id?: string; className?: string
}) {
  const Icon = variant === 'error' ? CircleAlert : CircleCheck
  return <div id={id} role={variant === 'error' ? 'alert' : 'status'} className={`feedback-message feedback-message--${variant} ${className}`}><Icon size={16} className="mt-0.5 shrink-0" aria-hidden="true" /><div className="min-w-0">{children}</div></div>
}
