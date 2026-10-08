export class ApiError extends Error {
  constructor(message: string, public readonly status?: number, public readonly fields: string[] = []) {
    super(message)
    this.name = 'ApiError'
  }
}

const fieldLabels: Record<string, string> = {
  name: 'Nombre', customer_code: 'Código de cliente', circuit_code: 'Código de circuito',
  title: 'Título', description: 'Descripción', node_id: 'Nodo de distribución', responsible_id: 'Responsable', customer_id: 'Cliente', circuit_id: 'Circuito',
  sector_id: 'Sector', department_id: 'Departamento', incident_type_id: 'Tipo de incidencia',
  content: 'Descripción de la intervención', occurred_at: 'Fecha/hora de intervención', visibility: 'Visibilidad',
  resolution: 'Resolución documentada', customer_description: 'Descripción del incidente', customer_resolution: 'Resolución del incidente',
  start_at: 'Inicio', end_at: 'Fin', status: 'Estado',
}

function detailMessage(detail: unknown): string | null {
  if (typeof detail === 'string' && detail.trim()) return detail
  if (!Array.isArray(detail)) return null
  const messages = detail.flatMap((entry: unknown) => {
    if (!entry || typeof entry !== 'object' || !('msg' in entry) || typeof entry.msg !== 'string') return []
    const location = 'loc' in entry && Array.isArray(entry.loc)
      ? entry.loc.filter((part: unknown) => typeof part === 'string' && part !== 'body').map((part: string) => fieldLabels[part] ?? part).join(' · ')
      : ''
    const message = entry.msg === 'Field required' ? 'Campo obligatorio' : entry.msg
    return [location ? `${location}: ${message}` : message]
  })
  return messages.length ? messages.join('. ') : null
}

async function requestJson<T>(path: string, options: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, options)
  } catch (error) {
    if (options.signal?.aborted) throw error
    throw new ApiError('No se pudo conectar con la API. Comprueba que el backend esté disponible.')
  }
  if (!response.ok) {
    let message: string | null = null
    let fields: string[] = []
    try {
      const body: unknown = await response.json()
      if (body && typeof body === 'object' && 'detail' in body) {
        message = detailMessage(body.detail)
        if (Array.isArray(body.detail)) fields = body.detail.flatMap((entry: unknown) => {
          if (!entry || typeof entry !== 'object' || !('loc' in entry) || !Array.isArray(entry.loc)) return []
          const location = entry.loc
          return location[0] === 'body' && typeof location[1] === 'string' ? [location[1]] : []
        })
      }
    } catch { /* Un error sin JSON conserva su código HTTP. */ }
    throw new ApiError(message ?? `La API devolvió un error HTTP ${response.status}.`, response.status, fields)
  }
  if (response.status === 204 && options.method === 'DELETE') return undefined as T
  try {
    return await response.json() as T
  } catch (error) {
    if (options.signal?.aborted) throw error
    throw new ApiError('La API devolvió una respuesta JSON inválida.')
  }
}

export function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return requestJson<T>(path, { signal, headers: { Accept: 'application/json' } })
}

export function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return requestJson<T>(path, {
    method: 'POST', signal,
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function patchJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return requestJson<T>(path, { method: "PATCH", signal, headers: { Accept: "application/json", "Content-Type": "application/json" }, body: JSON.stringify(body) })
}

export async function downloadFile(path: string, filename: string): Promise<void> {
  let response: Response
  try { response = await fetch(path) } catch { throw new ApiError('No se pudo conectar con la API.') }
  if (!response.ok) {
    let message: string | null = null
    try { const body: unknown = await response.json(); if (body && typeof body === 'object' && 'detail' in body) message = detailMessage(body.detail) } catch { /* conservar HTTP */ }
    throw new ApiError(message ?? `Error HTTP ${response.status} al exportar.`, response.status)
  }
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  try {
    const link = document.createElement('a'); link.href = url; link.download = filename
    document.body.append(link); link.click(); link.remove()
  } finally { URL.revokeObjectURL(url) }
}

export function deleteResource(path: string, signal?: AbortSignal): Promise<void> {
  return requestJson<void>(path, { method: 'DELETE', signal, headers: { Accept: 'application/json' } })
}
