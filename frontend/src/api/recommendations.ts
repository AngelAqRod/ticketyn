import { getJson, postJson } from './client'
import type { TicketRecommendationsResponse, AckResponse } from '../types/recommendation'

export function getTicketRecommendations(ticketId: number, internal = false, signal?: AbortSignal) {
  const scope = internal ? 'internal-tickets' : 'tickets'
  return getJson<TicketRecommendationsResponse>(`/api/${scope}/${ticketId}/recommendations`, signal)
}

export function createTicketAck(ticketId: number, payload: { duration_type: string; reason: string }, internal = false, signal?: AbortSignal) {
  const scope = internal ? 'internal-tickets' : 'tickets'
  return postJson<AckResponse>(`/api/${scope}/${ticketId}/ack`, payload, signal)
}

export function revokeTicketAck(ticketId: number, payload?: { reason?: string }, internal = false, signal?: AbortSignal) {
  const scope = internal ? 'internal-tickets' : 'tickets'
  return postJson<AckResponse>(`/api/${scope}/${ticketId}/ack/revoke`, payload ?? {}, signal)
}

export function listTicketAcks(ticketId: number, internal = false, signal?: AbortSignal) {
  const scope = internal ? 'internal-tickets' : 'tickets'
  return getJson<AckResponse[]>(`/api/${scope}/${ticketId}/acks`, signal)
}
