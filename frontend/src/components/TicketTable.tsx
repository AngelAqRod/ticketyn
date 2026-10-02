import type { Ticket } from '../types/ticket'
import { formatDate, formatDuration } from '../lib/format'
import { StatusBadge } from './StatusBadge'

export function TicketTable({ tickets }: { tickets: Ticket[] }) {
  return <div className="panel overflow-hidden">
    <div className="overflow-x-auto">
      <table className="w-full min-w-[780px] text-left text-sm">
        <caption className="sr-only">Listado de tickets</caption>
        <thead className="border-b border-slate-200 bg-slate-50 text-xs text-slate-500">
          <tr>{['Referencia', 'Título', 'Estado', 'Inicio', 'Fin', 'Duración'].map((title) =>
            <th key={title} scope="col" className="px-5 py-4 font-medium">{title}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {tickets.map((ticket) => <tr key={ticket.id} className="hover:bg-slate-50">
            <th scope="row" className="whitespace-nowrap px-5 py-5 font-medium text-emerald-800">{ticket.reference}</th>
            <td className="max-w-80 min-w-48 px-5 py-5 text-slate-900">{ticket.title}</td>
            <td className="px-5 py-5"><StatusBadge status={ticket.status} /></td>
            <td className="whitespace-nowrap px-5 py-5 text-slate-500"><time dateTime={ticket.start_at}>{formatDate(ticket.start_at)}</time></td>
            <td className="whitespace-nowrap px-5 py-5 text-slate-500">{ticket.end_at ? <time dateTime={ticket.end_at}>{formatDate(ticket.end_at)}</time> : '—'}</td>
            <td className="whitespace-nowrap px-5 py-5 text-slate-500">{formatDuration(ticket.duration_seconds)}</td>
          </tr>)}
        </tbody>
      </table>
    </div>
  </div>
}
