export interface NamedCatalog {
  id: number
  name: string
  active: boolean
  created_at: string
}

export interface Customer extends NamedCatalog {
  customer_code: string
}

export interface Circuit {
  node_id?: number | null
  node?: { id: number; name: string; active: boolean } | null
  id: number
  customer_id: number
  circuit_code: string
  description: string
  active: boolean
  created_at: string
}

export type Node = NamedCatalog
export interface Position extends NamedCatalog { department_id: number; description?: string | null; department: NamedCatalog }
export interface Responsible extends NamedCatalog {
  attention_level?: string | null // Preserved legacy value, read-only.
  department_id?: number | null; position_id?: number | null
  department?: NamedCatalog | null; position?: NamedCatalog | null
}
export interface ResponsibleInput extends NamedCatalogInput { department_id?: number | null; position_id?: number | null }
export interface PositionInput extends NamedCatalogInput { department_id: number }
export interface EscalationReason extends NamedCatalog { description?: string | null }
export type Sector = NamedCatalog
export type Department = NamedCatalog
export type IncidentType = NamedCatalog

export interface NamedCatalogInput { name: string; active: boolean; description?: string | null }
export interface CustomerInput extends NamedCatalogInput { customer_code: string }
export interface CircuitInput { node_id?: number | null; customer_id: number; circuit_code: string; description: string; active: boolean }
export type CatalogKind = 'customers' | 'circuits' | 'sectors' | 'departments' | 'incident-types' | 'nodes' | 'responsibles' | 'escalation-reasons' | 'positions'
