import { useState } from 'react'
import { CatalogAdmin } from '../components/CatalogAdmin'
import type { CatalogKind } from '../types/catalog'

export function Catalogs() {
  const [kind, setKind] = useState<CatalogKind>('sectors')
  return <>
    <nav aria-label="Catálogos" className="mb-6 flex flex-wrap gap-2">
      {(['sectors', 'departments', 'incident-types'] as const).map((value) => <button type="button" key={value} className={value === kind ? 'button-primary' : 'button-secondary'} aria-pressed={value === kind} onClick={() => setKind(value)}>{value === 'sectors' ? 'Sectores' : value === 'departments' ? 'Departamentos' : 'Tipos de incidencia'}</button>)}
    </nav>
    <CatalogAdmin key={kind} kind={kind} />
  </>
}
