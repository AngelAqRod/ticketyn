export type TicketStatus = 'OPEN' | 'CLOSED'

export interface TicketStats {
  total: number
  open: number
  closed: number
}

export interface TicketCreateInput {
  internal_ticket_id?: number | null
  node_id?: number
  resolution?: string | null
  customer_description?: string | null
  customer_resolution?: string | null
  responsible_id?: number | null
  title: string
  description: string
  customer_id: number
  circuit_id: number
  sector_id?: number
  department_id: number
  incident_type_id: number
  start_at: string
  end_at: string | null
  status: TicketStatus
}

export type AgeBucket = 'lt_1h' | '1_to_4h' | '4_to_24h' | 'gt_24h'

/** GET /api/tickets/open-overview: abiertos por antigüedad (excluyentes), sin responsable (transversal) y por sector. */
export interface OpenOverview {
  generated_at: string
  open: number
  buckets: Record<AgeBucket, number>
  future_start: number
  unassigned: number
  sectors: { id: number; name: string; count: number }[]
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
  age_bucket?: AgeBucket
  unassigned?: boolean
  order?: 'start_at_asc' | 'start_at_desc'
  from?: string
  to?: string
  limit?: number
  offset?: number
}

export interface Ticket {
  internal_ticket_id?: number | null
  node_id?: number | null
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
