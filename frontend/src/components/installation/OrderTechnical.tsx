import type { Circuit } from '../../types/catalog'
import type { NamedRef, OrderTechnical } from '../../types/installationOrders'
const ref = (row?: NamedRef | null): NamedRef | null => (row ? { id: row.id, name: row.name } : null)
export const technicalFromCircuit = (circuit: Circuit): OrderTechnical => ({ service_type: ref(circuit.service_type), node: ref(circuit.node), sector: ref(circuit.sector), device: ref(circuit.distribution_device), port: ref(circuit.distribution_port), cpe: ref(circuit.cpe_model) })
const rows: [keyof OrderTechnical, string][] = [['service_type', 'Tipo de servicio'], ['node', 'Nodo'], ['sector', 'Sector'], ['device', 'Equipo de distribución'], ['port', 'Puerto'], ['cpe', 'CPE']]
// Read-only: the circuit owns this data, the order never stores a copy of it.
export function OrderTechnicalData({ technical, title = 'Datos técnicos' }: { technical: OrderTechnical | null; title?: string }) {
 return <section aria-label={title}><h3 className="form-label">{title}</h3><dl className="installation-data">{rows.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{technical?.[key]?.name ?? 'No disponible'}</dd></div>)}</dl></section>
}
