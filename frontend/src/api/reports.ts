import { getJson, downloadFile } from './client'
import type { ReportQuery, ReportSummary } from '../types/report'
export function reportParams(query: ReportQuery): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) if (value !== undefined) params.set(key, String(value))
  return params.toString()
}
export const getReport = (query: ReportQuery, signal?: AbortSignal) => getJson<ReportSummary>(`/api/reports/summary?${reportParams(query)}`, signal)
export const reportExportUrl = (format: 'pdf' | 'xlsx', query: ReportQuery) => `/api/reports/export/${format}?${reportParams(query)}`
export const downloadReport = (format: 'pdf' | 'xlsx', query: ReportQuery) => downloadFile(reportExportUrl(format, query), `ticketyn-${query.node_id ? 'nodo' : query.responsible_id ? 'responsable' : query.sector_id ? 'sector' : 'general'}.${format}`)
