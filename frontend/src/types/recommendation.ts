export interface RecommendationItem {
  target_position_id: number
  target_position_name: string
  target_department_name: string
  threshold_minutes: number
  elapsed_minutes: number
  overdue_minutes: number
}

export interface AckResponse {
  id: number
  ticket_id: number
  duration_type: '1H' | '4H' | '8H' | 'INDEFINITE'
  reason: string
  active: boolean
  acknowledged_at: string
  expires_at: string | null
  acknowledged_by: { id: number; name: string; active: boolean }
  acknowledged_by_position?: { id: number; name: string; active: boolean } | null
  revoked_by?: { id: number; name: string; active: boolean } | null
  revoked_at?: string | null
  revoked_reason?: string | null
}

export interface TicketRecommendationsResponse {
  ticket_id: number
  ticket_status: string
  stage_name: string
  reference_position_id: number | null
  reference_position_name: string | null
  stage_started_at: string | null
  elapsed_minutes: number
  has_active_ack: boolean
  active_ack?: AckResponse | null
  can_acknowledge: boolean
  recommendations: RecommendationItem[]
}
