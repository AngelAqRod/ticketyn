import { ApiError, getJson, getJsonWithTotal, patchJson, postJson, downloadFile } from './client'
import { authHeaders, expiredSession } from '../auth/session'
import type { InstallationOrder, InstallationOrderInput, InstallationRequest, InstallationSummary, InstallationDocument, ReceptionFilters } from '../types/installationOrders'
import type { CircuitInput } from '../types/catalog'
export const ordersPath = '/api/installation-orders'
export const requestsPath = '/api/installation-requests'
export const listInstallationOrders = (query: URLSearchParams, signal?: AbortSignal) => getJsonWithTotal<InstallationOrder[]>(`${ordersPath}?${query}`, signal)
export const listInstallationRequests = (query: URLSearchParams, signal?: AbortSignal) => getJsonWithTotal<InstallationRequest[]>(`${requestsPath}?${query}`, signal)
export const installationSummary = (signal?: AbortSignal) => getJson<InstallationSummary>(`${requestsPath}/summary`, signal)
export const getInstallationOrder = (id: number, signal?: AbortSignal) => getJson<InstallationOrder>(`${ordersPath}/${id}`, signal)
export const getInstallationRequest = (id: number, signal?: AbortSignal) => getJson<InstallationRequest>(`${requestsPath}/${id}`, signal)
export const createInstallationOrder = (body: InstallationOrderInput) => postJson<InstallationOrder>(ordersPath, body)
export const updateInstallationOrder = (id: number, body: Partial<InstallationOrderInput>) => patchJson<InstallationOrder>(`${ordersPath}/${id}`, body)
export const reviewInstallationRequest = (id: number) => postJson<InstallationRequest>(`${requestsPath}/${id}/review`, {})
export const processInstallationRequest = (id: number, body: InstallationOrderInput, version: number) => postJson<InstallationOrder>(`${requestsPath}/${id}/process`, {...body, version})
export const discardInstallationRequest = (id: number, reason: string) => postJson<InstallationRequest>(`${requestsPath}/${id}/discard`, {reason})
async function authenticated(path: string, options: RequestInit = {}): Promise<Response> {
 const headers = authHeaders(options.headers), token = headers.get('Authorization')?.replace(/^Bearer /, '') ?? null
 let response: Response
 try { response = await fetch(path, {...options, headers}) } catch { throw new ApiError('No se pudo conectar con la API.') }
 if (!response.ok) {
  if (response.status === 401) expiredSession(token)
  let message = `Error HTTP ${response.status}.`
  try { const body = await response.json(); if (typeof body.detail === 'string') message = body.detail } catch { /* Preserve HTTP status. */ }
  throw new ApiError(message, response.status)
 }
 return response
}
export const saveInstallationDraft = async (id: number, data: Partial<InstallationOrderInput>, version: number): Promise<InstallationRequest> => (await authenticated(`${requestsPath}/${id}/draft`, {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({data,version})})).json()
export const linkInstallationCircuit = async (id: number, circuitId: number): Promise<InstallationOrder> => (await authenticated(`${ordersPath}/${id}/circuit`, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({circuit_id:circuitId})})).json()
export const unlinkInstallationCircuit = async (id: number): Promise<InstallationOrder> => (await authenticated(`${ordersPath}/${id}/circuit`,{method:'DELETE'})).json()
export const createInstallationCircuit = (id: number, body: CircuitInput) => postJson<InstallationOrder>(`${ordersPath}/${id}/circuit`,body)
export const uploadInstallationDocument = async (id: number, file: File): Promise<InstallationDocument> => (await authenticated(`${ordersPath}/${id}/documents?filename=${encodeURIComponent(file.name)}`,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file})).json()
export const installationDocumentBlob = async (id: number, signal?: AbortSignal) => (await authenticated(`/api/installation-documents/${id}/content`,{signal})).blob()
export const downloadInstallationDocument = (doc: InstallationDocument) => downloadFile(`/api/installation-documents/${doc.id}/content`,doc.original_name)
export const installationError = (error: unknown) => error instanceof Error ? error.message : 'No se pudo completar la operación. Intenta nuevamente.'
export const getReceptionFilters = (signal?: AbortSignal) => getJson<ReceptionFilters>('/api/incoming-mail/filters', signal)
export const saveReceptionFilters = (body: ReceptionFilters) => patchJson<ReceptionFilters>('/api/incoming-mail/filters', body)
