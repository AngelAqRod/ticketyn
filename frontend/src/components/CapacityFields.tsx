import { FormField } from './FormField'
export function CapacityFields({ id, label, value, unit, onChange, required = false }: { id: string; label: string; value: string; unit: string; onChange: (value: string, unit: string) => void; required?: boolean }) {
  return <div className="grid min-w-0 gap-2 sm:grid-cols-2">
    <FormField id={id} label={label} required={required}><input id={id} type="number" min="0.000001" step="0.000001" className="form-input" required={required} value={value} onChange={(event) => onChange(event.target.value, unit)} /></FormField>
    <FormField id={`${id}-unit`} label={`Unidad de ${label.toLowerCase()}`}><select id={`${id}-unit`} className="form-input" value={unit} onChange={(event) => onChange(value, event.target.value)}><option>Mbps</option><option>Gbps</option></select></FormField>
  </div>
}
