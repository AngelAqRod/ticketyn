import { ApiError, getJson, postJson } from './client'
import type { TicketUpdate, TicketUpdateCreate } from '../types/ticketUpdate'

export async function listTicketUpdates(ticketId: number, signal?: AbortSignal): Promise<TicketUpdate[]> {
  const updates = await getJson<TicketUpdate[]>(`/api/tickets/${ticketId}/updates`, signal)
  if (!Array.isArray(updates)) throw new ApiError('La API no devolvió un historial válido.')
  return updates
}

export const createTicketUpdate = (ticketId: number, payload: TicketUpdateCreate, signal?: AbortSignal) =>
  postJson<TicketUpdate>(`/api/tickets/${ticketId}/updates`, payload, signal)

export interface TicketUpdatePage { items: TicketUpdate[]; next_cursor: string | null }

export async function pageTicketUpdates(ticketId: number, cursor: string | null, signal?: AbortSignal): Promise<TicketUpdatePage> {
  const query = new URLSearchParams({ limit: '10' })
  if (cursor) query.set('cursor', cursor)
  const page = await getJson<TicketUpdatePage>(`/api/tickets/${ticketId}/updates?${query}`, signal)
  if (!page || !Array.isArray(page.items) || !(page.next_cursor === null || typeof page.next_cursor === 'string')) throw new ApiError('La API no devolvió un historial válido.')
  return page
}
