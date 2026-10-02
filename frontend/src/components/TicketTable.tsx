import { Link } from 'react-router'
import type { Ticket } from '../types/ticket'
import { formatDate, formatTableDate, formatDuration } from '../lib/format'
import { StatusBadge } from './StatusBadge'

export function TicketTable({ tickets }: { tickets: Ticket[] }) {
  return <div className="panel overflow-hidden">
    <div className="overflow-x-auto">
      <table className="operation-table min-w-[860px]">
        <caption className="sr-only">Listado de tickets</caption>
        <thead><tr>{['Referencia', 'Estado', 'Título', 'Inicio', 'Fin', 'Duración'].map((title) =>
          <th key={title} scope="col">{title}</th>)}</tr></thead>
        <tbody>
          {tickets.map((ticket) => <tr key={ticket.id}>
            <th scope="row" className="w-36 whitespace-nowrap text-emerald-800"><Link to={`/tickets/${ticket.id}`} className="record-code hover:underline underline-offset-4">{ticket.reference}</Link></th>
            <td className="w-28"><StatusBadge status={ticket.status} /></td>
            <td className="min-w-52 text-slate-900"><span className="line-clamp-2" title={ticket.title}>{ticket.title}</span></td>
            <td className="w-40 whitespace-nowrap text-xs tabular-nums text-slate-600"><time dateTime={ticket.start_at} title={formatDate(ticket.start_at)}>{formatTableDate(ticket.start_at)}</time></td>
            <td className="w-40 whitespace-nowrap text-xs tabular-nums text-slate-600">{ticket.end_at ? <time dateTime={ticket.end_at} title={formatDate(ticket.end_at)}>{formatTableDate(ticket.end_at)}</time> : '—'}</td>
            <td className="w-28 whitespace-nowrap font-mono text-xs tabular-nums text-slate-600">{formatDuration(ticket.duration_seconds)}</td>
          </tr>)}
        </tbody>
      </table>
    </div>
  </div>
}
