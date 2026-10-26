export interface NamedCatalog {
  id: number
  name: string
  active: boolean
  created_at: string
  operational_selectable?: boolean
}

export interface Customer extends NamedCatalog {
  customer_code: string
}

export type ServiceType = NamedCatalog

export interface DistributionDevice extends NamedCatalog {
  node_id: number
  description: string | null
  port_count: number
  circuit_count: number
}
export interface DistributionPort extends NamedCatalog {
  distribution_device_id: number
  description: string | null
  circuit_count: number
}
export type DistributionSummary = Pick<NamedCatalog, 'id' | 'name' | 'active'>

export interface Circuit {
  cpe_management_ip?: string | null
  distribution_device_id?: number | null
  distribution_port_id?: number | null
  distribution_device?: DistributionSummary | null
  distribution_port?: DistributionSummary | null
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
export interface PositionDestination {
  id: number
  target_position_id: number
  target_position_name: string
  target_department_name: string
  time_minutes: number | null
  order_index: number
  active: boolean
}

export interface PositionDestinationInput {
  target_position_id: number
  time_minutes?: number | null
}

export interface Position extends NamedCatalog {
  department_id: number
  description?: string | null
  department: NamedCatalog
  escalation_mode?: 'GENERAL' | 'INDIVIDUAL'
  general_escalation_time_minutes?: number | null
  destinations?: PositionDestination[]
}
export interface Responsible extends NamedCatalog {
  can_change_active?: boolean | null
  attention_level?: string | null // Preserved legacy value, read-only.
  department_id?: number | null; position_id?: number | null
  department?: NamedCatalog | null; position?: NamedCatalog | null
}
export interface ResponsibleInput extends NamedCatalogInput { operational_selectable?: boolean; department_id?: number | null; position_id?: number | null }
export interface PositionInput extends NamedCatalogInput {
  department_id: number
  escalation_mode?: 'GENERAL' | 'INDIVIDUAL'
  general_escalation_time_minutes?: number | null
  destinations?: PositionDestinationInput[] | null
}
export interface EscalationReason extends NamedCatalog { description?: string | null }
export type Sector = NamedCatalog
export type Department = NamedCatalog
export type IncidentType = NamedCatalog

export interface NamedCatalogInput { name: string; active: boolean; description?: string | null; applies_efficiency?: boolean }
export interface CustomerInput extends NamedCatalogInput { customer_code: string }
export interface CircuitInput { cpe_management_ip?: string | null; distribution_device_id?: number | null; distribution_port_id?: number | null; cpe_model_id?: number | null; sector_id: number; service_type_id?: number | null; initial_capacity?: string | null; initial_capacity_unit?: string | null; node_id: number; customer_id: number; circuit_code: string; description: string; active: boolean }
export type CatalogKind = 'change-types' | 'change-completion-types' | 'internal-incident-types' | 'providers' | 'cpe-models' | 'customers' | 'circuits' | 'sectors' | 'departments' | 'incident-types' | 'nodes' | 'responsibles' | 'escalation-reasons' | 'positions' | 'deactivation-reasons' | 'service-types'
