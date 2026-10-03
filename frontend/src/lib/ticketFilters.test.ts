import { describe, expect, it } from 'vitest'
import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { localDateBoundary, ticketQuery } from './ticketFilters'

describe('rangos operativos', () => {
  it('convierte días locales a límites inclusivo/exclusivo', () => {
    const { query, error } = ticketQuery(new URLSearchParams('from=2026-10-02&to=2026-10-02&customer_id=2&status=OPEN'))
    expect(error).toBeNull()
    expect(query).toEqual({ customer_id: 2, status: 'OPEN', from: new Date(2026, 9, 2).toISOString(), to: new Date(2026, 9, 3).toISOString() })
  })
  it('rechaza fechas inválidas y rangos invertidos', () => {
    expect(() => localDateBoundary('2026-02-30')).toThrow()
    expect(ticketQuery(new URLSearchParams('from=2026-10-03&to=2026-10-02')).error).toMatch('Hasta')
  })
  it.each([['Etc/GMT+6', '2026-03-09T06:00:00.000Z'], ['America/New_York', '2026-03-09T04:00:00.000Z'], ['UTC', '2026-03-09T00:00:00.000Z']])('respeta zona local y cambios de horario %s', (zone, expected) => {
    const moduleUrl = pathToFileURL(resolve('src/lib/ticketFilters.ts')).href
    const result = execFileSync(process.execPath, ['--input-type=module', '-e', `import { localDateBoundary } from ${JSON.stringify(moduleUrl)}; console.log(localDateBoundary('2026-03-08', true));`], { env: { ...process.env, TZ: zone }, encoding: 'utf8' })
    expect(result.trim()).toBe(expected)
  })
})
