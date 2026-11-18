import { DeviceTemplateAdmin } from '../components/DeviceTemplateAdmin'
import { usePermissions, catalogModule } from '../auth/permissions'
import { useState } from 'react'
import { PortNomenclatureAdmin } from '../components/PortNomenclatureAdmin'
import { CatalogAdmin } from '../components/CatalogAdmin'
import { SideNavLayout, type SideNavGroup } from '../components/SideNavLayout'
import type { CatalogKind } from '../types/catalog'

type Kind = CatalogKind | 'port-nomenclatures' | 'distribution-device-templates'

const groups: SideNavGroup<Kind>[] = [
  { label: 'Red', items: [{ id: 'nodes', label: 'Nodos' }, { id: 'sectors', label: 'Sectores' }, { id: 'distribution-device-templates', label: 'Plantillas de equipos' }, { id: 'port-nomenclatures', label: 'Nomenclaturas de puertos' }, { id: 'cpe-models', label: 'Modelos de CPE' }, { id: 'providers', label: 'Proveedores' }] },
  { label: 'Servicio', items: [{ id: 'service-types', label: 'Tipos de servicio' }, { id: 'deactivation-reasons', label: 'Motivos de baja' }] },
  { label: 'Tickets e incidencias', items: [{ id: 'incident-types', label: 'Tipos de incidencia' }, { id: 'internal-incident-types', label: 'Tipos de incidencia interna' }, { id: 'escalation-reasons', label: 'Motivos de escalamiento' }] },
  { label: 'Cambios', items: [{ id: 'change-types', label: 'Tipos de cambio' }, { id: 'change-completion-types', label: 'Tipos de finalización de cambios' }] },
  { label: 'Solicitudes', items: [{ id: 'admin-request-types', label: 'Tipos de solicitud administrativa' }] },
  { label: 'Organización', items: [{ id: 'departments', label: 'Departamentos' }, { id: 'positions', label: 'Puestos' }] },
]

export function Catalogs() {
  const access = usePermissions()
  const allowed = groups.map(group => ({ ...group, items: group.items.filter(item => access.can(catalogModule(item.id) + '.view')) })).filter(group => group.items.length)
  const [selected, setKind] = useState<Kind>('sectors')
  const kind = allowed.some(group => group.items.some(item => item.id === selected)) ? selected : allowed[0]?.items[0].id
  return <SideNavLayout label="Catálogos" groups={allowed} active={kind} onSelect={setKind} searchLabel="Filtrar categorías">
    {kind === 'distribution-device-templates' ? <DeviceTemplateAdmin /> : kind === 'port-nomenclatures' ? <PortNomenclatureAdmin /> : kind && <CatalogAdmin key={kind} kind={kind} />}
  </SideNavLayout>
}
