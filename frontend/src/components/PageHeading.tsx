import type { ReactNode } from 'react'
import { useLocation } from 'react-router'
import { identityFor } from './moduleIdentity'

export function PageHeading({ title, description, action }: {
  title: string; description: string; action?: ReactNode
}) {
  const identity = identityFor(useLocation().pathname)
  return <div className="page-heading" data-module={identity?.number}>
    <div className="flex min-w-0 items-center gap-4">
      {identity && <span aria-hidden="true" className="heading-emblem">{identity.number}</span>}
      <div className="min-w-0 [overflow-wrap:anywhere]">
      {identity && <p className="module-eyebrow">{identity.group}<span aria-hidden="true">/ {identity.number}</span></p>}
      <h1 className="page-title">{title}</h1>
      <p className="page-description">{description}</p>
      </div>
    </div>
    <div className="heading-actions">{action}</div>
  </div>
}
