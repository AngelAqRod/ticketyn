import type { TicketStatus } from '../types/ticket'

export function StatusBadge({ status }: { status: TicketStatus }) {
  const isOpen = status === 'OPEN'
  return (
    <span className={`status-badge ${
      isOpen ? 'status-active status-ticket-open' : 'status-neutral status-ticket-closed'
    }`}>
      <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${isOpen ? 'bg-red-400' : 'bg-emerald-400'}`} />
      {isOpen ? 'Abierto' : 'Cerrado'}
    </span>
  )
}
