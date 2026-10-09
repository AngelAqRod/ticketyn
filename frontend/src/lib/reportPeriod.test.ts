import { describe, expect, it } from 'vitest'
import { reportPeriod, localDateValue } from './reportPeriod'
const today = new Date(2026, 9, 2, 16, 20)
describe('períodos de reportería', () => {
  it.each([1, 7, 15, 30])('incluye hoy y %s días locales completos', (days) => {
    const selection = reportPeriod(new URLSearchParams(`period=${days}`), today)
    const start = new Date(2026, 9, 2); start.setDate(start.getDate() - days + 1)
    expect(selection.query.from).toBe(start.toISOString())
    expect(selection.query.to).toBe(new Date(2026, 9, 3).toISOString())
    expect(selection.query.timezone).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone)
  })
  it('acepta URL personalizada sin period explícito y sector', () => {
    const period = reportPeriod(new URLSearchParams('view=sector&sector_id=4&from=2026-09-01&to=2026-09-30'), today)
    expect(period.period).toBe('custom'); expect(period.query.sector_id).toBe(4)
    expect(period.query.to).toBe(new Date(2026, 9, 1).toISOString())
  })
  it.each(['period=bad', 'period=custom&from=2026-09-01', 'view=sector&sector_id=bad', 'from=2026-02-30&to=2026-03-01'])('rechaza URL inválida %s', (query) => {
    expect(() => reportPeriod(new URLSearchParams(query), today)).toThrow()
  })
  it('formatea fecha local sin aplicar UTC', () => {
    expect(localDateValue(today)).toBe('2026-10-02')
  })
})

it('Ayer termina exactamente donde comienza Hoy en el calendario local', () => {
  const yesterday = reportPeriod(new URLSearchParams('period=yesterday'), today)
  const current = reportPeriod(new URLSearchParams('period=1'), today)
  expect(yesterday.from).toBe('2026-10-01')
  expect(yesterday.to).toBe('2026-10-01')
  expect(yesterday.query.from).toBe(new Date(2026, 9, 1).toISOString())
  expect(yesterday.query.to).toBe(current.query.from)
  expect(yesterday.query.granularity).toBe('hour')
})
it('Ayer cruza correctamente límites de mes y año', () => {
  const range = reportPeriod(new URLSearchParams('period=yesterday'), new Date(2026, 0, 1, 0, 1))
  expect(range.from).toBe('2025-12-31')
  expect(range.query.to).toBe(new Date(2026, 0, 1).toISOString())
})
it('Hoy/Ayer conservan medianoches locales incluso durante cambios DST', () => {
  for (const date of [new Date(2026, 2, 9, 12), new Date(2026, 10, 2, 12)]) {
    const yesterday = reportPeriod(new URLSearchParams('period=yesterday'), date)
    const current = reportPeriod(new URLSearchParams('period=1'), date)
    expect(yesterday.query.to).toBe(current.query.from)
    expect(new Date(yesterday.query.from!).getHours()).toBe(0)
    expect(new Date(yesterday.query.to!).getHours()).toBe(0)
  }
})

it('Todos omite los límites y conserva contexto y destinatario separado', () => {
  const result = reportPeriod(new URLSearchParams('period=all&view=node&node_id=5&recipient_id=2'), today)
  expect(result.query.from).toBeUndefined()
  expect(result.query.to).toBeUndefined()
  expect(result.query.node_id).toBe(5)
  expect(result.query.recipient_id).toBe(2)
  expect(result.from).toBe('')
  expect(result.to).toBe('')
})
