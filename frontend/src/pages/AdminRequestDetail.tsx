import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { changeAdminRequestStatus, getAdminRequest } from '../api/adminRequests'
import { usePermissions } from '../auth/permissions'
import { PageHeading } from '../components/PageHeading'
import { RequestState } from '../components/RequestState'
import { AdminRequestLinks, linkKinds } from '../components/AdminRequestLinks'
import { formatDay } from './AdminRequests'
import { formatDate } from '../lib/format'
import { ticketynTimezone } from '../lib/datetime'
import { statusLabels, statusTransitions } from '../types/adminRequests'
import type { AdminRequest, AdminRequestStatus } from '../types/adminRequests'
import { FeedbackMessage } from '../components/FeedbackMessage'
import '../styles/installationOrders.css'

const actions: Record<string, string> = { CREATE: 'Registro', EDIT: 'Edición', LINK: 'Asociación', UNLINK: 'Desvinculación', STATUS: 'Cambio de estado' }
const eventText = (e: AdminRequest['events'][number]) => e.action === 'STATUS'
  ? `Cambio de estado: ${statusLabels[e.detail.from as AdminRequestStatus] ?? e.detail.from} → ${statusLabels[e.detail.to as AdminRequestStatus] ?? e.detail.to}` : actions[e.action] ?? e.action

export function AdminRequestDetail() {
  const access = usePermissions(), id = Number(useParams().id)
  const [item, setItem] = useState<AdminRequest | null>(null), [error, setError] = useState<string | null>(null), [retry, setRetry] = useState(0)
  const [busy, setBusy] = useState(false), [statusError, setStatusError] = useState<string | null>(null)
  async function move(status: AdminRequestStatus) {
    setBusy(true); setStatusError(null)
    try { setItem(await changeAdminRequestStatus(id, status)) } catch (cause) { setStatusError(cause instanceof Error ? cause.message : 'No se pudo cambiar el estado.') } finally { setBusy(false) }
  }
  useEffect(() => {
    const controller = new AbortController()
    getAdminRequest(id, controller.signal).then(data => { if (!controller.signal.aborted) { setItem(data); setError(null) } })
      .catch(cause => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'No se pudo cargar la solicitud.') })
    return () => controller.abort()
  }, [id, retry])
  if (!item) return <RequestState loading={!error} error={error} errorTitle="Error al cargar la solicitud" onRetry={() => setRetry(v => v + 1)} />
  const data: [string, string | null | undefined][] = [
    ['Estado', statusLabels[item.status] ?? item.status], ['Tipo de solicitud', item.type.name], ['Solicitante', item.requester.name], ['Cliente', item.customer?.name], ['Circuito', item.circuit?.circuit_code],
    ['Fecha de solicitud', formatDay(item.request_date)],
    ['Período de aplicación', item.application_start || item.application_end ? `${item.application_start ? formatDay(item.application_start) : 'Sin inicio'} – ${item.application_end ? formatDay(item.application_end) : 'Sin fin'}` : null], ['Fecha de registro', formatDate(item.created_at, ticketynTimezone)], ['Registrada por', item.registered_by.name],
    ['Descripción del requerimiento', item.description], ['Observaciones', item.notes],
  ]
  const linked = { ticket: item.links.tickets, internal_ticket: item.links.internal_tickets, change: item.links.changes }
  return <>
    <PageHeading title={item.reference} description="La fecha de solicitud es cuando se recibió el requerimiento; la fecha de registro es cuando se capturó en Ticketyn." theme="purple"
      action={<div className="flex flex-wrap gap-3"><Link className="button-secondary" to="/admin-requests">Volver a solicitudes</Link>{access.can('admin_requests.edit') && <Link className="button-primary button-primary--purple" to={`/admin-requests/${id}/edit`}>Editar solicitud</Link>}</div>} />
    <section className="panel installation-section"><h2>Solicitud</h2><dl className="installation-data">{data.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || 'No indicado'}</dd></div>)}</dl></section>
    {access.can('admin_requests.edit') && <section className="panel installation-section"><h2>Cambiar estado</h2>
      <div className="flex flex-wrap gap-3">{statusTransitions[item.status].map(next => <button key={next} type="button" className="button-secondary" disabled={busy} onClick={() => move(next)}>{`Pasar a ${statusLabels[next]}`}</button>)}</div>
      {statusError && <FeedbackMessage variant="error" className="mt-3">{statusError}</FeedbackMessage>}</section>}
    {linkKinds.map(def => <AdminRequestLinks key={def.kind} {...def} requestId={id} requestDate={item.request_date} linked={linked[def.kind]} onChanged={() => setRetry(v => v + 1)} />)}
    <section className="panel installation-section"><h2>Historial</h2><ul className="space-y-1 text-sm">{item.events.map(e => <li key={e.id}>{formatDate(e.created_at, ticketynTimezone)} · {eventText(e)}</li>)}</ul></section>
  </>
}
