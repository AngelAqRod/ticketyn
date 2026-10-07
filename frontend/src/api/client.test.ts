import { describe, expect, it, vi } from 'vitest'
import { getJson } from './client'
import { getHealth, getTicketStats, listCustomers, listTickets } from './index'
import { jsonResponse, ticket } from '../test/fixtures'

describe('cliente API', () => {
  it('carga todas las páginas del catálogo activo, sin limitar el selector a la primera', async () => {
    const firstPage = Array.from({ length: 200 }, (_, index) => ({ id: index + 1 }))
    const lastPage = [{ id: 201 }]
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(firstPage))
      .mockResolvedValueOnce(jsonResponse(lastPage))
    vi.stubGlobal('fetch', fetchMock)
    expect(await listCustomers()).toEqual([...firstPage, ...lastPage])
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/customers?include_inactive=false&limit=200&offset=0', expect.any(Object))
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/customers?include_inactive=false&limit=200&offset=200', expect.any(Object))
  })
  it('lee estadísticas globales sin parámetros de paginación', async () => {
    const stats = { total: 123, open: 20, closed: 103 }
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(stats))
    vi.stubGlobal('fetch', fetchMock)
    expect(await getTicketStats()).toEqual(stats)
    expect(fetchMock).toHaveBeenCalledWith('/api/tickets/stats', expect.any(Object))
  })
  it('lee JSON y usa una URL relativa con paginación', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse([ticket]))
    vi.stubGlobal('fetch', fetchMock)
    expect(await listTickets({ limit: 50, offset: 50 })).toEqual([ticket])
    expect(fetchMock).toHaveBeenCalledWith('/api/tickets?limit=50&offset=50', expect.any(Object))
  })
  it('expone errores HTTP', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'error' }, 503)))
    await expect(listTickets()).rejects.toMatchObject({ status: 503, message: 'error' })
  })
  it('conserva campos de validación para accesibilidad sin alterar el mensaje', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: [
      { loc: ['body', 'customer_id'], msg: 'Field required' },
      { loc: ['query', 'limit'], msg: 'Invalid' },
    ] }, 422)))
    await expect(getJson('/api/tickets')).rejects.toMatchObject({
      status: 422, fields: ['customer_id'], message: 'Cliente: Campo obligatorio. query · limit: Invalid',
    })
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
