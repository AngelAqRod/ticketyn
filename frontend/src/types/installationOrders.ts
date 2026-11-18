export interface InstallationPerson { id: number; name: string }
export interface InstallationDocument { id: number; original_name: string; media_type: string; size: number; checksum: string; created_at: string }
export interface InstallationEvent { id: number; action: string; detail: Record<string, unknown>; created_at: string; actor_id?: number | null; actor?: InstallationPerson | null }
export type InstallationOrderType = 'NORMAL' | 'EXTRAORDINARY'
export const orderTypeLabels: Record<InstallationOrderType, string> = { NORMAL: 'Normal', EXTRAORDINARY: 'Extraordinaria' }
export interface InstallationOrderInput { order_type: InstallationOrderType; customer_id: number; requested_at: string; external_reference?: string | null; contact?: string | null; phone?: string | null; notes?: string | null; circuit_id?: number | null; description?: string | null; service_type_id?: number | null; node_id?: number | null; sector_id?: number | null }
export type NamedRef = { id: number; name: string }
export interface OrderTechnical { service_type: NamedRef | null; node: NamedRef | null; sector: NamedRef | null; device: NamedRef | null; port: NamedRef | null; cpe: NamedRef | null }
// order_type null = legacy order created before the modalities existed; it is never classified automatically.
export interface InstallationOrder extends Omit<InstallationOrderInput, 'order_type'> { id: number; reference: string; order_type: InstallationOrderType | null; service?: string | null; location?: string | null; technical: OrderTechnical | null; circuit_location?: { address: string | null; latitude: string | null; longitude: string | null; additional_notes: string | null } | null; customer: InstallationPerson; author: InstallationPerson; circuit: {id: number; circuit_code: string} | null; source_request_id: number | null; source_request?: {sender:string;subject:string;received_at:string;body:string;message_id:string|null}|null; documents: InstallationDocument[]; events: InstallationEvent[]; created_at: string; updated_at: string }
export type InstallationState = 'PENDING' | 'REVIEWING' | 'PROCESSED' | 'DISCARDED'
export interface InstallationRequest { id: number; sender: string; subject: string; body: string; received_at: string; message_id: string | null; state: InstallationState; reviewer: InstallationPerson | null; order_id: number | null; has_draft: boolean; attachment_count: number; draft: {data: Partial<InstallationOrderInput>; version: number} | null; documents: InstallationDocument[]; events: InstallationEvent[]; discard_reason?: string | null }
export interface InstallationSummary { pending: number; reviewing: number; processed: number; discarded: number; to_attend: number }
export const installationStates: Record<InstallationState, string> = { PENDING: 'Pendiente', REVIEWING: 'En revisión', PROCESSED: 'Procesada', DISCARDED: 'Descartada' }

export interface ReceptionFilters { senders: string[]; subjects: string[] }
