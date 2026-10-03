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
