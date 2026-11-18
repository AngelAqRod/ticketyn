export interface AdminRequestInput {
  request_date: string
  requester_id: number
  customer_id: number | null
  circuit_id: number | null
  type_id: number
  description: string
  notes: string | null
  application_start: string | null
  application_end: string | null
}
export interface LinkedRecord { id: number; reference: string; title: string; date: string; link_id?: number }
export type LinkKind = 'ticket' | 'internal_ticket' | 'change'
export type AdminRequestStatus = 'REGISTERED' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED'
export const statusLabels: Record<AdminRequestStatus, string> = { REGISTERED: 'Registrada', IN_PROGRESS: 'En ejecución', COMPLETED: 'Completada', CANCELLED: 'Cancelada' }
// Mirrors TRANSITIONS in src/ticketyn/api/admin_requests.py; the backend is the authority.
export const statusTransitions: Record<AdminRequestStatus, AdminRequestStatus[]> = {
  REGISTERED: ['IN_PROGRESS', 'CANCELLED'], IN_PROGRESS: ['REGISTERED', 'COMPLETED', 'CANCELLED'], COMPLETED: ['REGISTERED', 'IN_PROGRESS'], CANCELLED: ['REGISTERED', 'IN_PROGRESS'],
}
export interface AdminRequest extends AdminRequestInput {
  id: number
  status: AdminRequestStatus
  reference: string
  created_at: string
  updated_at: string
  requester: { id: number; name: string }
  registered_by: { id: number; name: string }
  customer: { id: number; name: string } | null
  circuit: { id: number; circuit_code: string } | null
  type: { id: number; name: string }
  links: { tickets: LinkedRecord[]; internal_tickets: LinkedRecord[]; changes: LinkedRecord[] }
  events: { id: number; action: string; detail: Record<string, unknown>; actor_id: number; created_at: string }[]
}
export interface Paged<T> { total: number; items: T[] }
