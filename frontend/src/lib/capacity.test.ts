import { describe, expect, it } from 'vitest'
import { capacityInMicroMbps, formatCapacity } from './capacity'
import { reportPeriod } from './reportPeriod'
describe('Capacidad exacta y períodos operativos', () => {
  it('compara Mbps/Gbps con decimales sin pérdida de precisión', () => {
    expect(capacityInMicroMbps('1000', 'Mbps')).toBe(capacityInMicroMbps('1', 'Gbps'))
    expect(capacityInMicroMbps('999999999999.000001', 'Mbps')).toBeGreaterThan(capacityInMicroMbps('999999999999', 'Mbps'))
  })
  it.each(['0', '-1', 'NaN', 'Infinity', '1.0000001', '1000000000000'])('rechaza %s', (value) => {
    expect(() => capacityInMicroMbps(value, 'Mbps')).toThrow()
  })
  it.each([['1', '2026-10-13T06:00:00.000Z', '2026-10-14T06:00:00.000Z'], ['yesterday', '2026-10-12T06:00:00.000Z', '2026-10-13T06:00:00.000Z'], ['7', '2026-10-07T06:00:00.000Z', '2026-10-14T06:00:00.000Z'], ['15', '2026-09-29T06:00:00.000Z', '2026-10-14T06:00:00.000Z'], ['30', '2026-09-14T06:00:00.000Z', '2026-10-14T06:00:00.000Z']])('reutiliza rango %s en Guatemala', (period, from, to) => {
    const result = reportPeriod(new URLSearchParams({ period }), new Date('2026-10-13T23:00:00Z'))
    expect(result.query.from).toBe(from); expect(result.query.to).toBe(to)
  })
})


describe('Formato informativo de capacidades', () => {
  it.each([
    ['100', 'Mbps', '100 Mbps'], ['500', 'Mbps', '500 Mbps'],
    ['999', 'Mbps', '999 Mbps'], ['1000', 'Mbps', '1 Gbps'],
    ['1300', 'Mbps', '1.3 Gbps'], ['1500', 'Mbps', '1.5 Gbps'],
    ['1758', 'Mbps', '1.758 Gbps'], ['2000', 'Mbps', '2 Gbps'],
    ['2500', 'Mbps', '2.5 Gbps'], ['10000', 'Mbps', '10 Gbps'],
    ['1.5', 'Gbps', '1.5 Gbps'], ['1758.5', 'Mbps', '1.759 Gbps'],
    ['0.5', 'Gbps', '500 Mbps'], ['0.0015', 'Gbps', '1.5 Mbps'],
    ['100.123499', 'Mbps', '100.123 Mbps'], ['100.123500', 'Mbps', '100.124 Mbps'],
    ['1.000000', 'Gbps', '1 Gbps'], ['999.999500', 'Mbps', '1000 Mbps'],
    ['999999999999.000001', 'Mbps', '999999999.999 Gbps']
  ])('muestra %s %s como %s', (value, unit, expected) => {
    expect(formatCapacity(value, unit)).toBe(expected)
  })
  it.each([null, undefined, '', 'NaN'])('conserva desconocida para %s', value => {
    expect(formatCapacity(value, 'Mbps')).toBe('Sin registrar')
  })
  it('no inventa una unidad desconocida', () => {
    expect(formatCapacity('100', null)).toBe('Sin registrar')
  })
})
