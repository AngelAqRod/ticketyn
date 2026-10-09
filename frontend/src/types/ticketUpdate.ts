export type TicketUpdateVisibility = 'INTERNAL' | 'PUBLIC'

export interface TicketUpdate {
  id: number
  ticket_id: number
  escalation_id?: number | null
  content: string
  occurred_at: string
  created_at: string
  responsible_id: number | null
  responsible: { id: number; name: string; active: boolean } | null
  visibility: TicketUpdateVisibility
}

export interface TicketUpdateCreate {
  escalation_id?: number | null
  content: string
  occurred_at?: string
  responsible_id?: number | null
  visibility?: TicketUpdateVisibility
}
