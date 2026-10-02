import { describe, expect, it, vi } from 'vitest'
import { getJson } from './client'
import { getHealth, listTickets } from './index'
import { jsonResponse, ticket } from '../test/fixtures'

describe('cliente API', () => {
  it('lee JSON y usa una URL relativa con paginación', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([ticket]))
    vi.stubGlobal('fetch', fetchMock)
    expect(await listTickets({ limit: 50, offset: 50 })).toEqual([ticket])
    expect(fetchMock).toHaveBeenCalledWith('/api/tickets?limit=50&offset=50', expect.any(Object))
  })
  it('expone errores HTTP', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'error' }, 503)))
    await expect(listTickets()).rejects.toMatchObject({ status: 503, message: expect.stringContaining('503') })
  })
  it('expone fallos de conexión', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(listTickets()).rejects.toThrow('No se pudo conectar')
  })
  it('rechaza JSON inválido', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('invalid JSON')))
    await expect(getJson('/api/tickets')).rejects.toThrow('JSON inválida')
  })
  it('rechaza una colección que no es un array', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({})))
    await expect(listTickets()).rejects.toThrow('lista de tickets válida')
  })
  it('comprueba el health recibido', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse({ status: 'ok' }))
      .mockResolvedValueOnce(jsonResponse({ status: 'down' }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(getHealth()).resolves.toBeUndefined()
    await expect(getHealth()).rejects.toThrow('disponibilidad')
  })
})
