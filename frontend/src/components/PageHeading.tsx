import type { ReactNode } from 'react'

export function PageHeading({ title, description, action }: {
  title: string; description: string; action?: ReactNode
}) {
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3 border-b border-slate-300 pb-3">
      <div><h1 className="text-xl font-semibold tracking-tight text-slate-900">{title}</h1>
        <p className="mt-1 text-sm leading-5 text-slate-500">{description}</p></div>
      {action}
    </div>
  )
}
