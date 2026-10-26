import { getJson, patchJson, postJson } from './client'
import type { NumberFormat } from './portNomenclatures'

export interface TemplateGroup {
  nomenclature_id: number
  numbering_format: NumberFormat
  positions: number[]
  start: number
  end: number
}
export interface TemplateInput {
  name: string
  manufacturer: string | null
  description: string | null
  active: boolean
  groups: TemplateGroup[]
  preview_token?: string
}
export interface TemplatePreview {
  groups: (TemplateGroup & { nomenclature_name: string; prefix: string; names: string[]; warning: string | null })[]
  total_ports: number
  usable: boolean
  preview_token: string
}
export interface DeviceTemplate extends Omit<TemplateInput, 'groups' | 'preview_token'>, TemplatePreview { id: number; created_at: string }
const base = '/api/distribution-device-templates'
export async function listDeviceTemplates(signal?: AbortSignal, includeInactive = false) {
  const rows: DeviceTemplate[] = []
  for (let offset = 0; ; offset += 200) {
    const page = await getJson<DeviceTemplate[]>(`${base}?include_inactive=${includeInactive}&limit=200&offset=${offset}`, signal)
    rows.push(...page)
    if (page.length < 200) return rows
  }
}
export const getDeviceTemplate = (id: number, signal?: AbortSignal) => getJson<DeviceTemplate>(`${base}/${id}/preview`, signal)
export const previewDeviceTemplate = (input: TemplateInput, id?: number, signal?: AbortSignal) => postJson<TemplatePreview>(`${base}/preview${id ? `?template_id=${id}` : ''}`, input, signal)
export const saveDeviceTemplate = (input: TemplateInput, id?: number) => id ? patchJson<DeviceTemplate>(`${base}/${id}`, input) : postJson<DeviceTemplate>(base, input)
