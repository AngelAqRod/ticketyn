import { describe, expect, it } from 'vitest'
import { ageBucket, formatAge, ticketsUrl } from './ticketAge'

const now = Date.parse('2026-06-01T12:00:00Z')
const at = (ms: number) => new Date(now - ms).toISOString()
const H = 3_600_000

describe('ageBucket', () => {
  it.each([
    [0, 'lt_1h'], [H - 1, 'lt_1h'], [H, '1_to_4h'], [4 * H - 1, '1_to_4h'], [4 * H, '4_to_24h'], [24 * H, '4_to_24h'], [24 * H + 1, 'gt_24h'],
  ])('antigüedad %i ms → %s (límites idénticos al backend)', (age, bucket) => expect(ageBucket(at(age), now)).toBe(bucket))
  it('inicio futuro o fecha inválida no pertenecen a ningún tramo', () => {
    expect(ageBucket(at(-1), now)).toBeNull()
    expect(ageBucket('no-fecha', now)).toBeNull()
  })
})

describe('formatAge', () => {
  it.each([[45 * 60_000, '45 min'], [2 * H + 15 * 60_000, '2 h 15 min'], [9 * H, '9 h'], [28 * H, '1 d 4 h'], [48 * H, '2 d'], [0, '0 min'], [-H, 'Inicio futuro']])('%i ms → %s', (age, text) => expect(formatAge(at(age), now)).toBe(text))
})

it('construye la URL con filtros codificados', () => {
  expect(ticketsUrl({ status: 'OPEN', age_bucket: '1_to_4h' })).toBe('/tickets?status=OPEN&age_bucket=1_to_4h')
})
