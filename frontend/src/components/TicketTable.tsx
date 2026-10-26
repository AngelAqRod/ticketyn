import { Can } from '../auth/permissions'
import { Link } from 'react-router'
import type { Ticket } from '../types/ticket'
import { formatDate, formatTableDate, formatDuration } from '../lib/format'
import { StatusBadge } from './StatusBadge'
import { CircuitLink } from './CircuitLink'

export function TicketTable({ tickets }: { tickets: Ticket[] }) {
  return <div className="panel table-surface overflow-hidden">
    <div className="overflow-x-auto">
      <table className="operation-table w-full min-w-[1100px]">
        <caption className="table-title">Listado de tickets</caption>
        <thead><tr>{['Referencia', 'Estado', 'Cliente', 'Circuito', 'Nodo', 'Responsable', 'Sector', 'Tipo', 'Inicio', 'Fin', 'Duración', 'Acción'].map((title) =>
          <th key={title} scope="col">{title}</th>)}</tr></thead>
        <tbody>
          {tickets.map((ticket) => {
            const isOpen = ticket.status === 'OPEN'
            const durationText = formatDuration(ticket.duration_seconds, ticket.status)
            return (
              <tr key={ticket.id} className={isOpen ? 'ticket-state-open' : 'ticket-state-closed'}>
                <th scope="row" className="w-36 whitespace-nowrap text-primary"><Can permission="tickets.view" fallback={<span>{ticket.reference}</span>}><Link to={`/tickets/${ticket.id}`} className="record-code hover:underline underline-offset-4">{ticket.reference}</Link></Can><span className="mt-0.5 block max-w-44 truncate text-sm font-normal text-slate-400 font-sans" title={ticket.title}>{ticket.title}</span></th>
                <td className="w-24"><StatusBadge status={ticket.status} /></td>
                <td className="max-w-44 text-sm text-slate-300" title={ticket.customer ? `${ticket.customer.customer_code} — ${ticket.customer.name}` : undefined}>{ticket.customer ? <><span className="customer-code-badge">{ticket.customer.customer_code}</span><span className="block truncate text-slate-200 mt-0.5">{ticket.customer.name}</span></> : '—'}</td>
                <td className="max-w-36 text-sm" title={ticket.circuit?.description}>{ticket.circuit ? <span className="circuit-badge whitespace-nowrap"><CircuitLink id={ticket.circuit.id === ticket.circuit_id ? ticket.circuit_id : null}>{ticket.circuit.circuit_code}</CircuitLink></span> : '—'}</td>
                <td className="max-w-28 text-sm text-slate-300">{ticket.node?.name ?? 'Sin asignar'}</td>
                <td className="max-w-28 text-sm">{ticket.responsible ? <span className="font-mono font-medium text-amber-300/90">{ticket.responsible.name}</span> : <span className="text-slate-400">Sin asignar</span>}</td>
                <td className="max-w-28 text-sm text-slate-300"><span className="line-clamp-2">{ticket.sector?.name ?? '—'}</span></td>
                <td className="max-w-28 text-sm text-slate-300"><span className="line-clamp-2">{ticket.incident_type?.name ?? '—'}</span></td>
                <td className="w-28 whitespace-nowrap text-sm font-mono tabular-nums text-slate-400"><time dateTime={ticket.start_at} title={formatDate(ticket.start_at)}>{formatTableDate(ticket.start_at)}</time></td>
                <td className="w-28 whitespace-nowrap text-sm font-mono tabular-nums text-slate-400">{ticket.end_at ? <time dateTime={ticket.end_at} title={formatDate(ticket.end_at)}>{formatTableDate(ticket.end_at)}</time> : '—'}</td>
                <td className="w-24 whitespace-nowrap font-mono text-sm font-bold tabular-nums"><span className={isOpen ? 'text-red-400' : 'text-slate-400'}>{durationText}</span></td>
                <td className="w-20 text-center whitespace-nowrap"><Can permission="tickets.view" fallback={<span className="text-slate-600 text-sm font-mono">—</span>}><Link to={`/tickets/${ticket.id}`} className="inline-flex items-center px-3 py-1 rounded-full text-sm font-mono font-medium text-blue-400 hover:text-white hover:bg-blue-600/30 border border-blue-900/60 transition-colors shadow-xs">Ver</Link></Can></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  </div>
}
