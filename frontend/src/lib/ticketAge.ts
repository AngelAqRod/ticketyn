import type { AgeBucket } from '../types/ticket'

// Espejo de api/ticket_age.py (una sola definición de tramos): <1 h | 1 h ≤ x < 4 h | 4 h ≤ x ≤ 24 h | > 24 h.
// La antigüedad es solo tiempo transcurrido desde el inicio; no es un SLA.
const HOUR = 3_600_000

export const ageBuckets: { key: AgeBucket; label: string; color: string }[] = [
  { key: 'lt_1h', label: 'Menos de 1 h', color: '#cbd5e1' },
  { key: '1_to_4h', label: '1 a 4 h', color: '#f59e0b' },
  { key: '4_to_24h', label: '4 a 24 h', color: '#fb923c' },
  { key: 'gt_24h', label: 'Más de 24 h', color: '#f87171' },
]

export const ageBucketLabel = (key: string) => ageBuckets.find((bucket) => bucket.key === key)?.label

/** Tramo de un ticket abierto; null si el inicio es futuro o la fecha no es válida (se informan aparte). */
export function ageBucket(startAt: string, now = Date.now()): AgeBucket | null {
  const age = now - new Date(startAt).getTime()
  if (Number.isNaN(age) || age < 0) return null
  if (age < HOUR) return 'lt_1h'
  if (age < 4 * HOUR) return '1_to_4h'
  if (age <= 24 * HOUR) return '4_to_24h'
  return 'gt_24h'
}

/** «45 min», «2 h 15 min», «9 h», «1 d 4 h». */
export function formatAge(startAt: string, now = Date.now()): string {
  const minutes = Math.floor((now - new Date(startAt).getTime()) / 60_000)
  if (Number.isNaN(minutes)) return 'Fecha no válida'
  if (minutes < 0) return 'Inicio futuro'
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return minutes % 60 ? `${hours} h ${minutes % 60} min` : `${hours} h`
  return hours % 24 ? `${Math.floor(hours / 24)} d ${hours % 24} h` : `${Math.floor(hours / 24)} d`
}

/** URL de /tickets que reproduce exactamente un cuadro del Dashboard. */
export const ticketsUrl = (filters: Record<string, string>) => `/tickets?${new URLSearchParams(filters)}`
