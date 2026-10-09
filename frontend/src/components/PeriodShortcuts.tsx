export const periodLabel = (value: string) => value === 'all' ? 'Todos' : value === '1' ? 'Hoy' : value === 'yesterday' ? 'Ayer' : value === 'custom' ? 'Personalizado' : `${value}D`

export function PeriodShortcuts({ value, onChange, label, includeAll = false }: { value: string; onChange: (value: string) => void; label: string; includeAll?: boolean }) {
  return <div className="segmented-control max-w-full flex-wrap" role="group" aria-label={label}>
    {[...(includeAll ? ['all'] : []), '1', 'yesterday', '7', '15', '30', 'custom'].map((option) => <button key={option} type="button" className="segment-button" aria-label={!includeAll && ['7', '15', '30'].includes(option) ? `${option} días` : periodLabel(option)} aria-pressed={value === option} onClick={() => onChange(option)}>{periodLabel(option)}</button>)}
  </div>
}
