import { execFileSync } from 'node:child_process'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { describe, expect, it } from 'vitest'
import { localDateTimeToIso, localDateTimeValue } from './datetime'

describe('fechas operativas locales', () => {
  it('conserva la hora elegida al convertir a ISO y volver a local', () => {
    const selected = '2026-10-02T16:20'
    expect(localDateTimeToIso(selected)).toBe(new Date(2026, 9, 2, 16, 20).toISOString())
    expect(localDateTimeValue(new Date(localDateTimeToIso(selected)))).toBe(selected)
  })
  it('rechaza fechas inválidas sin normalizarlas silenciosamente', () => {
    expect(() => localDateTimeToIso('invalid')).toThrow('fecha/hora local válida')
    expect(() => localDateTimeToIso('2026-02-30T12:00')).toThrow('fecha/hora local válida')
  })
  it.each([
    ['Etc/GMT+6', '2026-10-02T22:20:00.000Z'],
    ['UTC', '2026-10-02T16:20:00.000Z'],
    ['Asia/Tokyo', '2026-10-02T07:20:00.000Z'],
  ])('usa la zona del navegador/entorno %s, sin un offset fijo', (zone, expected) => {
    const moduleUrl = pathToFileURL(resolve('src/lib/datetime.ts')).href
    const result = execFileSync(process.execPath, ['--input-type=module', '-e',
      `import { localDateTimeToIso } from ${JSON.stringify(moduleUrl)}; console.log(localDateTimeToIso('2026-10-02T16:20'));`,
    ], { env: { ...process.env, TZ: zone }, encoding: 'utf8' })
    expect(result.trim()).toBe(expected)
  })
})
