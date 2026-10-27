import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'
import { FilterChips, type FilterChipItem } from './FilterChips'

export type FilterBarTheme = 'blue' | 'purple' | 'amber' | 'emerald' | 'slate' | 'cyan'

interface Props {
  /** Nombre accesible de la región (p. ej. «Filtros de tickets»). */
  label: string
  /** Identidad del módulo: acento del borde superior, foco, control abierto y contador. */
  theme?: FilterBarTheme
  /** Primera fila: búsqueda y hasta dos filtros rápidos específicos. */
  search?: ReactNode
  quick?: ReactNode
  /** Segunda fila: estado, atajos y período. */
  primary?: ReactNode
  /** Filtros avanzados (usar `FilterPanelGroup`). Siempre montados: plegar no pierde valores. */
  panel?: ReactNode
  /** Filtros avanzados activos; es lo que muestra «Filtros (n)». */
  panelCount?: number
  /** Todos los filtros activos, visibles aunque el panel esté plegado. */
  chips: FilterChipItem[]
  onClear: () => void
}

/**
 * Estructura visual común de filtros. Solo distribuye y pliega: valores, URL, dependencias y consultas
 * son responsabilidad del módulo que la usa.
 */
export function FilterBar({ label, theme = 'blue', search, quick, primary, panel, panelCount = 0, chips, onClear }: Props) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const toggle = useRef<HTMLButtonElement>(null)
  function onPanelKey(event: KeyboardEvent) {
    if (event.key !== 'Escape') return
    event.stopPropagation(); setOpen(false); toggle.current?.focus()
  }
  return <section aria-label={label} className={`filter-toolbar filter-bar filter-bar--${theme}`}>
    <div className="filter-bar-row">
      {search && <div className="filter-bar-search">{search}</div>}
      {quick}
      {panel && <button ref={toggle} type="button" className={`button-secondary rounded-full filter-bar-toggle ${panelCount > 0 ? 'filter-bar-toggle--active' : ''}`} aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(!open)}>
        Filtros{panelCount > 0 ? ` (${panelCount})` : ''}
        <ChevronDown size={14} className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>}
    </div>
    {primary && <div className="filter-bar-row filter-bar-row--primary">{primary}</div>}
    {panel && <div id={panelId} role="group" aria-label="Filtros avanzados" hidden={!open} className="filter-bar-panel" onKeyDown={onPanelKey}>{panel}</div>}
    <FilterChips items={chips} theme={theme} action={chips.length > 0 ? <button type="button" className="filter-bar-clear" onClick={onClear}>Limpiar todo</button> : undefined} />
  </section>
}

export function FilterPanelGroup({ title, children }: { title: string; children: ReactNode }) {
  return <fieldset className="filter-bar-group"><legend>{title}</legend>{children}</fieldset>
}

/** Segmentado de un solo valor (p. ej. Estado) con el color del módulo; el valor activo se anuncia con aria-pressed. */
export function FilterSegment({ label, options, value, onChange }: { label: string; options: readonly (readonly [string, string])[]; value: string; onChange: (value: string) => void }) {
  return <div className="segmented-control segmented-control--soft filter-bar-segment" role="group" aria-label={label}>
    {options.map(([option, text]) => <button key={text} type="button" className="segment-button" aria-pressed={value === option} onClick={() => onChange(option)}>{text}</button>)}
  </div>
}
