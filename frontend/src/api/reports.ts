import { getJson, downloadFile } from './client'
import type { ReportQuery, ReportSummary } from '../types/report'
export function reportParams(query: ReportQuery): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) if (value !== undefined) params.set(key, String(value))
  return params.toString()
}
export const getReport = (query: ReportQuery, signal?: AbortSignal, internal = false) => getJson<ReportSummary>(`/api/reports/${internal ? 'internal-tickets/' : ''}summary?${reportParams(query)}`, signal)
export const reportExportUrl = (format: 'pdf' | 'xlsx', query: ReportQuery, internal = false) => `/api/reports/${internal ? 'internal-tickets/' : ''}export/${format}?${reportParams(query)}`
export const downloadReport = (format: 'pdf' | 'xlsx', query: ReportQuery, internal = false) => downloadFile(reportExportUrl(format, query, internal), `ticketyn-${internal ? 'tickets-internos' : query.node_id ? 'nodo' : query.responsible_id ? 'responsable' : query.sector_id ? 'sector' : 'general'}.${format}`)
