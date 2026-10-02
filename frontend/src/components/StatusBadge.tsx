import type { TicketStatus } from '../types/ticket'

export function StatusBadge({ status }: { status: TicketStatus }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
      status === 'OPEN' ? 'bg-amber-50 text-amber-800' : 'bg-emerald-50 text-emerald-800'
    }`}>
      <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${status === 'OPEN' ? 'bg-amber-600' : 'bg-emerald-600'}`} />
      {status === 'OPEN' ? 'Abierto' : 'Cerrado'}
    </span>
  )
}
