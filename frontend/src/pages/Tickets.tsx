import { useState } from 'react'
import { Link, useLocation } from 'react-router'
import { ArrowLeft, ArrowRight, RefreshCw, Plus, FileText, FileSpreadsheet } from 'lucide-react'
import { downloadTickets } from '../api/ticketExports'
import { useTickets } from '../hooks/useTickets'
import { PageHeading } from '../components/PageHeading'
import { RequestState } from '../components/RequestState'
import { useUrlFilters } from '../hooks/useUrlFilters'
import { ticketFilterKeys, ticketQuery } from '../lib/ticketFilters'
import { TicketFilters } from '../components/TicketFilters'
import { TicketTable } from '../components/TicketTable'

export function Tickets() {
  const location = useLocation()
  const navigationState: unknown = location.state
  const createdReference = navigationState && typeof navigationState === 'object'
    && 'createdReference' in navigationState && typeof navigationState.createdReference === 'string'
    ? navigationState.createdReference : null
  const { params, change, clear } = useUrlFilters(ticketFilterKeys)
  const rawOffset = Number(params.get('offset') ?? 0)
  const offset = Number.isInteger(rawOffset) && rawOffset >= 0 ? rawOffset : 0
  const { query, error: filterError } = ticketQuery(params)
  const setOffset = (value: number) => change({ offset: value ? String(value) : '' }, false)
  const [refresh, setRefresh] = useState(0)
  const { loading, tickets, error } = useTickets(offset, refresh, query, filterError)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  async function exportTickets(format: 'pdf' | 'xlsx') {
    if (exporting || filterError) return
    setExporting(true); setExportError(null)
    try { await downloadTickets(format, query) } catch (failure) { setExportError(failure instanceof Error ? failure.message : 'No se pudo exportar el listado.') } finally { setExporting(false) }
  }
  return <>
    <PageHeading title="Tickets" description="Consulta las incidencias registradas, de la más reciente a la más antigua." action={<div className="flex flex-wrap gap-2"><button className="button-secondary" disabled={loading} onClick={() => setRefresh(refresh + 1)}><RefreshCw size={15} aria-hidden="true" />Actualizar</button><button type="button" className="button-secondary" disabled={exporting || Boolean(filterError)} onClick={() => exportTickets('pdf')}><FileText size={15} aria-hidden="true" />Exportar PDF</button><button type="button" className="button-secondary" disabled={exporting || Boolean(filterError)} onClick={() => exportTickets('xlsx')}><FileSpreadsheet size={15} aria-hidden="true" />Exportar Excel</button><Link className="button-primary" to="/tickets/new"><Plus size={15} aria-hidden="true" />Nuevo ticket</Link></div>} />
    {createdReference && <p role="status" className="mb-3 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">Ticket {createdReference} creado correctamente.</p>}
    {exporting && <p role="status" className="mb-3 text-sm text-muted">Generando archivo...</p>}
    {exportError && <p role="alert" className="mb-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">{exportError}</p>}
    <TicketFilters params={params} change={change} clear={clear} />
    <div className="mb-2 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
      <span>{params.get('status') === 'OPEN' ? 'Abiertos' : params.get('status') === 'CLOSED' ? 'Cerrados' : 'Todos los estados'}</span><span>Fechas en tu zona horaria local</span>
    </div>
    {loading || error || tickets.length === 0 ? <RequestState loading={loading} error={error} empty={tickets.length === 0} onRetry={() => setRefresh(refresh + 1)} /> : <TicketTable tickets={tickets} />}
    <div className="pagination-bar">
      <p className="text-xs text-slate-500">Página {Math.floor(offset / 50) + 1}{!loading && !error && tickets.length > 0 ? ` · Registros ${offset + 1}–${offset + tickets.length}` : ''}</p>
      <div className="flex gap-2"><button className="button-secondary" disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - 50))}><ArrowLeft size={15} aria-hidden="true" />Anterior</button>
        <button className="button-secondary" disabled={loading || Boolean(error) || tickets.length < 50} onClick={() => setOffset(offset + 50)}>Siguiente<ArrowRight size={15} aria-hidden="true" /></button></div>
    </div>
  </>
}
