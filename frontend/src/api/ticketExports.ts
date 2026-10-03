import { downloadFile } from './client'
import type { TicketQuery } from '../types/ticket'

export function ticketExportUrl(format: 'pdf' | 'xlsx', query: TicketQuery, timezone = Intl.DateTimeFormat().resolvedOptions().timeZone): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (key !== 'limit' && key !== 'offset' && value !== undefined && value !== '') params.set(key, String(value))
  }
  params.set('timezone', timezone)
  return `/api/tickets/export/${format}?${params}`
}
export const downloadTickets = (format: 'pdf' | 'xlsx', query: TicketQuery) => downloadFile(ticketExportUrl(format, query), `ticketyn-tickets.${format}`)
