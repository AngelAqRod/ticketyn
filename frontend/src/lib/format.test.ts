import { describe, expect, it } from 'vitest'
import { formatDate, formatDuration } from './format'

describe('formatDuration', () => {
  it.each([
    [null, 'En curso'], [0, '0 s'], [45, '45 s'], [120, '2 min'],
    [3720, '1 h 2 min'], [3600, '1 h'], [45.9, '45 s'],
  ])('formatea %s como %s', (input, output) => {
    expect(formatDuration(input)).toBe(output)
  })
})

it('formatea fechas sin modificar el timestamp original', () => {
  const input = '2026-01-01T12:00:00+00:00'
  expect(formatDate(input)).toContain('2026')
  expect(input).toBe('2026-01-01T12:00:00+00:00')
  expect(formatDate(null)).toBe('—')
  expect(formatDate('invalid')).toBe('Fecha no válida')
})
