import { SlidersHorizontal } from 'lucide-react'

export function FilterHeading({
  title,
  theme = 'blue',
  className = '',
}: {
  title: string
  theme?: 'blue' | 'purple' | 'amber' | 'emerald' | 'slate' | 'cyan'
  className?: string
}) {
  return (
    <div className={`toolbar-heading flex items-center gap-2.5 ${className}`}>
      <span className={`icon-surface icon-surface--${theme}`} aria-hidden="true">
        <SlidersHorizontal size={14} />
      </span>
      <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
        {title}
      </h2>
    </div>
  )
}
