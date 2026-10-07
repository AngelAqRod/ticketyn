import { useId, useState } from 'react'
import { Link } from 'react-router'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { RankingChart } from './ReportCharts'
import type { ReportRanking } from '../types/report'

export function RankingSection({ title, rows, destination }: {
  title: string; rows: ReportRanking[]; destination: (row: ReportRanking) => string
}) {
  const [expanded, setExpanded] = useState(false)
  const tableId = useId()
  return <section className="ranking-section" aria-label={title}>
    <div className="mb-2 flex items-baseline justify-between gap-2"><h3 className="text-sm font-semibold">{title}</h3><span className="chip chip-primary shrink-0">Top 10</span></div>
    {rows.length === 0 ? <p className="py-4 text-sm text-muted">Sin incidencias.</p> : <>
      <RankingChart rows={rows} title={title} />
      <button type="button" className="button-ghost ranking-toggle" aria-expanded={expanded} aria-controls={tableId} onClick={() => setExpanded(!expanded)}>
        {expanded ? <ChevronUp size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}
        {expanded ? `Ocultar ranking completo (${rows.length})` : `Ver ranking completo (${rows.length})`}
      </button>
      <div id={tableId} hidden={!expanded} className="table-surface mt-3 max-h-80 overflow-auto rounded-lg border border-slate-200">
        {expanded && <table className="operation-table"><caption className="sr-only">{title}</caption><thead><tr><th scope="col">Nombre / código</th><th scope="col" className="text-right">Incidencias</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}>
          <th scope="row" className="font-normal"><Link className="text-primary hover:underline underline-offset-4" to={destination(row)}>{row.label}</Link>{row.customer_code && <span className="block text-[11px] text-muted"><span className="font-mono">{row.customer_code}</span> — {row.customer_name}</span>}</th>
          <td className="text-right font-mono tabular-nums">{row.count}</td>
        </tr>)}</tbody></table>}
      </div>
    </>}
  </section>
}
