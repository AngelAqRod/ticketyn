import type { TicketStatus } from '../types/ticket'

export function StatusBadge({ status }: { status: TicketStatus }) {
  return (
    <span className={`status-badge ${
      status === 'OPEN' ? 'border-amber-200 bg-amber-50 text-amber-900' : 'border-slate-200 bg-slate-100 text-slate-600'
    }`}>
      <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${status === 'OPEN' ? 'bg-amber-600' : 'bg-slate-500'}`} />
      {status === 'OPEN' ? 'Abierto' : 'Cerrado'}
    </span>
  )
}
