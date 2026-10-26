export type MyTicketView = 'assigned' | 'participated' | 'escalations' | 'to_verify'

export type MyTicketScope = 'ALL' | 'CUSTOMER' | 'INTERNAL'

export interface MyTicketItem {
  id: number
  ticket_type: 'CUSTOMER' | 'INTERNAL'
  reference: string
  title: string
  description: string
  status: 'OPEN' | 'CLOSED'
  created_at: string
  start_at: string
  end_at: string | null

  // Responsible
  responsible_id: number | null
  responsible_name: string | null

  // Metadata
  sector_name: string | null
  node_name: string | null
  department_name: string | null
  incident_type_name: string | null

  // Customer
  customer_name: string | null
  customer_code: string | null
  circuit_code: string | null

  // Internal
  provider_name: string | null

  // Recommendations
  has_recommendation: boolean
  recommendations_count: number

  // Escalations
  escalation_id: number | null
  escalation_status: string | null
  escalation_reason: string | null
  escalation_started_at: string | null
  escalation_finished_at: string | null
  escalation_description: string | null
  escalation_requester_name: string | null
  escalation_recipient_name: string | null
  escalation_position_name: string | null

  // Verification details
  recommendation_stage: string | null
  recommendation_elapsed_minutes: number | null
  recommendation_threshold_minutes: number | null
  recommendation_overdue_minutes: number | null
  recommendation_target_position_name: string | null
  recommendation_reference_position_name: string | null
}

export interface MyTicketsListResponse {
  items: MyTicketItem[]
  total: number
  limit: number
  offset: number
}

export interface MyTicketsSummaryResponse {
  assigned_count: number
  participated_count: number
  escalations_count: number
  to_verify_count: number
}

export interface MyTicketsFilterParams {
  view?: MyTicketView
  scope?: MyTicketScope
  open_only?: boolean | null
  escalation_status?: 'ACTIVE' | 'FINISHED' | null
  search?: string
  limit?: number
  offset?: number
}
