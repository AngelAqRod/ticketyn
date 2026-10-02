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
  id: number
  customer_id: number
  circuit_code: string
  description: string
  active: boolean
  created_at: string
}

export type Sector = NamedCatalog
export type Department = NamedCatalog
export type IncidentType = NamedCatalog
