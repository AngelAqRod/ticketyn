export interface NamedCatalog {
  id: number
  name: string
  active: boolean
  created_at: string
}

export interface Customer extends NamedCatalog {
  customer_code: string
}

export type ServiceType = NamedCatalog

export interface Circuit {
  cpe_model_id?: number | null
  cpe_model?: Pick<NamedCatalog, 'id' | 'name' | 'active'> | null
  sector_id?: number | null
  sector?: Pick<NamedCatalog, 'id' | 'name' | 'active'> | null
  service_type_id?: number | null
  service_type?: Pick<NamedCatalog, 'id' | 'name' | 'active'> | null
  initial_capacity?: string | null
  initial_capacity_unit?: string | null
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

export interface NamedCatalogInput { name: string; active: boolean; description?: string | null; applies_efficiency?: boolean }
export interface CustomerInput extends NamedCatalogInput { customer_code: string }
export interface CircuitInput { cpe_model_id?: number | null; sector_id: number; service_type_id?: number | null; initial_capacity?: string | null; initial_capacity_unit?: string | null; node_id: number; customer_id: number; circuit_code: string; description: string; active: boolean }
export type CatalogKind = 'change-types' | 'change-completion-types' | 'internal-incident-types' | 'providers' | 'cpe-models' | 'customers' | 'circuits' | 'sectors' | 'departments' | 'incident-types' | 'nodes' | 'responsibles' | 'escalation-reasons' | 'positions' | 'deactivation-reasons' | 'service-types'
