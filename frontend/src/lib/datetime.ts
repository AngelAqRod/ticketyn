export function localDateTimeValue(date = new Date()): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${String(date.getFullYear()).padStart(4, '0')}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function localDateTimeToIso(value: string): string {
  // Date interpreta un datetime sin offset como hora local, no como UTC.
  const date = new Date(value)
  if (Number.isNaN(date.getTime()) || localDateTimeValue(date) !== value) {
    throw new Error('Introduce una fecha/hora local válida. Esa hora podría no existir por un cambio de horario.')
  }
  return date.toISOString()
}

export const ticketynTimezone = 'America/Guatemala'
export function ticketynDateTimeValue(date = new Date(), seconds = false): string {
  const parts = new Intl.DateTimeFormat('sv-SE', { timeZone: ticketynTimezone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', ...(seconds ? { second: '2-digit' as const } : {}), hourCycle: 'h23' }).formatToParts(date)
  const part = (name: string) => parts.find((item) => item.type === name)!.value
  return `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}${seconds ? ':' + part('second') : ''}`
}
export function ticketynDateTimeToIso(value: string): string {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(value)) throw new Error('Introduce una fecha/hora válida.')
  // Solve the IANA offset rather than relying on the administrator's browser zone.
  const normalized = value.length === 16 ? `${value}:00` : value
  const wallTime = new Date(`${normalized}Z`)
  let instant = wallTime
  if (Number.isNaN(instant.getTime())) throw new Error('Introduce una fecha/hora válida.')
  for (let i = 0; i < 3; i++) {
    const represented = new Date(`${ticketynDateTimeValue(instant, true)}Z`)
    instant = new Date(instant.getTime() + wallTime.getTime() - represented.getTime())
  }
  if (Number.isNaN(instant.getTime()) || ticketynDateTimeValue(instant, true) !== normalized) throw new Error('Introduce una fecha/hora válida.')
  return instant.toISOString()
}
