import type { ReportSummary, ReportRanking } from './report'
export interface FmsReportSummary {
  generated_at: string; period: ReportSummary['period']
  sector: { id: number; name: string } | null; node: { id: number; name: string } | null; responsible: { id: number; name: string } | null
  kpis: { total?: number; distinct_customers?: number; distinct_circuits?: number; increases?: number; decreases?: number; known_added_mbps?: string; known_reduced_mbps?: string; known_net_mbps?: string; unknown_variations?: number; deactivations?: number; reactivations?: number; distinct_deactivated_circuits?: number; distinct_reactivated_circuits?: number }
  trend: { start_at: string; count: number; first: number; second: number }[]
  customers: ReportRanking[]; reasons: ReportRanking[]
}
