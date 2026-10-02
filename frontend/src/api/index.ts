import { getJson, ApiError } from './client'
import type { Ticket } from '../types/ticket'

export async function getHealth(signal?: AbortSignal): Promise<void> {
  const health = await getJson<{ status: string }>('/health', signal)
  if (health?.status !== 'ok') throw new ApiError('La API no confirmó su disponibilidad.')
}

export async function listTickets(
  { limit = 50, offset = 0 }: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<Ticket[]> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  const tickets = await getJson<Ticket[]>(`/api/tickets?${query}`, signal)
  if (!Array.isArray(tickets)) throw new ApiError('La API no devolvió una lista de tickets válida.')
  return tickets
}
