import { Children, cloneElement, isValidElement } from 'react'
import type { AriaAttributes, ReactNode } from 'react'

type FieldChild = { id?: string; children?: ReactNode } & Pick<AriaAttributes, 'aria-describedby' | 'aria-invalid'>

function describeControl(children: ReactNode, id: string, describedBy?: string, invalid?: boolean): ReactNode {
  return Children.map(children, (child) => {
    if (!isValidElement<FieldChild>(child)) return child
    if (child.props.id === id) {
      const descriptions = [...new Set(`${child.props['aria-describedby'] ?? ''} ${describedBy ?? ''}`.split(/\s+/).filter(Boolean))].join(' ')
      return cloneElement(child, { 'aria-describedby': descriptions || undefined, 'aria-invalid': invalid || child.props['aria-invalid'] })
    }
    return child.props.children === undefined ? child : cloneElement(child, { children: describeControl(child.props.children, id, describedBy, invalid) })
  })
}

export function FormField({ id, label, required = false, children, describedBy, invalid }: {
  id: string; label: string; required?: boolean; children: ReactNode; describedBy?: string; invalid?: boolean
}) {
  return <div className="min-w-0"><label htmlFor={id} className="form-label">{label}{required && <span aria-hidden="true" className="ml-1 text-slate-500">*</span>}</label>{describeControl(children, id, describedBy, invalid)}</div>
}
