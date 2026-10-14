import { ticketynTimezone } from '../lib/datetime'
import { getJson, postJson, downloadFile } from './client'
import type { ActivationIntervention, CircuitOperationalDetail, FmsKind, Operation } from '../types/fms'
export const listOperations = (kind: FmsKind, query: URLSearchParams, signal?: AbortSignal) => getJson<Operation[]>(`/api/${kind}?${query}`, signal)
export const createOperation = (kind: FmsKind, payload: Record<string, unknown>) => postJson<Operation>(`/api/${kind}`, payload)
export const getCircuitDetail = (id: number, signal?: AbortSignal) => getJson<CircuitOperationalDetail>(`/api/circuits/${id}/operational-detail`, signal)
export const getActivation = (id: number, signal?: AbortSignal) => getJson<Operation>(`/api/activations/${id}`, signal)
export const listActivationInterventions = (id: number, offset: number, signal?: AbortSignal) => getJson<ActivationIntervention[]>(`/api/activations/${id}/interventions?limit=50&offset=${offset}`, signal)
export const createActivationIntervention = (id: number, payload: Record<string, unknown>) => postJson<ActivationIntervention>(`/api/activations/${id}/interventions`, payload)

export function operationExportUrl(kind: FmsKind, format: 'pdf' | 'xlsx', filters: URLSearchParams): string {
  const query = new URLSearchParams(filters)
  query.delete('limit'); query.delete('offset')
  query.set('timezone', ticketynTimezone)
  return `/api/${kind}/export/${format}?${query}`
}
export const downloadOperations = (kind: FmsKind, format: 'pdf' | 'xlsx', filters: URLSearchParams) => downloadFile(operationExportUrl(kind, format, filters), `ticketyn-${kind}.${format}`)

export const downloadActivationReport = (id: number) => downloadFile(`/api/activations/${id}/reports/pdf?${new URLSearchParams({ timezone: ticketynTimezone })}`, `ticketyn-activacion-${id}.pdf`)
