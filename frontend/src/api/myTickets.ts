import { getJson } from './client'
import type { MyTicketsFilterParams, MyTicketsListResponse, MyTicketsSummaryResponse } from '../types/myTickets'

export function getMyTickets(params: MyTicketsFilterParams = {}, signal?: AbortSignal): Promise<MyTicketsListResponse> {
  const query = new URLSearchParams()
  if (params.view) query.set('view', params.view)
  if (params.scope && params.scope !== 'ALL') query.set('scope', params.scope)
  if (params.open_only !== undefined && params.open_only !== null) {
    query.set('open_only', String(params.open_only))
  }
  if (params.escalation_status) query.set('escalation_status', params.escalation_status)
  if (params.search && params.search.trim()) query.set('search', params.search.trim())
  if (params.limit !== undefined) query.set('limit', String(params.limit))
  if (params.offset !== undefined) query.set('offset', String(params.offset))

  const queryString = query.toString()
  const url = queryString ? `/api/my-tickets?${queryString}` : '/api/my-tickets'
  return getJson<MyTicketsListResponse>(url, signal)
}

export function getMyTicketsSummary(signal?: AbortSignal): Promise<MyTicketsSummaryResponse> {
  return getJson<MyTicketsSummaryResponse>('/api/my-tickets/summary', signal)
}
