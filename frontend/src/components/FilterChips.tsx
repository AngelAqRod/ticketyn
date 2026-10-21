export interface FilterChipItem {
  label: string
  value: string
}

export function FilterChips({
  items,
  theme = 'blue',
}: {
  items: FilterChipItem[]
  theme?: 'blue' | 'purple' | 'amber' | 'emerald' | 'slate'
}) {
  if (!items.length) return null
  const chipClass =
    theme === 'purple'
      ? 'chip chip-purple'
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
      {items.map(({ label, value }) => (
        <span
          key={label}
          className={`${chipClass} max-w-full`}
          title={`${label}: ${value}`}
        >
          <span className="max-w-72 truncate">
            {label}: {value}
          </span>
        </span>
      ))}
    </div>
  )
}
