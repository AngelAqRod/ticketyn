import type { Circuit, NamedCatalog } from './catalog'
export type FmsKind = 'activations' | 'capacity-changes' | 'circuit-lifecycle'
export interface Operation {
  node_id?: number | null; node?: Pick<NamedCatalog, 'id' | 'name' | 'active'> | null
  sector_id?: number | null; sector?: Pick<NamedCatalog, 'id' | 'name' | 'active'> | null
  cpe_activation?: string | null; service_type_name?: string | null; initial_capacity?: string | null; initial_capacity_unit?: string | null
  id: number; circuit_id: number; circuit: Circuit; responsible_id: number; responsible: Pick<NamedCatalog, 'id' | 'name' | 'active'>
  effective_at: string; created_at: string; reference?: string; activation_number?: number
  operation_type?: 'INCREASE' | 'DECREASE' | 'DEACTIVATE' | 'REACTIVATE'
  previous_capacity?: string | null; previous_unit?: string | null; new_capacity?: string; new_unit?: string
  description?: string | null; observations?: string | null; reason?: Pick<NamedCatalog, 'id' | 'name' | 'active'> | null
}
export interface ActivationIntervention { id: number; activation_id: number; responsible: Pick<NamedCatalog, 'id' | 'name' | 'active'>; occurred_at: string; created_at: string; content: string }
export interface CircuitOperationalDetail { circuit: Circuit; customer: Pick<NamedCatalog, 'id' | 'name' | 'active'>; current_capacity: string | null; current_capacity_unit: string | null; initial_activation: Operation | null }
export const fmsTitles: Record<FmsKind, string> = { activations: 'Activaciones', 'capacity-changes': 'Cambios de capacidad', 'circuit-lifecycle': 'Bajas y Reactivaciones' }
export const operationLabel = (value?: string) => ({ INCREASE: 'Incremento', DECREASE: 'Decremento', DEACTIVATE: 'Baja', REACTIVATE: 'Reactivación' }[value ?? ''] ?? 'Activación')
export { formatCapacity as capacityLabel } from '../lib/capacity'
