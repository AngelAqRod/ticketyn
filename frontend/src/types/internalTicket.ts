import type { TicketStatus } from './ticket'
import type { NamedCatalog } from './catalog'
type CatalogReference = Pick<NamedCatalog, 'id' | 'name' | 'active'>
export interface InternalTicket {
  id: number; ticket_number: number; reference: string; title: string; description: string
  sector_id: number; node_id: number | null; department_id: number; incident_type_id: number
  responsible_id: number | null; provider_id: number | null; resolution: string | null
  start_at: string; end_at: string | null; status: TicketStatus; duration_seconds: number | null
  created_at: string; updated_at: string; related_count: number
  sector: CatalogReference; node: CatalogReference | null; department: CatalogReference; incident_type: CatalogReference
  responsible: CatalogReference | null; provider: CatalogReference | null
}
