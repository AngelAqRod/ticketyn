import { useRef } from 'react'
import type { AriaAttributes } from 'react'
import { X } from 'lucide-react'
import { SearchableSelect } from './SearchableSelect'
import type { SelectOption } from './SearchableSelect'

interface Props extends Pick<AriaAttributes, 'aria-describedby' | 'aria-invalid'> {
  id: string
  label: string
  value: string[]
  options: SelectOption[]
  onChange: (value: string[]) => void
  disabled?: boolean
  placeholder: string
}

/** Multiple assignments composed from the existing searchable combobox and chips. */
export function SearchableMultiSelect({ id, label, value, options, onChange, disabled = false, placeholder, 'aria-describedby': describedBy, 'aria-invalid': invalid }: Props) {
  const root = useRef<HTMLDivElement>(null)
  const selected = [...new Set(value)]
  const available = options.filter(option => !selected.includes(option.value))
  function focusSearch() { root.current?.querySelector<HTMLInputElement>('input[role="combobox"]')?.focus() }
  function remove(id: string) {
    if (disabled) return
    onChange(selected.filter(value => value !== id))
    focusSearch()
  }
  return <div ref={root} className="min-w-0">
    {selected.length > 0 && <ul className="mb-2 flex flex-wrap gap-2" aria-label={`${label}: personas seleccionadas`}>
      {selected.map(id => {
        const option = options.find(option => option.value === id)
        const name = option?.label ?? id
        return <li key={id} className="chip chip-primary max-w-full">
          <span className="min-w-0 whitespace-normal [overflow-wrap:anywhere]">{name}{option?.disabled && ' (Inactivo)'}</span>
          <button type="button" className="combobox-action" disabled={disabled} aria-label={`Quitar ${name}`} onClick={() => remove(id)}><X size={14} aria-hidden="true" /></button>
        </li>
      })}
    </ul>}
    <SearchableSelect id={id} label={label} value="" disabled={disabled} options={available}
      aria-describedby={describedBy} aria-invalid={invalid}
      placeholder={selected.length ? 'Buscar otra persona...' : placeholder}
      emptyMessage="No hay más personas disponibles para agregar." noMatchMessage="No se encontraron personas."
      onChange={id => {
        if (disabled || selected.includes(id) || !available.some(option => option.value === id && !option.disabled)) return
        onChange([...selected, id])
      }} />
    <span className="sr-only" role="status">{selected.length} personas seleccionadas</span>
    <button type="button" className="button-ghost mt-1" disabled={disabled || selected.length === 0} onClick={() => { onChange([]); focusSearch() }}>Limpiar {label.toLocaleLowerCase()}</button>
  </div>
}
