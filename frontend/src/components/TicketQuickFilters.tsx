import { FilterSegment } from './FilterBar'
interface Props { params: URLSearchParams; change: (values: Record<string, string>) => void }

/**
 * Cápsulas de filtrado rápido. Solo escriben en la URL (useUrlFilters) y el listado se consulta en el backend.
 * Abiertos / Todos / Cerrados son excluyentes; «Sin responsable» y «Más de 24 h» son interruptores que implican Abiertos.
 * Sin conteos: obtenerlos exigiría consultas adicionales en cada cambio de búsqueda (el Dashboard ya los muestra).
 */
export function TicketQuickFilters({ params, change }: Props) {
  const status = params.get('status') ?? ''
  const unassigned = params.get('unassigned') === 'true'
  const older = params.get('age_bucket') === 'gt_24h'
  // Todos y Cerrados no son compatibles con condiciones que solo existen en abiertos.
  const setStatus = (value: string) => change({ status: value, ...(value === 'OPEN' ? {} : { unassigned: '', age_bucket: '' }) })
  return <div className="flex flex-wrap items-center gap-2">
    <FilterSegment label="Estado del ticket" options={[['OPEN', 'Abiertos'], ['', 'Todos'], ['CLOSED', 'Cerrados']]} value={status} onChange={setStatus} />
    <div className="segmented-control segmented-control--soft segmented-control--blue" role="group" aria-label="Filtros rápidos de abiertos">
      <button type="button" className="segment-button" aria-pressed={unassigned} onClick={() => change({ status: 'OPEN', unassigned: unassigned ? '' : 'true', responsible_id: '' })}>Sin responsable</button>
      <button type="button" className="segment-button" aria-pressed={older} onClick={() => change({ status: 'OPEN', age_bucket: older ? '' : 'gt_24h' })}>Más de 24 h</button>
    </div>
  </div>
}
