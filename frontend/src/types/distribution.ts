import type { NamedCatalog } from './catalog'

export interface DistributionDevice extends NamedCatalog {
  node_id: number
  description: string | null
  port_count: number
  unassigned_port_count?: number
  circuit_count: number
}

export interface DistributionPort extends NamedCatalog {
  distribution_device_id: number
  nomenclature_id?: number | null
  numbering_format?: string | null
  number_components?: number[] | null
  description: string | null
  circuit_count: number
}

export type DistributionSummary = Pick<NamedCatalog, 'id' | 'name' | 'active'>

export interface DistributionCircuit {
  id: number
  circuit_code: string
  description: string
  active: boolean
  customer_id: number
  customer_code: string
  customer_name: string
  service_type_id: number | null
  service_type_name: string | null
  distribution_port_id: number | null
  distribution_port_name: string | null
}

export interface DeviceCreateInput {
  node_id: number
  name: string
  description?: string | null
  template_id?: number
  template_token?: string
}

export type PortCreateInput = import('../api/portNomenclatures').PortGeneration

export interface DistributionEditInput {
  name?: string
  description?: string | null
}

export interface DeviceMoveInput {
  node_id: number
}

export interface PortMoveInput {
  distribution_device_id: number
}

export interface DistributionStatusInput {
  active: boolean
}

export interface DistributionDeviceFilter {
  node_id?: number
  search?: string
  active?: boolean
  include_inactive?: boolean
  limit?: number
  offset?: number
}

export interface DistributionPortFilter {
  distribution_device_id?: number
  search?: string
  active?: boolean
  include_inactive?: boolean
  limit?: number
  offset?: number
}
