import { getJson, postJson, patchJson, deleteResource, ApiError } from './client'
import type { Ticket, TicketCreateInput, TicketStats, TicketQuery } from '../types/ticket'
import type { Position, PositionInput, ResponsibleInput, EscalationReason, Node, Responsible, Circuit, Customer, Department, IncidentType, Sector, CustomerInput, CircuitInput, NamedCatalogInput } from '../types/catalog'

async function catalogList<T>(path: string, signal?: AbortSignal, filters: Record<string, string> = {}, includeInactive = false): Promise<T[]> {
  const items: T[] = []
  for (let offset = 0; ; offset += 200) {
    const query = new URLSearchParams({ ...filters, include_inactive: String(includeInactive), limit: '200', offset: String(offset) })
    const page = await getJson<T[]>(`${path}?${query}`, signal)
    if (!Array.isArray(page)) throw new ApiError('La API no devolvió un catálogo válido.')
    items.push(...page)
    if (page.length < 200) return items
  }
}

export const listCustomers = (signal?: AbortSignal, includeInactive = false) => catalogList<Customer>('/api/customers', signal, {}, includeInactive)
export const listSectors = (signal?: AbortSignal, includeInactive = false) => catalogList<Sector>('/api/sectors', signal, {}, includeInactive)
export const listDepartments = (signal?: AbortSignal, includeInactive = false) => catalogList<Department>('/api/departments', signal, {}, includeInactive)
export const listIncidentTypes = (signal?: AbortSignal, includeInactive = false) => catalogList<IncidentType>('/api/incident-types', signal, {}, includeInactive)
export const listCircuits = (customerId?: number, signal?: AbortSignal, includeInactive = false, filters: { search?: string; active?: boolean; node_id?: number } = {}) =>
  catalogList<Circuit>('/api/circuits', signal, { ...(customerId === undefined ? {} : { customer_id: String(customerId) }), ...(filters.node_id === undefined ? {} : { node_id: String(filters.node_id) }), ...(filters.search ? { search: filters.search } : {}), ...(filters.active !== undefined ? { active: String(filters.active) } : {}) }, includeInactive)

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
  { limit = 50, offset = 0, ...filters }: TicketQuery = {},
  signal?: AbortSignal,
): Promise<Ticket[]> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  for (const [key, value] of Object.entries(filters)) if (value !== undefined && value !== '') query.set(key, String(value))
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
  const responsible = ticket.responsible_id ? await getJson<Responsible>(`/api/responsibles/${ticket.responsible_id}`, signal) : null
  return { customer, circuit, sector, department, incidentType, responsible, node: circuit.node ?? null }
}

export const createCustomer = (payload: CustomerInput, signal?: AbortSignal) => postJson<Customer>('/api/customers', payload, signal)
export const updateCustomer = (id: number, payload: Partial<CustomerInput>, signal?: AbortSignal) => patchJson<Customer>(`/api/customers/${id}`, payload, signal)

export const createCircuit = (payload: CircuitInput, signal?: AbortSignal) => postJson<Circuit>('/api/circuits', payload, signal)
export const updateCircuit = (id: number, payload: Partial<CircuitInput>, signal?: AbortSignal) => patchJson<Circuit>(`/api/circuits/${id}`, payload, signal)

export const createSector = (payload: NamedCatalogInput, signal?: AbortSignal) => postJson<Sector>('/api/sectors', payload, signal)
export const updateSector = (id: number, payload: Partial<NamedCatalogInput>, signal?: AbortSignal) => patchJson<Sector>(`/api/sectors/${id}`, payload, signal)

export const createDepartment = (payload: NamedCatalogInput, signal?: AbortSignal) => postJson<Department>('/api/departments', payload, signal)
export const updateDepartment = (id: number, payload: Partial<NamedCatalogInput>, signal?: AbortSignal) => patchJson<Department>(`/api/departments/${id}`, payload, signal)

export const createIncidentType = (payload: NamedCatalogInput, signal?: AbortSignal) => postJson<IncidentType>('/api/incident-types', payload, signal)
export const updateIncidentType = (id: number, payload: Partial<NamedCatalogInput>, signal?: AbortSignal) => patchJson<IncidentType>(`/api/incident-types/${id}`, payload, signal)

export const listNodes = (signal?: AbortSignal, includeInactive = false) => catalogList<Node>("/api/nodes", signal, {}, includeInactive)
export const listResponsibles = (signal?: AbortSignal, includeInactive = false) => catalogList<Responsible>("/api/responsibles", signal, {}, includeInactive)
export const createNode = (payload: NamedCatalogInput, signal?: AbortSignal) => postJson<Node>("/api/nodes", payload, signal)
export const updateNode = (id: number, payload: Partial<NamedCatalogInput>, signal?: AbortSignal) => patchJson<Node>(`/api/nodes/${id}`, payload, signal)
export const createResponsible = (payload: ResponsibleInput, signal?: AbortSignal) => postJson<Responsible>("/api/responsibles", payload, signal)
export const updateResponsible = (id: number, payload: Partial<ResponsibleInput>, signal?: AbortSignal) => patchJson<Responsible>(`/api/responsibles/${id}`, payload, signal)

export const deleteCustomer = (id: number, signal?: AbortSignal) => deleteResource(`/api/customers/${id}`, signal)
export const deleteCircuit = (id: number, signal?: AbortSignal) => deleteResource(`/api/circuits/${id}`, signal)

export const listEscalationReasons = (signal?: AbortSignal, includeInactive = false) => catalogList<EscalationReason>('/api/escalation-reasons', signal, {}, includeInactive)
export const createEscalationReason = (payload: NamedCatalogInput, signal?: AbortSignal) => postJson<EscalationReason>('/api/escalation-reasons', payload, signal)
export const updateEscalationReason = (id: number, payload: Partial<NamedCatalogInput>, signal?: AbortSignal) => patchJson<EscalationReason>(`/api/escalation-reasons/${id}`, payload, signal)

export const listPositions = (signal?: AbortSignal, includeInactive = false, departmentId?: number) => catalogList<Position>('/api/positions', signal, departmentId === undefined ? {} : { department_id: String(departmentId) }, includeInactive)
export const createPosition = (payload: PositionInput, signal?: AbortSignal) => postJson<Position>('/api/positions', payload, signal)
export const updatePosition = (id: number, payload: Partial<PositionInput>, signal?: AbortSignal) => patchJson<Position>(`/api/positions/${id}`, payload, signal)
