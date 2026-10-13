import { ticketynDateTimeValue, ticketynDateTimeToIso, ticketynTimezone } from './datetime'
function periodBoundary(value: string, nextDay = false) {
  const begin = ticketynDateTimeToIso(`${value}T00:00`)
  if (!nextDay) return begin
  const calendar = new Date(`${value}T12:00:00Z`); calendar.setUTCDate(calendar.getUTCDate() + 1)
  return ticketynDateTimeToIso(`${calendar.toISOString().slice(0, 10)}T00:00`)
}
import type { ReportQuery } from '../types/report'

export const reportFilterKeys = ['view', 'period', 'sector_id', 'node_id', 'responsible_id', 'recipient_id', 'from', 'to'] as const
export function localDateValue(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
export function reportPeriod(params: URLSearchParams, today = new Date()) {
  const custom = params.get('period') === 'custom' || (!params.has('period') && (params.has('from') || params.has('to')))
  if (custom && params.has('from') !== params.has('to')) throw new Error('Completa Desde y Hasta para el período personalizado.')
  const period = custom ? 'custom' : params.get('period') ?? '30'
  if (!custom && !['all', '1', 'yesterday', '7', '15', '30'].includes(period)) throw new Error('Período inválido.')
  const calendarToday = new Date(`${ticketynDateTimeValue(today).slice(0, 10)}T12:00:00Z`)
  const start = new Date(calendarToday); start.setUTCDate(start.getUTCDate() - (custom ? 29 : period === 'yesterday' ? 1 : period === 'all' ? 0 : Number(period) - 1))
  const from = custom ? params.get('from') ?? start.toISOString().slice(0, 10) : start.toISOString().slice(0, 10)
  const to = custom ? params.get('to') ?? calendarToday.toISOString().slice(0, 10) : period === 'yesterday' ? start.toISOString().slice(0, 10) : calendarToday.toISOString().slice(0, 10)
  const begin = periodBoundary(from), end = periodBoundary(to, true)
  if (new Date(begin) >= new Date(end)) throw new Error('Hasta debe ser igual o posterior a Desde.')
  const sector = params.get('view') === 'sector' ? params.get('sector_id') : null
  if (sector && (!Number.isInteger(Number(sector)) || Number(sector) <= 0)) throw new Error('Sector inválido.')
  const query: ReportQuery = { ...(period === 'all' ? {} : { from: begin, to: end }), timezone: ticketynTimezone, ...(sector ? { sector_id: Number(sector) } : {}), granularity: ['1', 'yesterday'].includes(period) ? 'hour' : 'auto' }
  for (const [view, key] of [['node', 'node_id'], ['responsible', 'responsible_id']] as const) {
    if (params.get('view') !== view || !params.get(key)) continue
    const value = Number(params.get(key))
    if (!Number.isInteger(value) || value <= 0) throw new Error('Selección inválida.')
    query[key] = value
  }
  const recipient = params.get('recipient_id')
  if (recipient) {
    const id = Number(recipient)
    if (!Number.isInteger(id) || id <= 0) throw new Error('Destinatario inválido.')
    query.recipient_id = id
  }
  return { period, from: period === 'all' ? '' : from, to: period === 'all' ? '' : to, query }
}
export function ticketDrillDown(field: string, id: number, from: string, to: string, sectorId?: number, nodeId?: number, responsibleId?: number): string {
  return `/tickets?${new URLSearchParams({ [field]: String(id), ...(from && to ? { from, to } : {}), ...(sectorId ? { sector_id: String(sectorId) } : {}), ...(nodeId ? { node_id: String(nodeId) } : {}), ...(responsibleId ? { responsible_id: String(responsibleId) } : {}) })}`
}
