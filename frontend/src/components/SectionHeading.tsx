import type { ReactNode } from 'react'

export function SectionHeading({ number, title, id, action, icon }: {
  number: string; title: string; id?: string; action?: ReactNode; icon?: ReactNode
}) {
  return <div className="section-heading">
    <div className="flex items-center gap-2.5"><span aria-hidden="true" className="section-number">{number}</span>{icon && <span className="icon-surface" aria-hidden="true">{icon}</span>}<h2 id={id}>{title}</h2></div>
    {action}
  </div>
}
