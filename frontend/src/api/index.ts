import { getJson, postJson, patchJson, ApiError } from './client'
import type { Ticket, TicketCreateInput, TicketStats } from '../types/ticket'
import type { Circuit, Customer, Department, IncidentType, Sector } from '../types/catalog'

async function activeCatalog<T>(path: string, signal?: AbortSignal, filters: Record<string, string> = {}): Promise<T[]> {
  const items: T[] = []
  for (let offset = 0; ; offset += 200) {
    const query = new URLSearchParams({ ...filters, include_inactive: 'false', limit: '200', offset: String(offset) })
    const page = await getJson<T[]>(`${path}?${query}`, signal)
    if (!Array.isArray(page)) throw new ApiError('La API no devolvió un catálogo válido.')
    items.push(...page)
    if (page.length < 200) return items
  }
}

export const listCustomers = (signal?: AbortSignal) => activeCatalog<Customer>('/api/customers', signal)
export const listSectors = (signal?: AbortSignal) => activeCatalog<Sector>('/api/sectors', signal)
export const listDepartments = (signal?: AbortSignal) => activeCatalog<Department>('/api/departments', signal)
export const listIncidentTypes = (signal?: AbortSignal) => activeCatalog<IncidentType>('/api/incident-types', signal)
export const listCircuits = (customerId: number, signal?: AbortSignal) =>
  activeCatalog<Circuit>('/api/circuits', signal, { customer_id: String(customerId) })

export function createTicket(payload: TicketCreateInput, signal?: AbortSignal): Promise<Ticket> {
  return postJson<Ticket>('/api/tickets', payload, signal)
}

export async function getTicketStats(signal?: AbortSignal): Promise<TicketStats> {
  return getJson<TicketStats>('/api/tickets/stats', signal)
}

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

export const getTicket = (id: number, signal?: AbortSignal) => getJson<Ticket>(`/api/tickets/${id}`, signal)
export const updateTicket = (id: number, payload: Partial<TicketCreateInput>, signal?: AbortSignal) => patchJson<Ticket>(`/api/tickets/${id}`, payload, signal)
export async function getTicketCatalogs(ticket: Ticket, signal?: AbortSignal) {
  const [customer, circuit, sector, department, incidentType] = await Promise.all([
    getJson<Customer>(`/api/customers/${ticket.customer_id}`, signal),
    getJson<Circuit>(`/api/circuits/${ticket.circuit_id}`, signal),
    getJson<Sector>(`/api/sectors/${ticket.sector_id}`, signal),
    getJson<Department>(`/api/departments/${ticket.department_id}`, signal),
    getJson<IncidentType>(`/api/incident-types/${ticket.incident_type_id}`, signal),
  ])
  return { customer, circuit, sector, department, incidentType }
}
