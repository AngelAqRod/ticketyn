import type { ReactNode } from 'react'

export function FormField({ id, label, required = false, children }: {
  id: string; label: string; required?: boolean; children: ReactNode
}) {
  return <div><label htmlFor={id} className="mb-2 block text-sm font-medium text-slate-700">{label}{required && <span aria-hidden="true" className="ml-1 text-slate-500">*</span>}</label>{children}</div>
}
