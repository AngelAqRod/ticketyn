import { Link } from 'react-router'
import type { Ticket } from '../types/ticket'
import { formatDate, formatTableDate, formatDuration } from '../lib/format'
import { StatusBadge } from './StatusBadge'

export function TicketTable({ tickets }: { tickets: Ticket[] }) {
  return <div className="panel overflow-hidden">
    <div className="overflow-x-auto">
      <table className="operation-table min-w-[1350px]">
        <caption className="sr-only">Listado de tickets</caption>
        <thead><tr>{['Referencia', 'Estado', 'Cliente', 'Circuito', 'Nodo', 'Responsable', 'Sector', 'Tipo', 'Inicio', 'Fin', 'Duración'].map((title) =>
          <th key={title} scope="col">{title}</th>)}</tr></thead>
        <tbody>
          {tickets.map((ticket) => <tr key={ticket.id}>
            <th scope="row" className="w-36 whitespace-nowrap text-primary"><Link to={`/tickets/${ticket.id}`} className="record-code hover:underline underline-offset-4">{ticket.reference}</Link><span className="mt-0.5 block max-w-48 truncate text-xs font-normal text-slate-600" title={ticket.title}>{ticket.title}</span></th>
            <td className="w-28"><StatusBadge status={ticket.status} /></td>
            <td className="max-w-48 text-xs text-slate-800" title={ticket.customer ? `${ticket.customer.customer_code} — ${ticket.customer.name}` : undefined}>{ticket.customer ? <><span className="record-code">{ticket.customer.customer_code}</span><span className="block truncate">{ticket.customer.name}</span></> : '—'}</td>
            <td className="max-w-44 text-xs" title={ticket.circuit?.description}><span className="record-code">{ticket.circuit?.circuit_code ?? '—'}</span></td>
            <td className="max-w-36 text-xs">{ticket.node?.name ?? 'Sin asignar'}</td><td className="max-w-36 text-xs">{ticket.responsible?.name ?? 'Sin asignar'}</td>
            <td className="max-w-36 text-xs"><span className="line-clamp-2">{ticket.sector?.name ?? '—'}</span></td>
            <td className="max-w-36 text-xs"><span className="line-clamp-2">{ticket.incident_type?.name ?? '—'}</span></td>
            <td className="w-40 whitespace-nowrap text-xs tabular-nums text-slate-600"><time dateTime={ticket.start_at} title={formatDate(ticket.start_at)}>{formatTableDate(ticket.start_at)}</time></td>
            <td className="w-40 whitespace-nowrap text-xs tabular-nums text-slate-600">{ticket.end_at ? <time dateTime={ticket.end_at} title={formatDate(ticket.end_at)}>{formatTableDate(ticket.end_at)}</time> : '—'}</td>
            <td className="w-28 whitespace-nowrap font-mono text-xs tabular-nums text-slate-600">{formatDuration(ticket.duration_seconds)}</td>
          </tr>)}
        </tbody>
      </table>
    </div>
  </div>
}
