import type { Circuit, NamedCatalog } from '../types/catalog'
import { FormField } from './FormField'

export interface CircuitAssignmentProps {
  id: string; circuit?: Circuit; options: Pick<NamedCatalog, 'id' | 'name' | 'active'>[]; value: string;
  onChange: (value: string) => void; disabled?: boolean; describedBy?: string; invalid?: boolean;
  persistedName?: string | null;
}

/** Only an unassigned circuit exposes an editable selector. */
export function CircuitAssignmentField({ id, circuit, options, value, onChange, disabled = false, describedBy, invalid, field, persistedName }: CircuitAssignmentProps & { field: 'node' | 'sector' }) {
  const label = field === 'node' ? 'Nodo' : 'Sector'
  const assigned = circuit?.[`${field}_id`]
  const displayName = persistedName ?? circuit?.[field]?.name ?? options.find(item => item.id === assigned)?.name ?? `${label} asignado`
  return <FormField id={id} label={label} required describedBy={describedBy} invalid={invalid}>
    {assigned ? <input id={id} className="form-input" readOnly value={displayName} /> :
      <select id={id} className="form-input" required disabled={disabled || !circuit} value={value} onChange={event => onChange(event.target.value)}><option value="">Selecciona un {label.toLowerCase()}</option>{options.filter(item => item.active).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>}
  </FormField>
}
