import { getJson, patchJson } from './client'

export interface AuditPerson { id: number; name: string; username: string | null }
export interface AuditEntry {
  id: number; occurred_at: string; actor: AuditPerson | null; target: AuditPerson | null
  identifier: string | null; event: string; event_label: string; source: string; success: boolean
  details: { label: string; value: string }[]
}
export interface AuditPage {
  items: AuditEntry[]; total: number; limit: number; offset: number
  events: { code: string; label: string }[]
}
export function getSecurityAudit(query: string, signal: AbortSignal) {
  return getJson<AuditPage>(`/api/security/audit?${query}`, signal)
}

export interface AuditRetention { retention_days: number }
export function getAuditRetention(signal: AbortSignal) {
  return getJson<AuditRetention>('/api/security/audit/retention', signal)
}
export function saveAuditRetention(retention_days: number, expected_days: number, confirm_reduction: boolean, signal: AbortSignal) {
  return patchJson<AuditRetention>('/api/security/audit/retention', { retention_days, expected_days, confirm_reduction }, signal)
}
