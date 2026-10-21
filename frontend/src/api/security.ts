import { getJson } from './client'
import type { Responsible } from '../types/catalog'

export interface Account extends Responsible {
  account_exists: boolean; username: string | null; role_id: number | null; role_name: string | null
  access_granted: boolean; effective_access: boolean; password_change_required: boolean
}
export interface SecurityRole {
  id: number; code: string | null; name: string; description: string | null
  revision: number; permissions: string[]; editable: boolean; duplicable: boolean
}
export interface Permission { code: string; module: string; label: string; requires: string[]; exclusive: boolean }
export interface ActiveSession {
  id: string; responsible_id: number; name: string; username: string; current: boolean
  ip: string; agent: string; last_activity: string; expires_in: number
}
export async function allPages<T>(path: string, signal?: AbortSignal): Promise<T[]> {
  const result: T[] = []
  for (let offset = 0; ; offset += 200) {
    const page = await getJson<T[]>(`${path}?limit=200&offset=${offset}`, signal)
    result.push(...page)
    if (page.length < 200) return result
  }
}
