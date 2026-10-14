export const periodLabel = (value: string) => value === 'all' ? 'Todos' : value === '1' ? 'Hoy' : value === 'yesterday' ? 'Ayer' : value === 'custom' ? 'Personalizado' : `${value}D`

export function PeriodShortcuts({ value, onChange, label, includeAll = false, labels = {} }: { value: string; onChange: (value: string) => void; label: string; includeAll?: boolean; labels?: Record<string, string> }) {
  return <div className="segmented-control max-w-full flex-wrap" role="group" aria-label={label}>
    {[...(includeAll ? ['all'] : []), '1', 'yesterday', '7', '15', '30', 'custom'].map((option) => <button key={option} type="button" className="segment-button" aria-label={labels[option] ?? (!includeAll && ['7', '15', '30'].includes(option) ? `${option} días` : periodLabel(option))} aria-pressed={value === option} onClick={() => onChange(option)}>{labels[option] ?? periodLabel(option)}</button>)}
  </div>
}
