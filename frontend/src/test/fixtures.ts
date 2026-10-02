import type { Ticket } from '../types/ticket'

export const ticket: Ticket = {
  id: 1, ticket_number: 3, reference: 'TEST-003', title: 'Sin conectividad',
  description: 'Revisión del circuito', customer_id: 1, circuit_id: 1, sector_id: 1,
  department_id: 1, incident_type_id: 1, start_at: '2026-01-01T12:00:00Z',
  end_at: null, status: 'OPEN', duration_seconds: null,
  created_at: '2026-01-01T12:00:00Z', updated_at: '2026-01-01T12:00:00Z',
}

export function jsonResponse(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
}
