import { SlidersHorizontal } from 'lucide-react'

export function FilterHeading({ title, className = '' }: { title: string; className?: string }) {
  return <p className={`toolbar-heading gap-3 ${className}`}><span className="icon-surface" aria-hidden="true"><SlidersHorizontal size={15} /></span>{title}</p>
}
