import { downloadFile } from './client'
import type { TicketQuery } from '../types/ticket'

export function ticketExportUrl(format: 'pdf' | 'xlsx', query: TicketQuery, timezone = Intl.DateTimeFormat().resolvedOptions().timeZone): string {
  return listExportUrl('tickets', format, Object.entries(query), timezone)
}

function listExportUrl(scope: string, format: 'pdf' | 'xlsx', entries: Iterable<[string, unknown]>, timezone: string): string {
  const params = new URLSearchParams()
  for (const [key, value] of entries) {
    if (key !== 'limit' && key !== 'offset' && value !== undefined && value !== '') params.set(key, String(value))
  }
  params.set('timezone', timezone)
  return `/api/${scope}/export/${format}?${params}`
}

export function internalTicketExportUrl(format: 'pdf' | 'xlsx', query: URLSearchParams, timezone = Intl.DateTimeFormat().resolvedOptions().timeZone): string {
  return listExportUrl('internal-tickets', format, query.entries(), timezone)
}
export const downloadInternalTickets = (format: 'pdf' | 'xlsx', query: URLSearchParams) => downloadFile(internalTicketExportUrl(format, query), `ticketyn-tickets-internos.${format}`)

export const downloadTickets = (format: 'pdf' | 'xlsx', query: TicketQuery) => downloadFile(ticketExportUrl(format, query), `ticketyn-tickets.${format}`)
