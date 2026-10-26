import { DeviceTemplateAdmin } from '../components/DeviceTemplateAdmin'
import { Can, usePermissions, catalogModule } from '../auth/permissions'
import { useLayoutEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, Layers3 } from 'lucide-react'
import { PortNomenclatureAdmin } from '../components/PortNomenclatureAdmin'
import { CatalogAdmin } from '../components/CatalogAdmin'
import type { CatalogKind } from '../types/catalog'

function scrollBehavior(): ScrollBehavior {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
}

// Scroll this strip only; never move the page or other scroll containers.
function revealOption(viewport: HTMLDivElement, option: HTMLElement, behavior: ScrollBehavior) {
  if (!viewport.clientWidth) return
  const bounds = viewport.getBoundingClientRect(), item = option.getBoundingClientRect()
  const padding = Number.parseFloat(window.getComputedStyle(viewport).paddingLeft) || 3
  const delta = item.left < bounds.left + padding ? item.left - bounds.left - padding
    : item.right > bounds.right - padding ? item.right - bounds.right + padding : 0
  const left = Math.max(0, Math.min(viewport.scrollWidth - viewport.clientWidth, viewport.scrollLeft + delta))
  if (delta && Math.abs(left - viewport.scrollLeft) > 0.5) viewport.scrollTo({ left, behavior })
}

export function Catalogs() {
  const access=usePermissions()
  const kinds:(CatalogKind | 'port-nomenclatures' | 'distribution-device-templates')[]=['sectors','departments','incident-types','nodes','positions','escalation-reasons','service-types','deactivation-reasons','cpe-models','internal-incident-types','providers','change-completion-types','change-types','port-nomenclatures', 'distribution-device-templates']
  const available=kinds.filter(value=>access.can(catalogModule(value)+'.view'))
  const [selected, setKind] = useState<CatalogKind | 'port-nomenclatures' | 'distribution-device-templates'>('sectors')
  const kind=available.includes(selected)?selected:available[0]
  const viewport = useRef<HTMLDivElement>(null)
  const [edges, setEdges] = useState({ previous: false, next: false })
  useLayoutEffect(() => {
    const element = viewport.current!
    const measure = () => setEdges(current => {
      const previous = element.scrollLeft > 1
      const next = element.scrollLeft + element.clientWidth < element.scrollWidth - 1
      return current.previous === previous && current.next === next ? current : { previous, next }
    })
    const resize = () => {
      const active = element.querySelector<HTMLElement>('[aria-pressed="true"]')
      if (active) revealOption(element, active, 'auto')
      measure()
    }
    element.addEventListener('scroll', measure, { passive: true })
    window.addEventListener('resize', resize)
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize)
    observer?.observe(element)
    Array.from(element.children).forEach(child => observer?.observe(child))
    resize()
    return () => { element.removeEventListener('scroll', measure); window.removeEventListener('resize', resize); observer?.disconnect() }
  }, [])
  useLayoutEffect(() => {
    const element = viewport.current!
    const active = element.querySelector<HTMLElement>('[aria-pressed="true"]')
    if (active) revealOption(element, active, scrollBehavior())
  }, [kind])
  function move(direction: number) {
    const element = viewport.current!
    element.scrollTo({ left: Math.max(0, Math.min(element.scrollWidth - element.clientWidth, element.scrollLeft + direction * element.clientWidth * 0.8)), behavior: scrollBehavior() })
  }
  return <>
    <nav aria-label="Catálogos" className="catalog-selector mb-4">
      <button type="button" className="catalog-selector-arrow" aria-label="Catálogos anteriores" aria-controls="catalog-selector-options" disabled={!edges.previous} onClick={() => move(-1)}><ChevronLeft size={16} /></button>
      <span className="icon-surface catalog-selector-icon" aria-hidden="true"><Layers3 size={15} /></span>
      <div className="catalog-selector-window">
        <span className={'catalog-selector-overflow catalog-selector-overflow-left' + (edges.previous ? ' is-visible' : '')} aria-hidden="true" />
        <div ref={viewport} id="catalog-selector-options" role="group" aria-label="Categorías de catálogos" className="catalog-selector-options">{available.map((value) => <button type="button" key={value} className="segment-button" aria-pressed={value === kind} onClick={() => setKind(value)} onFocus={event => { if (viewport.current) revealOption(viewport.current, event.currentTarget, scrollBehavior()) }}>{value === 'distribution-device-templates' ? 'Plantillas de equipos' : value === 'port-nomenclatures' ? 'Nomenclaturas de puertos' : value === 'change-types' ? 'Tipos de cambio' : value === 'change-completion-types' ? 'Tipos de finalización de cambios' : value === 'providers' ? 'Proveedores' : value === 'internal-incident-types' ? 'Tipos de incidencia interna' : value === 'cpe-models' ? 'Modelos de CPE' : value === 'service-types' ? 'Tipos de servicio' : value === 'deactivation-reasons' ? 'Motivos de baja' : value === 'positions' ? 'Puestos' : value === 'escalation-reasons' ? 'Motivos de escalamiento' : value === 'sectors' ? 'Sectores' : value === 'departments' ? 'Departamentos' : value === 'nodes' ? 'Nodos' : value === 'responsibles' ? 'Responsables' : 'Tipos de incidencia'}</button>)}</div>
        <span className={'catalog-selector-overflow catalog-selector-overflow-right' + (edges.next ? ' is-visible' : '')} aria-hidden="true" />
      </div>
      <button type="button" className="catalog-selector-arrow" aria-label="Catálogos siguientes" aria-controls="catalog-selector-options" disabled={!edges.next} onClick={() => move(1)}><ChevronRight size={16} /></button>
    </nav>
    {kind === 'distribution-device-templates' ? <DeviceTemplateAdmin /> : kind === 'port-nomenclatures' ? <PortNomenclatureAdmin /> : kind && <CatalogAdmin key={kind} kind={kind} />}
  </>
}
