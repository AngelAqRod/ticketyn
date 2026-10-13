import type { NamedCatalog, EscalationReason } from './catalog'
import type { ReportRanking, ReportSummary } from './report'
export interface Escalation {
  id: number; ticket_id: number; requester_id: number | null; recipient_id: number | null; department_id: number | null; started_at: string; updated_at: string; reason_id: number
  requester: NamedCatalog | null; recipient: NamedCatalog | null; reason: EscalationReason; recipient_level: string | null; recipient_position_name?: string | null; recipient_department_name?: string | null
  description: string; status: 'ACTIVE' | 'FINISHED'; created_at: string; finished_at: string | null
}
export interface EscalationInput { requester_id?: number | null; recipient_id?: number | null; department_id: number; started_at: string; reason_id: number; description: string }
export interface EscalationSummary {
  total_tickets: number; escalated_tickets: number; events: number; active: number; finished: number
  average_duration_seconds: number | null; escalated_percentage: number; granularity: string
  departments?: (Omit<ReportRanking, 'id'> & { id: number | null })[]; event_tickets?: number; trend: ReportSummary['trend']; recipients: (Omit<ReportRanking, 'id'> & { id: number | null })[]
}
export interface EscalationTicket { id: number; reference: string; title: string; status: string }
