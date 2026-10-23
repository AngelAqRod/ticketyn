import { jsonResponse } from './fixtures'
import type { DistributionPort } from '../types/distribution'

export const testNomenclature = { id: 90, name: 'Fibra', prefix: 'sfp+', formats: ['N', 'X/Y', 'X/Y/Z', 'W/X/Y/Z'], active: true, created_at: '' }
export function portGenerationResponse(url: URL, init: RequestInit | undefined, ports: DistributionPort[], nextId = 99): Promise<Response> | undefined {
  if (url.pathname === '/api/port-nomenclatures') return Promise.resolve(jsonResponse([testNomenclature]))
  const payload = init?.body ? JSON.parse(String(init.body)) : null
  if (!payload || init?.method !== 'POST' || !url.pathname.startsWith('/api/distribution-ports')) return
  if (!['/api/distribution-ports', '/api/distribution-ports/preview', '/api/distribution-ports/batch'].includes(url.pathname)) return
  const names = Array.from({ length: (payload.end ?? payload.start) - payload.start + 1 }, (_, index) => {
    const name = 'sfp+' + [...payload.positions, payload.start + index].join('/')
    return { name, existing: ports.some(row => row.distribution_device_id === payload.distribution_device_id && row.name.toLowerCase() === name.toLowerCase()) }
  })
  const existing_count = names.filter(row => row.existing).length
  if (url.pathname.endsWith('/preview')) return Promise.resolve(jsonResponse({ names, total: names.length, existing_count, create_count: names.length - existing_count, blocked: payload.mode === 'complete' && existing_count > 0, preview_token: 'checked' }))
  const created = names.filter(row => !row.existing).map((row, index) => ({ id: nextId + index, distribution_device_id: payload.distribution_device_id, name: row.name, description: payload.description, active: true, circuit_count: 0, created_at: '' }))
  ports.push(...created)
  return Promise.resolve(jsonResponse(url.pathname.endsWith('/batch') ? { created, total: names.length, existing_count } : created[0], url.pathname.endsWith('/batch') ? 200 : 201))
}
