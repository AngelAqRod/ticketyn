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
