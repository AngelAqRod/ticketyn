import type { EscalationSummary } from './escalation'
export interface ReportRanking { id: number; label: string; count: number; customer_id: number | null; customer_code: string | null; customer_name: string | null }
export interface ReportSummary {
  escalations?: EscalationSummary | null
  node?: { id: number; name: string } | null
  responsible?: { id: number; name: string } | null
  nodes?: ReportRanking[]
  responsibles?: ReportRanking[]
  activity?: { start_at: string; started: number; closed: number }[]
  hours?: ReportRanking[]
  weekdays?: ReportRanking[]
  departments?: ReportRanking[]
  department_durations?: { id: number; label: string; count: number; average_duration_seconds: number }[]
  sector_durations?: { id: number; label: string; count: number; average_duration_seconds: number }[]
  period: { from_at: string | null; to_exclusive: string | null; timezone: string; granularity: 'hour' | 'day' | 'week' | 'month' }
  generated_at: string
  sector: { id: number; name: string } | null
  kpis: { started: number; closed: number; average_duration_seconds: number | null; total_duration_seconds: number }
  trend: { start_at: string; count: number }[]
  sectors: ReportRanking[]; customers: ReportRanking[]; circuits: ReportRanking[]; incident_types: ReportRanking[]
}
export interface ReportQuery { from?: string; to?: string; recipient_id?: number; timezone: string; sector_id?: number; node_id?: number; responsible_id?: number; granularity?: string }
