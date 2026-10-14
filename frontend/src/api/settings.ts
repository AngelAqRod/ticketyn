import { getJson, patchJson } from './client'
import type { TicketNumberConfig, TicketNumberChanges } from '../types/settings'
export const getTicketNumberConfig = (signal?: AbortSignal, activation = false) => getJson<TicketNumberConfig>(activation ? '/api/settings/activation-number' : '/api/settings/ticket-number', signal)
export const updateTicketNumberConfig = (changes: TicketNumberChanges, signal?: AbortSignal, activation = false) => patchJson<TicketNumberConfig>(activation ? '/api/settings/activation-number' : '/api/settings/ticket-number', changes, signal)
