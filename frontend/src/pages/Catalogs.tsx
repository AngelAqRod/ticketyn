import { useState } from 'react'
import { Layers3 } from 'lucide-react'
import { CatalogAdmin } from '../components/CatalogAdmin'
import type { CatalogKind } from '../types/catalog'

export function Catalogs() {
  const [kind, setKind] = useState<CatalogKind>('sectors')
  return <>
    <nav aria-label="Catálogos" className="catalog-selector mb-4">
      <span className="icon-surface mx-1 catalog-selector-icon" aria-hidden="true"><Layers3 size={15} /></span>
      <div className="catalog-selector-options">{(['sectors', 'departments', 'incident-types', 'nodes', 'responsibles', 'positions', 'escalation-reasons', 'service-types', 'deactivation-reasons', 'cpe-models'] as const).map((value) => <button type="button" key={value} className="segment-button" aria-pressed={value === kind} onClick={() => setKind(value)}>{value === 'cpe-models' ? 'Modelos de CPE' : value === 'service-types' ? 'Tipos de servicio' : value === 'deactivation-reasons' ? 'Motivos de baja' : value === 'positions' ? 'Puestos' : value === 'escalation-reasons' ? 'Motivos de escalamiento' : value === 'sectors' ? 'Sectores' : value === 'departments' ? 'Departamentos' : value === 'nodes' ? 'Nodos' : value === 'responsibles' ? 'Responsables' : 'Tipos de incidencia'}</button>)}</div>
    </nav>
    <CatalogAdmin key={kind} kind={kind} />
  </>
}
