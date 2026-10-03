import type { TicketStatus } from '../types/ticket'

export function StatusBadge({ status }: { status: TicketStatus }) {
  return (
    <span className={`status-badge ${
      status === 'OPEN' ? 'status-active' : 'status-neutral'
    }`}>
      <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${status === 'OPEN' ? 'bg-primary' : 'bg-slate-500'}`} />
      {status === 'OPEN' ? 'Abierto' : 'Cerrado'}
    </span>
  )
}
