import { getJson, patchJson, postJson } from './client'
import type { NamedCatalog } from '../types/catalog'
import type { DistributionPort } from '../types/distribution'

export const numberFormats = ['N', 'X/Y', 'X/Y/Z', 'W/X/Y/Z'] as const
export type NumberFormat = typeof numberFormats[number]
export interface PortNomenclature extends NamedCatalog { prefix: string; formats: NumberFormat[] }
export type NomenclatureInput = Pick<PortNomenclature, 'name' | 'prefix' | 'formats' | 'active'>
export interface PortGeneration {
  distribution_device_id: number
  nomenclature_id: number
  numbering_format: NumberFormat
  positions: number[]
  start: number
  end?: number
  mode: 'complete' | 'missing'
  description: string | null
  preview_token?: string
}
export interface PortPreview {
  names: { name: string; existing: boolean }[]
  total: number
  existing_count: number
  create_count: number
  blocked: boolean
  preview_token: string
}
export interface PortBatchResult { created: DistributionPort[]; existing_count: number; total: number }

export async function listPortNomenclatures(signal?: AbortSignal, includeInactive = false): Promise<PortNomenclature[]> {
  const rows: PortNomenclature[] = []
  for (let offset = 0; ; offset += 200) {
    const page = await getJson<PortNomenclature[]>(`/api/port-nomenclatures?include_inactive=${includeInactive}&limit=200&offset=${offset}`, signal)
    rows.push(...page)
    if (page.length < 200) return rows
  }
}
export const createPortNomenclature = (input: NomenclatureInput) => postJson<PortNomenclature>('/api/port-nomenclatures', input)
export const updatePortNomenclature = (id: number, input: NomenclatureInput) => patchJson<PortNomenclature>(`/api/port-nomenclatures/${id}`, input)
export const previewPorts = (input: PortGeneration, signal?: AbortSignal) => postJson<PortPreview>('/api/distribution-ports/preview', input, signal)
export const createPortRange = (input: PortGeneration, signal?: AbortSignal) => postJson<PortBatchResult>('/api/distribution-ports/batch', input, signal)
