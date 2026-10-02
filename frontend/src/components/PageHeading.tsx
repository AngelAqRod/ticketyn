import type { ReactNode } from 'react'

export function PageHeading({ title, description, action }: {
  title: string; description: string; action?: ReactNode
}) {
  return (
    <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
      <div><h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">{description}</p></div>
      {action}
    </div>
  )
}
