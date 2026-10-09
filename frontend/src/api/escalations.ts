import { getJson, postJson } from './client'
import type { Escalation, EscalationInput, EscalationSummary, EscalationTicket } from '../types/escalation'
export async function listEscalations(id: number, signal?: AbortSignal) {
  const items: Escalation[] = []
  for (let offset = 0; ; offset += 200) {
    const page = await getJson<Escalation[]>(`/api/tickets/${id}/escalations?limit=200&offset=${offset}`, signal)
    if (!Array.isArray(page)) throw new Error('La API no devolvió escalamientos válidos.')
    items.push(...page)
    if (page.length < 200) return items
  }
}
export const createEscalation = (id: number, payload: EscalationInput, signal?: AbortSignal) => postJson<Escalation>(`/api/tickets/${id}/escalations`, payload, signal)
export const finishEscalation = (id: number, escalation: number, signal?: AbortSignal) => postJson<Escalation>(`/api/tickets/${id}/escalations/${escalation}/finish`, {}, signal)
export const escalationSummary = (query: URLSearchParams, signal?: AbortSignal) => getJson<EscalationSummary>(`/api/escalations/summary?${query}`, signal)
export const escalationTickets = (query: URLSearchParams, signal?: AbortSignal) => getJson<EscalationTicket[]>(`/api/escalations/tickets?${query}`, signal)
