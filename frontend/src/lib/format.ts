const dateFormatter = new Intl.DateTimeFormat('es', { dateStyle: 'medium', timeStyle: 'short' })

export function formatDate(value: string | null): string {
  if (value === null) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Fecha no válida' : dateFormatter.format(date)
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null) return 'En curso'
  const total = Math.floor(seconds)
  if (total < 60) return `${total} s`
  const minutes = Math.floor(total / 60)
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  const remainder = minutes % 60
  return `${hours} h${remainder ? ` ${remainder} min` : ''}`
}
