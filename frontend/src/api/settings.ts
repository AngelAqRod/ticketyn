import { getJson, patchJson } from './client'
import type { TicketNumberConfig, TicketNumberChanges } from '../types/settings'
export const getTicketNumberConfig = (signal?: AbortSignal) => getJson<TicketNumberConfig>('/api/settings/ticket-number', signal)
export const updateTicketNumberConfig = (changes: TicketNumberChanges, signal?: AbortSignal) => patchJson<TicketNumberConfig>('/api/settings/ticket-number', changes, signal)
