import type { ReactNode } from 'react'
import { X } from 'lucide-react'

export interface FilterChipItem {
  label: string
  value: string
  /** Si se define, el filtro puede quitarse desde su chip. */
  onRemove?: () => void
}

export function FilterChips({
  items,
  theme = 'blue',
  action,
}: {
  items: FilterChipItem[]
  /** Acción al final de la fila (p. ej. «Limpiar todo»). */
  action?: ReactNode
  theme?: 'blue' | 'purple' | 'amber' | 'emerald' | 'slate' | 'cyan'
}) {
  if (!items.length) return null
  const chipClass =
    theme === 'purple'
      ? 'chip chip-purple'
      : theme === 'cyan'
      ? 'chip chip-cyan'
      : theme === 'amber'
      ? 'chip chip-amber'
      : theme === 'emerald'
      ? 'chip chip-emerald'
      : theme === 'slate'
      ? 'chip chip-slate'
      : 'chip chip-primary'
  return (
    <div aria-label="Filtros activos" className="mt-3 flex flex-wrap items-center gap-2">
      <span className="text-xs font-semibold text-muted">Filtros activos</span>
      {items.map(({ label, value, onRemove }) => (
        <span
          key={label}
          className={`${chipClass} max-w-full`}
          title={`${label}: ${value}`}
        >
          <span className="max-w-72 truncate">
            {label}: {value}
          </span>
          {onRemove && (
            <button type="button" className="-mr-1 rounded-full p-0.5 hover:bg-white/10" aria-label={`Quitar filtro ${label}: ${value}`} onClick={onRemove}>
              <X size={12} aria-hidden="true" />
            </button>
          )}
        </span>
      ))}
      {action}
    </div>
  )
}
