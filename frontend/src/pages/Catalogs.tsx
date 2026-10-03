import { useState } from 'react'
import { CatalogAdmin } from '../components/CatalogAdmin'
import type { CatalogKind } from '../types/catalog'

export function Catalogs() {
  const [kind, setKind] = useState<CatalogKind>('sectors')
  return <>
    <nav aria-label="Catálogos" className="segmented-control mb-4">
      {(['sectors', 'departments', 'incident-types', 'nodes', 'responsibles'] as const).map((value) => <button type="button" key={value} className="segment-button" aria-pressed={value === kind} onClick={() => setKind(value)}>{value === 'sectors' ? 'Sectores' : value === 'departments' ? 'Departamentos' : value === 'nodes' ? 'Nodos' : value === 'responsibles' ? 'Responsables' : 'Tipos de incidencia'}</button>)}
    </nav>
    <CatalogAdmin key={kind} kind={kind} />
  </>
}
