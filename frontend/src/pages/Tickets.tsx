import { Can } from '../auth/permissions'
import { PaginationBar } from '../components/PaginationBar'
import { FeedbackMessage } from '../components/FeedbackMessage'
import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router'
import { RefreshCw, Plus, FileText, FileSpreadsheet } from 'lucide-react'
import { downloadTickets } from '../api/ticketExports'
import { useTickets } from '../hooks/useTickets'
import { PageHeading } from '../components/PageHeading'
import { RequestState } from '../components/RequestState'
import { useUrlFilters } from '../hooks/useUrlFilters'
import { ticketFilterKeys, ticketQuery } from '../lib/ticketFilters'
import { TicketFilters } from '../components/TicketFilters'
import { TicketTable } from '../components/TicketTable'
import { loadHiddenColumns, saveHiddenColumns, optionalColumns } from '../lib/ticketColumns'
import type { OptionalColumn } from '../components/TicketTable'
import { pageInfo, pageText, rangeText, PAGE_SIZE } from '../lib/pagination'

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
  const { loading, tickets, total: apiTotal, error } = useTickets(offset, refresh, query, filterError)
  // Sin cabecera X-Total-Count se conserva el comportamiento anterior (cota inferior).
  const total = apiTotal ?? offset + tickets.length
  const info = pageInfo(offset, tickets.length, total)
  // Una página fuera de rango (p. ej. tras cambiar filtros o borrar registros) salta a la última existente.
  useEffect(() => { if (!loading && !error && apiTotal !== null && tickets.length === 0 && offset > 0) setOffset(apiTotal ? info.lastOffset : 0) }, [loading, error, apiTotal, tickets.length, offset]) // eslint-disable-line react-hooks/exhaustive-deps
  const [hidden, setHidden] = useState<OptionalColumn[]>(loadHiddenColumns)
  function toggleColumn(column: OptionalColumn) {
    const next = hidden.includes(column) ? hidden.filter((item) => item !== column) : [...hidden, column]
    setHidden(next); saveHiddenColumns(next)
  }
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  async function exportTickets(format: 'pdf' | 'xlsx') {
    if (exporting || filterError) return
    setExporting(true); setExportError(null)
    try { await downloadTickets(format, query) } catch (failure) { setExportError(failure instanceof Error ? failure.message : 'No se pudo exportar el listado.') } finally { setExporting(false) }
  }
  return <>
    <PageHeading
      title="Tickets"
      description="Consulta las incidencias registradas, de la más reciente a la más antigua."
      telemetry={
        !loading && !error && (
          <span className="heading-telemetry">
            <span>Total:</span>
            <strong className="telemetry-value--blue">{total}</strong>
          </span>
        )
      }
      action={
        <div className="flex flex-wrap gap-2">
          <button className="button-secondary rounded-full shadow-xs" disabled={loading} onClick={() => setRefresh(refresh + 1)}>
            <RefreshCw size={14} aria-hidden="true" />Actualizar
          </button>
          <Can permission="tickets.export">
            <button type="button" className="button-secondary rounded-full shadow-xs" disabled={exporting || Boolean(filterError)} onClick={() => exportTickets('pdf')}>
              <FileText size={14} aria-hidden="true" />Exportar PDF
            </button>
          </Can>
          <Can permission="tickets.export">
            <button type="button" className="button-secondary rounded-full shadow-xs" disabled={exporting || Boolean(filterError)} onClick={() => exportTickets('xlsx')}>
              <FileSpreadsheet size={14} aria-hidden="true" />Exportar Excel
            </button>
          </Can>
          <Can permission="tickets.create">
            <Link className="button-primary rounded-full shadow-sm" to="/tickets/new">
              <Plus size={15} aria-hidden="true" />Nuevo ticket
            </Link>
          </Can>
        </div>
      }
    />
    {createdReference && <FeedbackMessage variant="success" className="mb-3">Ticket {createdReference} creado correctamente.</FeedbackMessage>}
    {exporting && <RequestState loading compact loadingText="Generando archivo..." className="mb-3 workspace-caption" />}
    {exportError && <FeedbackMessage variant="error" className="mb-3">{exportError}</FeedbackMessage>}
    <TicketFilters params={params} change={change} clear={clear} />
    <div className="mb-2 flex flex-wrap items-center justify-between gap-3 text-sm workspace-caption">
      <span>{params.get('status') === 'OPEN' ? 'Abiertos' : params.get('status') === 'CLOSED' ? 'Cerrados' : 'Todos los estados'}{!loading && !error && ` · ${rangeText(info)}`}</span><span className="flex flex-wrap items-center gap-3">
        <details className="column-picker">
          <summary className="button-secondary rounded-full text-xs cursor-pointer">Columnas</summary>
          <fieldset className="column-picker-menu"><legend className="sr-only">Columnas opcionales</legend>
            {optionalColumns.map(({ key, label }) => <label key={key} className="flex items-center gap-2"><input type="checkbox" checked={!hidden.includes(key)} onChange={() => toggleColumn(key)} />Mostrar {label}</label>)}
          </fieldset>
        </details>
        <span>Fechas en America/Guatemala</span>
      </span>
    </div>
    {loading || error || tickets.length === 0 ? <RequestState loading={loading} error={error} empty={tickets.length === 0} onRetry={() => setRefresh(refresh + 1)} /> : <TicketTable tickets={tickets} hidden={hidden} />}
    <PaginationBar page={Math.floor(offset / 50) + 1} info={<p className="text-sm">{!loading && !error ? pageText(info) : `Página ${info.page}`}</p>} previousDisabled={offset === 0 || loading} nextDisabled={loading || Boolean(error) || (apiTotal === null ? tickets.length < PAGE_SIZE : offset + tickets.length >= apiTotal)} onPrevious={() => setOffset(Math.max(0, offset - 50))} onNext={() => setOffset(offset + 50)} />
  </>
}
