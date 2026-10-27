import type { OptionalColumn } from '../components/TicketTable'

export const optionalColumns: { key: OptionalColumn; label: string }[] = [
  { key: 'node', label: 'Nodo' }, { key: 'sector', label: 'Sector' }, { key: 'type', label: 'Tipo' }, { key: 'end', label: 'Fin' },
]
// Sector queda visible: es la dimensión con la que el Dashboard agrupa los abiertos.
export const defaultHiddenColumns: OptionalColumn[] = ['node', 'type', 'end']
const storageKey = 'ticketyn_ticket_hidden_columns'

/** Valida lo almacenado: cualquier valor inesperado vuelve a los predeterminados. */
export function parseHiddenColumns(raw: string | null): OptionalColumn[] {
  try {
    const value: unknown = raw === null ? null : JSON.parse(raw)
    if (!Array.isArray(value)) return defaultHiddenColumns
    const known = optionalColumns.map((column) => column.key)
    return value.every((item) => known.includes(item)) ? [...new Set(value as OptionalColumn[])] : defaultHiddenColumns
  } catch { return defaultHiddenColumns }
}

export function loadHiddenColumns(): OptionalColumn[] {
  try { return parseHiddenColumns(localStorage.getItem(storageKey)) } catch { return defaultHiddenColumns }
}

export function saveHiddenColumns(hidden: OptionalColumn[]) {
  try { localStorage.setItem(storageKey, JSON.stringify(hidden)) } catch { /* almacenamiento no disponible: la preferencia solo dura la sesión */ }
}
