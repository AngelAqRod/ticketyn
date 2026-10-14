import type { Sector } from '../types/catalog'
import { CircuitAssignmentField } from './CircuitAssignmentField'
import type { CircuitAssignmentProps } from './CircuitAssignmentField'

export function CircuitSectorField({ sectors, ...props }: Omit<CircuitAssignmentProps, 'options'> & { sectors: Sector[] }) {
  return <CircuitAssignmentField {...props} field="sector" options={sectors} />
}
