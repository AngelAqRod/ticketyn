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
export type Responsible = NamedCatalog
export type Sector = NamedCatalog
export type Department = NamedCatalog
export type IncidentType = NamedCatalog

export interface NamedCatalogInput { name: string; active: boolean }
export interface CustomerInput extends NamedCatalogInput { customer_code: string }
export interface CircuitInput { node_id?: number | null; customer_id: number; circuit_code: string; description: string; active: boolean }
export type CatalogKind = 'customers' | 'circuits' | 'sectors' | 'departments' | 'incident-types' | 'nodes' | 'responsibles'
