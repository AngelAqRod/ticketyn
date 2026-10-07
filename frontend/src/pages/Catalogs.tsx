import { useState } from 'react'
import { Layers3 } from 'lucide-react'
import { CatalogAdmin } from '../components/CatalogAdmin'
import type { CatalogKind } from '../types/catalog'

export function Catalogs() {
  const [kind, setKind] = useState<CatalogKind>('sectors')
  return <>
    <nav aria-label="Catálogos" className="segmented-control segmented-control--soft mb-4">
      <span className="icon-surface mx-1" aria-hidden="true"><Layers3 size={15} /></span>
      {(['sectors', 'departments', 'incident-types', 'nodes', 'responsibles'] as const).map((value) => <button type="button" key={value} className="segment-button" aria-pressed={value === kind} onClick={() => setKind(value)}>{value === 'sectors' ? 'Sectores' : value === 'departments' ? 'Departamentos' : value === 'nodes' ? 'Nodos' : value === 'responsibles' ? 'Responsables' : 'Tipos de incidencia'}</button>)}
    </nav>
    <CatalogAdmin key={kind} kind={kind} />
  </>
}
