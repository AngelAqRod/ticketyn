export class ApiError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, { signal, headers: { Accept: 'application/json' } })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new ApiError('No se pudo conectar con la API. Comprueba que el backend esté disponible.')
  }
  if (!response.ok) {
    throw new ApiError(`La API devolvió un error HTTP ${response.status}.`, response.status)
  }
  try {
    return await response.json() as T
  } catch (error) {
    if (signal?.aborted) throw error
    throw new ApiError('La API devolvió una respuesta JSON inválida.')
  }
}
