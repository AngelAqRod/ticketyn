import type { ReactNode } from 'react'
import { ArrowUpRight } from 'lucide-react'
import { Link } from 'react-router'
import { usePermissions } from '../auth/permissions'

/** Uses already resolved data; inactive circuits remain valid historical destinations. */
export function CircuitLink({ id, children }: { id?: number | null; children: ReactNode }) {
  const access = usePermissions()
  if (!access.can('circuits.view') || !id || !Number.isSafeInteger(id) || id < 1) return <>{children}</>
  return <Link to={`/circuits/${id}`} title="Consultar ficha técnica del circuito"
    onClick={event => event.stopPropagation()}
    className="inline-flex max-w-full min-w-0 items-baseline gap-1 rounded-sm text-sky-400 underline-offset-4 hover:text-sky-300 hover:underline focus-visible:outline-sky-300">
    <span className="min-w-0 [overflow-wrap:anywhere]">{children}</span>
    <ArrowUpRight size={12} className="shrink-0 self-center" aria-hidden="true" />
  </Link>
}
