export type TicketStatus = 'OPEN' | 'CLOSED'

export interface TicketStats {
  total: number
  open: number
  closed: number
}

export interface TicketCreateInput {
  resolution?: string | null
  customer_description?: string | null
  customer_resolution?: string | null
  responsible_id?: number | null
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
}

export interface TicketQuery {
  node_id?: number
  responsible_id?: number
  search?: string
  status?: string
  customer_id?: number
  circuit_id?: number
  sector_id?: number
  department_id?: number
  incident_type_id?: number
  from?: string
  to?: string
  limit?: number
  offset?: number
}

export interface Ticket {
  resolution?: string | null
  customer_description?: string | null
  customer_resolution?: string | null
  responsible_id?: number | null
  responsible?: { id: number; name: string; active: boolean } | null
  node?: { id: number; name: string; active: boolean } | null
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
  customer?: { id: number; customer_code: string; name: string }
  circuit?: { id: number; circuit_code: string; description: string }
  sector?: { id: number; name: string }
  department?: { id: number; name: string }
  incident_type?: { id: number; name: string }
}
