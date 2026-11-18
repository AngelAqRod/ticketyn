import { deleteResource, getJson, patchJson, postJson } from './client'
import type { AdminRequest, AdminRequestStatus, AdminRequestInput, LinkKind, LinkedRecord, Paged } from '../types/adminRequests'

const base = '/api/admin-requests'
export const candidatePaths: Record<LinkKind, string> = { ticket: 'tickets', internal_ticket: 'internal-tickets', change: 'changes' }
export const listAdminRequests = (query: URLSearchParams, signal?: AbortSignal) => getJson<Paged<AdminRequest>>(`${base}?${query}`, signal)
export const getAdminRequest = (id: number, signal?: AbortSignal) => getJson<AdminRequest>(`${base}/${id}`, signal)
export const createAdminRequest = (body: AdminRequestInput) => postJson<AdminRequest>(base, body)
export const updateAdminRequest = (id: number, body: Partial<AdminRequestInput>) => patchJson<AdminRequest>(`${base}/${id}`, body)
export const changeAdminRequestStatus = (id: number, status: AdminRequestStatus) => postJson<AdminRequest>(`${base}/${id}/status`, { status })
export const searchLinkCandidates = (id: number, kind: LinkKind, query: URLSearchParams, signal?: AbortSignal) =>
  getJson<Paged<LinkedRecord>>(`${base}/${id}/candidates/${candidatePaths[kind]}?${query}`, signal)
export const addAdminRequestLink = (id: number, kind: LinkKind, targetId: number) => postJson<AdminRequest>(`${base}/${id}/links`, { kind, target_id: targetId })
export const removeAdminRequestLink = (id: number, linkId: number) => deleteResource(`${base}/${id}/links/${linkId}`)
