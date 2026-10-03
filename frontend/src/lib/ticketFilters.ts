import type { TicketQuery } from '../types/ticket'

export const ticketFilterKeys = ['search', 'status', 'customer_id', 'circuit_id', 'sector_id', 'department_id', 'incident_type_id', 'node_id', 'responsible_id', 'from', 'to'] as const
export const circuitFilterKeys = ['search', 'customer_id', 'node_id', 'active'] as const

export function localDateBoundary(value: string, nextDay = false): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) throw new Error('Introduce fechas válidas para Desde y Hasta.')
  const date = new Date(`${value}T00:00:00`)
  const pad = (part: number) => String(part).padStart(2, '0')
  if (Number.isNaN(date.getTime()) || `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` !== value) throw new Error('Introduce fechas válidas para Desde y Hasta.')
  // Calendario local: un día con cambio de horario puede durar 23 o 25 horas.
  if (nextDay) date.setDate(date.getDate() + 1)
  return date.toISOString()
}

export function ticketQuery(params: URLSearchParams): { query: TicketQuery; error: string | null } {
  const query: TicketQuery = {}
  for (const key of ['search', 'status'] as const) if (params.get(key)) query[key] = params.get(key)!
  for (const key of ['customer_id', 'circuit_id', 'sector_id', 'department_id', 'incident_type_id', 'node_id', 'responsible_id'] as const) if (params.get(key)) query[key] = Number(params.get(key))
  try {
    if (params.get('from')) query.from = localDateBoundary(params.get('from')!)
    if (params.get('to')) query.to = localDateBoundary(params.get('to')!, true)
    if (query.from && query.to && new Date(query.from) >= new Date(query.to)) throw new Error('Hasta debe ser igual o posterior a Desde.')
    return { query, error: null }
  } catch (failure) { return { query, error: failure instanceof Error ? failure.message : 'Rango de fechas inválido.' } }
}
