export function FilterChips({ items }: { items: { label: string; value: string }[] }) {
  if (!items.length) return null
  return <div aria-label="Filtros activos" className="mt-3 flex flex-wrap items-center gap-2">
    <span className="text-[10px] font-semibold text-muted">Filtros activos</span>
    {items.map(({ label, value }) => <span key={label} className="chip chip-primary max-w-full" title={`${label}: ${value}`}><span className="max-w-72 truncate">{label}: {value}</span></span>)}
  </div>
}
