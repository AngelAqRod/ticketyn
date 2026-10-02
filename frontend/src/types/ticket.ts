export type TicketStatus = 'OPEN' | 'CLOSED'

export interface Ticket {
  id: number
  ticket_number: number
  reference: string
  title: string
  description: string
  customer_id: number
  circuit_id: number
  sector_id: number
  department_id: number
  incident_type_id: number
  start_at: string
  end_at: string | null
  status: TicketStatus
  duration_seconds: number | null
  created_at: string
  updated_at: string
}
