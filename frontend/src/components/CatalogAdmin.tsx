import { CircuitDistributionFields } from './CircuitDistributionFields'
import { CircuitsNavigation } from './CircuitsNavigation'
import { ResponsibleAccess } from './ResponsibleAccess'
import { allPages, type Account } from '../api/security'
import { Can, usePermissions, catalogModule } from '../auth/permissions'
import { postJson, patchJson } from '../api/client'
import { FilterHeading } from './FilterHeading'
import { CircuitActions } from './CircuitActions'
import { confirmDeactivation } from '../lib/catalogActions'
import { capacityInMicroMbps } from '../lib/capacity'
import { CapacityFields } from './CapacityFields'
import { RequestState } from './RequestState'
import { FeedbackMessage } from './FeedbackMessage'
import { ApiError } from '../api/client'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router'
import { Network, Users, Ticket, Pencil, Power, Trash2, Plus, Layers3, ArrowUpRight } from 'lucide-react'
import { CatalogDeleteConfirmation } from './CatalogDeleteConfirmation'
import { QuickCatalogCreate } from './QuickCatalogCreate'
import { SearchableSelect } from './SearchableSelect'
import { useUrlFilters } from '../hooks/useUrlFilters'
import { circuitFilterKeys } from '../lib/ticketFilters'
import type { FormEvent } from 'react'
import * as api from '../api'
import type { CatalogKind, Circuit, Customer, NamedCatalog, Position, PositionInput } from '../types/catalog'
import { formatDate, formatTableDate } from '../lib/format'
import { FormField } from './FormField'
import { PageHeading } from './PageHeading'
import { FilterBar, FilterSegment } from './FilterBar'
import { FilterChips, type FilterChipItem } from './FilterChips'

const labels = {
  'change-types': { title: 'Tipos de cambio', singular: 'tipo de cambio', empty: 'tipos de cambio', description: 'Clasificación de trabajos operativos y ventanas de mantenimiento.' },
  'change-completion-types': { title: 'Tipos de finalización de cambios', singular: 'tipo de finalización', empty: 'tipos de finalización', description: 'Elegibilidad para eficiencia; los cambios finalizados conservan su valor histórico.' },
  'cpe-models': { title: 'Modelos de CPE', singular: 'modelo', empty: 'modelos de CPE', description: 'Modelos actuales de equipos de cliente.' },
  'service-types': { title: 'Tipos de servicio', singular: 'tipo de servicio', empty: 'tipos de servicio', description: 'Tipos configurables asociados opcionalmente a circuitos.' },
  'deactivation-reasons': { title: 'Motivos de baja', singular: 'motivo de baja', empty: 'motivos de baja', description: 'Desactivar conserva los registros operativos históricos.' },
  positions: { title: 'Puestos', singular: 'puesto', empty: 'puestos', description: 'Puestos configurables por departamento, sin jerarquía obligatoria.' },
  'escalation-reasons': { title: 'Motivos de escalamiento', singular: 'motivo de escalamiento', empty: 'motivos', description: 'Solicitudes de apoyo; desactivar conserva el historial.' },
  nodes: { title: "Nodos", singular: "nodo", empty: "nodos", description: "Nodos de distribución asociados a circuitos." },
  responsibles: { title: "Responsables", singular: "responsable", empty: "responsables", description: "Asignados operativos de los tickets." },
  customers: { title: 'Clientes', singular: 'cliente', empty: 'clientes', description: 'Clientes y sus códigos de negocio.' },
  circuits: { title: 'Circuitos', singular: 'circuito', empty: 'circuitos', description: 'Circuitos y servicios contratados por tus clientes.' },
  'internal-incident-types': { title: 'Tipos de incidencia interna', singular: 'tipo de incidencia interna', empty: 'tipos de incidencia interna', description: 'Clasificación de incidencias de infraestructura y NOC.' },
  providers: { title: 'Proveedores', singular: 'proveedor', empty: 'proveedores', description: 'Proveedores atribuibles a incidencias internas.' },
  sectors: { title: 'Sectores', singular: 'sector', empty: 'sectores', description: 'Administra los sectores de esta instalación.' },
  departments: { title: 'Departamentos', singular: 'departamento', empty: 'departamentos', description: 'Administra los departamentos de esta instalación.' },
  'incident-types': { title: 'Tipos de incidencia', singular: 'tipo de incidencia', empty: 'tipos de incidencia', description: 'Administra los tipos de incidencia de esta instalación.' },
}

type CatalogItem = Customer | Circuit | NamedCatalog
interface Draft { cpeManagementIp: string; appliesEfficiency: boolean; sectorId: string; id: number | null; code: string; name: string; customerId: string; nodeId: string; distributionDeviceId: string; distributionPortId: string; active: boolean; detail: string; departmentId: string; positionId: string; operationalSelectable: boolean; capacity: string; capacityUnit: string; serviceTypeId: string; cpeModelId: string; escalationMode: 'GENERAL' | 'INDIVIDUAL'; generalEscalationTime: string; escalationDestinations: { target_position_id: number; time_minutes: string }[] }
const blank = (): Draft => ({ cpeManagementIp: '', operationalSelectable: true, appliesEfficiency: false, sectorId: '', id: null, code: '', name: '', customerId: '', nodeId: '', distributionDeviceId: '', distributionPortId: '', active: true, detail: '', departmentId: '', positionId: '', capacity: '', capacityUnit: 'Mbps', serviceTypeId: '', cpeModelId: '', escalationMode: 'GENERAL', generalEscalationTime: '', escalationDestinations: [] })
const message = (error: unknown) => error instanceof Error ? error.message : 'Ocurrió un error inesperado.'

function list(kind: CatalogKind, signal: AbortSignal, filters?: URLSearchParams): Promise<CatalogItem[]> {
  switch (kind) {
    case 'change-types': return api.listChangeTypes(signal, true)
    case 'change-completion-types': return api.listChangeCompletionTypes(signal, true)
    case 'internal-incident-types': return api.listInternalIncidentTypes(signal, true)
    case 'providers': return api.listProviders(signal, true)
    case 'cpe-models': return api.listCpeModels(signal, true)
    case 'service-types': return api.listServiceTypes(signal, true)
    case 'deactivation-reasons': return api.listDeactivationReasons(signal, true)
    case 'positions': return api.listPositions(signal, true, filters?.get('department_id') ? Number(filters.get('department_id')) : undefined)
    case 'escalation-reasons': return api.listEscalationReasons(signal, true)
    case 'nodes': return api.listNodes(signal, true)
    case 'responsibles': return api.listResponsibles(signal, true)
    case 'customers': return api.listCustomers(signal, true)
    case 'circuits': return api.listCircuits(filters?.get('customer_id') ? Number(filters.get('customer_id')) : undefined, signal, true, { search: filters?.get('search') || undefined, sector_id: filters?.get('sector_id') ? Number(filters.get('sector_id')) : undefined, node_id: filters?.get('node_id') ? Number(filters.get('node_id')) : undefined, active: filters?.get('active') === 'true' ? true : filters?.get('active') === 'false' ? false : undefined })
    case 'sectors': return api.listSectors(signal, true)
    case 'departments': return api.listDepartments(signal, true)
    case 'incident-types': return api.listIncidentTypes(signal, true)
  }
}

function save(kind: CatalogKind, draft: Draft, original?: CatalogItem): Promise<CatalogItem> {
  const id = draft.id
  const named = { name: draft.name.trim(), active: draft.active }
  switch (kind) {
    case 'change-types': { const payload = {...named, description:draft.detail.trim() || null}; return id === null ? postJson('/api/change-types',payload) : patchJson(`/api/change-types/${id}`,payload) }
    case 'change-completion-types': { const payload = {...named, description:draft.detail.trim() || null, applies_efficiency:draft.appliesEfficiency}; return id === null ? postJson('/api/change-completion-types',payload) : patchJson(`/api/change-completion-types/${id}`,payload) }
    case 'providers': { const payload = { ...named, description: draft.detail.trim() || null }; return id === null ? postJson('/api/providers', payload) : patchJson(`/api/providers/${id}`, payload) }
    case 'internal-incident-types': return id === null ? postJson('/api/internal-incident-types', named) : patchJson(`/api/internal-incident-types/${id}`, named)
    case 'cpe-models': return id === null ? api.createCpeModel(named) : api.updateCpeModel(id, named)
    case 'service-types': return id === null ? api.createServiceType(named) : api.updateServiceType(id, named)
    case 'deactivation-reasons': { const payload = { ...named, description: draft.detail.trim() || null }; return id === null ? api.createDeactivationReason(payload) : api.updateDeactivationReason(id, payload) }
    case 'escalation-reasons': { const payload = { ...named, description: draft.detail.trim() || null }; return id === null ? api.createEscalationReason(payload) : api.updateEscalationReason(id, payload) }
    case 'positions': {
      const prevDestinations = original && 'destinations' in (original as Position) ? (original as Position).destinations : undefined
      const hasDestinations = draft.escalationDestinations.length > 0
      const payload: PositionInput = {
        ...named,
        department_id: Number(draft.departmentId),
        description: draft.detail.trim() || null,
        ...(hasDestinations ? {
          escalation_mode: draft.escalationMode,
          general_escalation_time_minutes: draft.escalationMode === 'GENERAL' && draft.generalEscalationTime ? Number(draft.generalEscalationTime) : null,
          destinations: draft.escalationDestinations.map((d) => ({
            target_position_id: d.target_position_id,
            time_minutes: draft.escalationMode === 'INDIVIDUAL' && d.time_minutes ? Number(d.time_minutes) : null,
          })),
        } : (prevDestinations && prevDestinations.length > 0 ? {
          destinations: [],
        } : {})),
      }
      return id === null ? api.createPosition(payload) : api.updatePosition(id, payload)
    }
    case 'nodes': return id === null ? api.createNode(named) : api.updateNode(id, named)
    case 'responsibles': { const payload = { ...named, operational_selectable: draft.operationalSelectable, department_id: draft.departmentId ? Number(draft.departmentId) : null, position_id: draft.positionId ? Number(draft.positionId) : null }; return id === null ? api.createResponsible(payload) : api.updateResponsible(id, payload) }
    case 'customers': {
      const payload = { ...named, customer_code: draft.code.trim() }
      return id === null ? api.createCustomer(payload) : api.updateCustomer(id, payload)
    }
    case 'circuits': {
      const deviceId = draft.distributionDeviceId ? Number(draft.distributionDeviceId) : null
      const portId = draft.distributionPortId ? Number(draft.distributionPortId) : null
      const previousDevice = original && 'distribution_device_id' in original ? original.distribution_device_id ?? null : null
      const previousPort = original && 'distribution_port_id' in original ? original.distribution_port_id ?? null : null
      const distribution = {
        ...((id === null ? deviceId !== null : deviceId !== previousDevice) ? { distribution_device_id: deviceId } : {}),
        ...((id === null ? portId !== null : portId !== previousPort) ? { distribution_port_id: portId } : {}),
      }
      const managementIp = draft.cpeManagementIp.trim() || null
      const previousIp = original && 'cpe_management_ip' in original ? original.cpe_management_ip ?? null : null
      const payload = { ...distribution, ...((id === null || managementIp !== previousIp) ? { cpe_management_ip: managementIp } : {}), cpe_model_id: draft.cpeModelId ? Number(draft.cpeModelId) : null, sector_id: Number(draft.sectorId), service_type_id: draft.serviceTypeId ? Number(draft.serviceTypeId) : null, initial_capacity: draft.capacity || null, initial_capacity_unit: draft.capacity ? draft.capacityUnit : null, description: draft.name.trim(), circuit_code: draft.code.trim(), node_id: Number(draft.nodeId), customer_id: Number(draft.customerId), active: draft.active }
      return id === null ? api.createCircuit(payload) : api.updateCircuit(id, payload)
    }
    case 'sectors': return id === null ? api.createSector(named) : api.updateSector(id, named)
    case 'departments': return id === null ? api.createDepartment(named) : api.updateDepartment(id, named)
    case 'incident-types': return id === null ? api.createIncidentType(named) : api.updateIncidentType(id, named)
  }
}

function changeActive(kind: CatalogKind, id: number, active: boolean): Promise<CatalogItem> {
  switch (kind) {
    case 'change-types': return patchJson(`/api/change-types/${id}`, { active })
    case 'change-completion-types': return patchJson(`/api/change-completion-types/${id}`, { active })
    case 'providers': return patchJson(`/api/providers/${id}`, { active })
    case 'internal-incident-types': return patchJson(`/api/internal-incident-types/${id}`, { active })
    case 'cpe-models': return api.updateCpeModel(id, { active })
    case 'service-types': return api.updateServiceType(id, { active })
    case 'deactivation-reasons': return api.updateDeactivationReason(id, { active })
    case 'escalation-reasons': return api.updateEscalationReason(id, { active })
    case 'positions': return api.updatePosition(id, { active })
    case 'nodes': return api.updateNode(id, { active })
    case 'responsibles': return api.updateResponsible(id, { active })
    case 'customers': return api.updateCustomer(id, { active })
    case 'circuits': return api.updateCircuit(id, { active })
    case 'sectors': return api.updateSector(id, { active })
    case 'departments': return api.updateDepartment(id, { active })
    case 'incident-types': return api.updateIncidentType(id, { active })
  }
}

const catalogName = (item: CatalogItem) => 'circuit_code' in item ? item.description : item.name
const catalogCode = (item: CatalogItem) => 'customer_code' in item ? item.customer_code : 'circuit_code' in item ? item.circuit_code : ''
function draftFor(item: CatalogItem, kind: CatalogKind): Draft {
  const pos = item as Position
  return {
    cpeManagementIp: 'cpe_management_ip' in item ? item.cpe_management_ip ?? '' : '',
    distributionDeviceId: 'distribution_device_id' in item && item.distribution_device_id ? String(item.distribution_device_id) : '',
    distributionPortId: 'distribution_port_id' in item && item.distribution_port_id ? String(item.distribution_port_id) : '',
    operationalSelectable: !('operational_selectable' in item) || item.operational_selectable !== false,
    appliesEfficiency: 'applies_efficiency' in item && Boolean(item.applies_efficiency),
    cpeModelId: 'cpe_model_id' in item && item.cpe_model_id ? String(item.cpe_model_id) : '',
    sectorId: 'sector_id' in item && item.sector_id ? String(item.sector_id) : '',
    id: item.id,
    serviceTypeId: 'service_type_id' in item && item.service_type_id ? String(item.service_type_id) : '',
    capacity: 'initial_capacity' in item ? String(item.initial_capacity ?? '') : '',
    capacityUnit: 'initial_capacity_unit' in item ? item.initial_capacity_unit ?? 'Mbps' : 'Mbps',
    code: catalogCode(item),
    name: catalogName(item),
    nodeId: 'node_id' in item && item.node_id ? String(item.node_id) : '',
    customerId: 'customer_id' in item ? String(item.customer_id) : '',
    active: item.active,
    departmentId: 'department_id' in item && item.department_id ? String(item.department_id) : '',
    positionId: 'position_id' in item && item.position_id ? String(item.position_id) : '',
    detail: (kind === 'positions' || kind === 'escalation-reasons' || kind === 'deactivation-reasons' || kind === 'providers' || kind === 'change-types' || kind === 'change-completion-types') && 'description' in item ? String(item.description ?? '') : '',
    escalationMode: kind === 'positions' && 'escalation_mode' in pos && pos.escalation_mode ? pos.escalation_mode : 'GENERAL',
    generalEscalationTime: kind === 'positions' && 'general_escalation_time_minutes' in pos && pos.general_escalation_time_minutes ? String(pos.general_escalation_time_minutes) : '',
    escalationDestinations: kind === 'positions' && 'destinations' in pos && Array.isArray(pos.destinations)
      ? pos.destinations.map(d => ({ target_position_id: d.target_position_id, time_minutes: d.time_minutes ? String(d.time_minutes) : '' }))
      : [],
  }
}

export function CatalogAdmin({ kind, embedded = false, administrativeAccess = false, circuitEditor }: { kind: CatalogKind; embedded?: boolean; administrativeAccess?: boolean; circuitEditor?: { item: Circuit; onSaved: (item: Circuit) => void; onCancel: () => void; onBusyChange: (busy: boolean) => void } }) {
  const access=usePermissions(), permissionModule=catalogModule(kind)
  const info = labels[kind]
  const manageAccess = kind === 'responsibles' && administrativeAccess && access.can('accounts.manage')
  const [accessRows, setAccessRows] = useState<Account[]>([])
  const [accessId, setAccessId] = useState<number | null>(null)
  const refreshedModule = kind === 'customers' || kind === 'circuits'
  const RecordIcon = kind === 'circuits' ? Network : Users
  const editorItem = circuitEditor?.item
  const [items, setItems] = useState<CatalogItem[]>(editorItem ? [editorItem] : [])
  const [cpeModels, setCpeModels] = useState<NamedCatalog[]>([])
  const [serviceTypes, setServiceTypes] = useState<NamedCatalog[]>([])
  const [departments, setDepartments] = useState<NamedCatalog[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [departmentFilter, setDepartmentFilter] = useState('')
  const [sectors, setSectors] = useState<NamedCatalog[]>([])
  const [nodes, setNodes] = useState<NamedCatalog[]>([])
  const [quickNode, setQuickNode] = useState(false)
  const [distributionOpen, setDistributionOpen] = useState(false)
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [apiInvalidFields, setApiInvalidFields] = useState<string[]>([])
  const navigationState: unknown = useLocation().state
  const [notice, setNotice] = useState<string | null>(() => kind === 'circuits' && navigationState && typeof navigationState === 'object' && 'deletedCircuitCode' in navigationState && typeof navigationState.deletedCircuitCode === 'string' ? `Circuito ${navigationState.deletedCircuitCode} eliminado correctamente.` : null)
  const [retry, setRetry] = useState(0)
  const [localSearch, setLocalSearch] = useState('')
  const { params, change, clear } = useUrlFilters(circuitFilterKeys)
  const filterKey = kind === 'circuits' ? params.toString() : kind === 'positions' ? new URLSearchParams(departmentFilter ? { department_id: departmentFilter } : {}).toString() : ''
  const search = kind === 'circuits' ? params.get('search') ?? '' : localSearch
  const setSearch = (value: string) => kind === 'circuits' ? change({ search: value }) : setLocalSearch(value)
  const customerCache = useRef<Customer[] | null>(null)
  const [draft, setDraft] = useState<Draft | null>(() => editorItem ? draftFor(editorItem, kind) : null)
  const expandedForm = useRef<HTMLFormElement>(null)
  const revealForm = useRef(false)
  useEffect(() => {
    if (!draft || !revealForm.current) return
    revealForm.current = false
    const form = expandedForm.current
    if (!form || circuitEditor || form.closest('dialog')) return
    form.scrollIntoView?.({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' })
  }, [draft, circuitEditor])
  const [deleting, setDeleting] = useState<Customer | Circuit | null>(null)
  const [busy, setBusy] = useState(false)
  const sending = useRef(false)
  const newRecordButton = useRef<HTMLButtonElement>(null)
  const mounted = useRef(true)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setLoadError(null)
    Promise.all([editorItem ? Promise.resolve([editorItem]) : (kind === 'responsibles' && !access.can('catalogs.responsibles.view') ? allPages<Account>('/api/responsibles/access', controller.signal) : list(kind, controller.signal, new URLSearchParams(filterKey))), kind === 'circuits' ? (customerCache.current ? Promise.resolve(customerCache.current) : api.listCustomers(controller.signal, true)) : Promise.resolve([]), kind === 'circuits' ? api.listNodes(controller.signal, true) : Promise.resolve([]), kind === 'positions' || kind === 'responsibles' && access.can('catalogs.departments.lookup') ? api.listDepartments(controller.signal, true) : Promise.resolve([]), (kind === 'positions' || (kind === 'responsibles' && access.can('catalogs.positions.lookup'))) ? api.listPositions(controller.signal, true) : Promise.resolve([]), kind === 'circuits' ? api.listServiceTypes(controller.signal, true) : Promise.resolve([]), kind === 'circuits' ? api.listSectors(controller.signal, true) : Promise.resolve([]), kind === 'circuits' ? api.listCpeModels(controller.signal, true) : Promise.resolve([])]).then(([rows, clients, nodeRows, departmentRows, positionRows, serviceRows, sectorRows, cpeRows]) => {
      if (!controller.signal.aborted) { setCpeModels(cpeRows); setSectors(sectorRows); setServiceTypes(serviceRows); setItems(rows); setCustomers(clients); setNodes(nodeRows); setDepartments(departmentRows); setPositions(positionRows); if (kind === 'circuits') customerCache.current = clients; setLoading(false) }
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) { setLoadError(message(failure)); setLoading(false) }
    })
    return () => controller.abort()
  }, [kind, retry, filterKey, editorItem])

  useEffect(() => {
    if (!manageAccess) { setAccessRows([]); setAccessId(null); return }
    const controller = new AbortController()
    allPages<Account>('/api/responsibles/access', controller.signal).then(rows => { if (!controller.signal.aborted) { setAccessRows(rows); setAccessId(current => current !== null && !rows.some(row => row.id === current) ? null : current) } }).catch(cause => { if (!controller.signal.aborted) setError(message(cause)) })
    return () => controller.abort()
  }, [manageAccess, retry, access.permissions.join('\0')])

  const customerLabel = (id: number) => {
    const customer = customers.find((item) => item.id === id)
    return customer ? `${customer.customer_code} — ${customer.name}` : 'Cliente no disponible'
  }
  const name = catalogName
  const code = catalogCode
  const visible = items.filter((item) => {
    if (!`${code(item)} ${name(item)}`.toLocaleLowerCase().includes((kind === 'circuits' ? search : search.trim()).toLocaleLowerCase())) return false
    if (kind !== 'circuits') return true
    if (params.get('customer_id') && (!('customer_id' in item) || String(item.customer_id) !== params.get('customer_id'))) return false
    if (params.get('sector_id') && (!('sector_id' in item) || String(item.sector_id) !== params.get('sector_id'))) return false
    if (params.get('node_id') && (!('node_id' in item) || String(item.node_id) !== params.get('node_id'))) return false
    return !params.get('active') || String(item.active) === params.get('active')
  })
  const ordered = [...visible].sort((a, b) => (code(a) || name(a)).localeCompare(code(b) || name(b)) || a.id - b.id)

  function edit(item?: CatalogItem) {
    revealForm.current = true
    setError(null); setApiInvalidFields([]); setNotice(null)
    setDraft(item ? draftFor(item, kind) : blank())
  }
  async function persist(operation: () => Promise<CatalogItem>, success: string, closeForm = false) {
    if (sending.current) return
    sending.current = true; setBusy(true); circuitEditor?.onBusyChange(true); setError(null); setApiInvalidFields([]); setNotice(null)
    try {
      const item = await operation()
      if (mounted.current) {
        setItems((current) => current.some((row) => row.id === item.id) ? current.map((row) => row.id === item.id ? item : row) : [...current, item])
        setNotice(success)
        if (closeForm) { if (circuitEditor && 'circuit_code' in item) circuitEditor.onSaved(item); else setDraft(null) }
      }
    } catch (failure) { if (mounted.current) { setError(message(failure)); setApiInvalidFields(failure instanceof ApiError ? failure.fields : []) } }
    finally { sending.current = false; if (mounted.current) { setBusy(false); circuitEditor?.onBusyChange(false) } }
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (kind === 'circuits' && draft && !draft.nodeId) { setError('Selecciona un Nodo antes de guardar.'); return }
    if (kind === 'circuits' && draft && !draft.sectorId) { setError('Selecciona un Sector antes de guardar.'); return }
    if (!draft || sending.current || distributionOpen) return
    setApiInvalidFields([])
    if (!draft.name.trim() || ((kind === 'customers' || kind === 'circuits') && !draft.code.trim()) || (kind === 'circuits' && !draft.customerId) || (kind === 'positions' && !draft.departmentId)) {
      setError('Completa los campos obligatorios antes de guardar.'); return
    }
    if (kind === 'positions' && draft) {
      if (draft.escalationDestinations.length > 0) {
        if (draft.escalationMode === 'GENERAL') {
          const generalTime = Number(draft.generalEscalationTime)
          if (!draft.generalEscalationTime.trim() || isNaN(generalTime) || generalTime <= 0 || !Number.isInteger(generalTime)) {
            setError('Indica un tiempo general de escalamiento en minutos (número entero mayor a 0).')
            return
          }
        } else if (draft.escalationMode === 'INDIVIDUAL') {
          const invalidDest = draft.escalationDestinations.some(d => {
            const t = Number(d.time_minutes)
            return !d.time_minutes.trim() || isNaN(t) || t <= 0 || !Number.isInteger(t)
          })
          if (invalidDest) {
            setError('Todos los destinos deben tener un tiempo de escalamiento en minutos (número entero mayor a 0).')
            return
          }
        }
      }
    }
    if (kind === 'circuits' && draft.capacity) { try { capacityInMicroMbps(draft.capacity, draft.capacityUnit) } catch (failure) { setError(message(failure)); return } }
    if (!draft.active && (draft.id === null || items.find((item) => item.id === draft.id)?.active) && !confirmDeactivation()) return
    void persist(() => save(kind, draft, items.find(item => item.id === draft.id)), draft.id === null ? 'Registro creado correctamente.' : 'Cambios guardados correctamente.', true)
  }
  function toggle(item: CatalogItem) {
    if (sending.current || (item.active && !confirmDeactivation())) return
    void persist(() => changeActive(kind, item.id, !item.active), item.active ? 'Registro desactivado. Los tickets históricos conservan su referencia.' : 'Registro activado correctamente.')
  }

  return <>
    {!circuitEditor && (embedded ? (
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="toolbar-heading">{info.title}</h2>
        <Can permission={permissionModule+".create"}>
          <button ref={newRecordButton} type="button" className={`button-primary ${kind === 'customers' || kind === 'circuits' ? 'button-primary--blue' : 'button-primary--slate'} rounded-full shadow-sm`} disabled={busy || loading || Boolean(loadError)} onClick={() => edit()}>
            <Plus size={15} aria-hidden="true" />
            Nuevo {info.singular}
          </button>
        </Can>
      </div>
    ) : (
      <PageHeading
        title={info.title}
        description={info.description}
        telemetry={
          !loading && !loadError && items.length > 0 && (
            <span className="heading-telemetry">
              <span>Total:</span>
              <strong className={kind === 'customers' || kind === 'circuits' ? 'telemetry-value--blue' : 'telemetry-value--slate'}>
                {items.length}
              </strong>
              {items.some((i) => !i.active) && (
                <>
                  <span className="text-slate-600">·</span>
                  <span>Activos:</span>
                  <strong className="text-emerald-400">
                    {items.filter((i) => i.active).length}
                  </strong>
                </>
              )}
            </span>
          )
        }
        action={
          <Can permission={permissionModule+".create"}>
            <button
              ref={newRecordButton}
              type="button"
              className={`button-primary ${kind === 'customers' || kind === 'circuits' ? 'button-primary--blue' : 'button-primary--slate'} rounded-full shadow-sm`}
              disabled={busy || loading || Boolean(loadError)}
              onClick={() => edit()}
            >
              <Plus size={15} aria-hidden="true" />
              Nuevo {info.singular}
            </button>
          </Can>
        }
      />
    ))}
    {kind === 'circuits' && <CircuitsNavigation />}
    {accessId !== null && manageAccess && <ResponsibleAccess key={accessId} id={accessId} onClose={() => setAccessId(null)} onSaved={() => setRetry(value => value + 1)} />}
    {notice && <FeedbackMessage variant="success" className="mb-4">{notice}</FeedbackMessage>}
    {error && <FeedbackMessage id="catalog-form-error" variant="error" className="mb-4">{error}</FeedbackMessage>}
    {circuitEditor && <RequestState compact loading={loading} loadingText="Cargando catálogos del circuito..." errorTitle="" error={loadError} onRetry={() => setRetry(retry + 1)} />}
    {draft && access.can(permissionModule+(draft.id===null?".create":".edit")) && (
      <form
        ref={expandedForm}
        className={`form-surface mb-5 ${
          kind === 'customers' || kind === 'circuits'
            ? 'p-6 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl space-y-4'
            : 'p-6 rounded-2xl bg-[#0b1426] border border-slate-700/60 shadow-xl space-y-4'
        }`}
        aria-label={`${draft.id === null ? 'Crear' : 'Editar'} ${info.singular}`}
        onSubmit={submit}
        noValidate
        aria-describedby={error ? "catalog-form-error" : undefined}
      >
        {kind === 'customers' || kind === 'circuits' ? (
          <div className="flex items-center gap-2 border-b border-sky-500/15 pb-2.5 mb-4">
            <span
              className="flex h-6 w-6 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs"
              aria-hidden="true"
            >
              {kind === 'customers' ? <Users size={13} /> : <Network size={13} />}
            </span>
            <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
              {draft.id === null ? 'Nuevo' : 'Editar'} {info.singular}
            </h2>
          </div>
        ) : (
          <div className="flex items-center gap-2 border-b border-slate-700/60 pb-2.5 mb-4">
            <span
              className="flex h-6 w-6 items-center justify-center rounded-lg bg-slate-800/80 border border-slate-700/80 text-slate-300 text-xs"
              aria-hidden="true"
            >
              {kind === 'responsibles' ? <Users size={13} /> : <Layers3 size={13} />}
            </span>
            <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
              {draft.id === null ? 'Nuevo' : 'Editar'} {info.singular}
            </h2>
          </div>
        )}
        <fieldset disabled={busy || Boolean(circuitEditor && (loading || loadError))} className="grid gap-3 sm:grid-cols-2"><legend className="sr-only">Datos del registro</legend>
          {kind === 'circuits' && (
            <FormField
              describedBy={error ? "catalog-form-error" : undefined}
              invalid={(error === "Completa los campos obligatorios antes de guardar." && !draft.customerId.trim()) || apiInvalidFields.includes("customer_id")}
              id="admin-customer"
              label="Cliente"
              required
            >
              <SearchableSelect
                id="admin-customer"
                label="Cliente"
                required
                value={draft.customerId}
                onChange={(value) => setDraft({ ...draft, customerId: value })}
                options={customers
                  .filter((item) => item.active || String(item.id) === draft.customerId)
                  .map((item) => ({
                    value: String(item.id),
                    label: item.customer_code && item.name ? `${item.customer_code} — ${item.name}` : (item.customer_code || item.name || 'Cliente'),
                    disabled: !item.active,
                  }))}
                placeholder="Selecciona un cliente"
                emptyMessage="No hay clientes activos."
                noMatchMessage="No se encontraron clientes."
              />
            </FormField>
          )}
          {kind === 'circuits' && <FormField describedBy={error ? "catalog-form-error" : undefined} invalid={Boolean(error && !draft.nodeId) || apiInvalidFields.includes("node_id")} id="admin-node" required label="Nodo"><div className="flex gap-2"><div className="min-w-0 flex-1"><SearchableSelect id="admin-node" required label="Nodo" value={draft.nodeId} onChange={(value) => setDraft(current => current ? { ...current, nodeId: value, ...(value !== current.nodeId ? { distributionDeviceId: '', distributionPortId: '' } : {}) } : current)} options={nodes.filter((item) => item.active || String(item.id) === draft.nodeId).map((item) => ({ value: String(item.id), label: item.name, disabled: !item.active }))} placeholder="Selecciona un nodo" emptyMessage="No hay nodos activos." noMatchMessage="No se encontraron nodos." /></div><Can anyOf={["catalogs.nodes.create","context.nodes.create"]}><button type="button" className="button-secondary" aria-label="Nuevo nodo" title="Nuevo nodo" onClick={() => setQuickNode(true)}>+</button></Can></div></FormField>}
          {kind === 'circuits' && <CircuitDistributionFields key={draft.id ?? 'new'} nodeId={draft.nodeId} nodeName={nodes.find(node => String(node.id) === draft.nodeId)?.name ?? ''} deviceId={draft.distributionDeviceId} portId={draft.distributionPortId}
            original={items.find((item): item is Circuit => item.id === draft.id && 'circuit_code' in item)} disabled={busy} invalidFields={apiInvalidFields} onModalChange={setDistributionOpen}
            onChange={(distributionDeviceId, distributionPortId) => setDraft(current => current ? { ...current, distributionDeviceId, distributionPortId } : current)} />}
          {(kind === 'customers' || kind === 'circuits') && <FormField describedBy={error ? "catalog-form-error" : undefined} invalid={(error === "Completa los campos obligatorios antes de guardar." && !draft.code.trim()) || apiInvalidFields.includes(kind === "circuits" ? "circuit_code" : "customer_code")} id="admin-code" label={kind === 'customers' ? 'Código de cliente' : 'Código de circuito'} required><input id="admin-code" className="form-input font-mono" required value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value })} /></FormField>}
          <FormField describedBy={error ? "catalog-form-error" : undefined} invalid={(error === "Completa los campos obligatorios antes de guardar." && !draft.name.trim()) || apiInvalidFields.includes(kind === "circuits" ? "description" : "name")} id="admin-name" label={kind === 'circuits' ? 'Descripción' : 'Nombre'} required><input id="admin-name" className="form-input" required value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} /></FormField>
          {(kind === 'responsibles' || kind === 'positions') && <FormField id="admin-department" label="Departamento" describedBy={error ? "catalog-form-error" : undefined} invalid={apiInvalidFields.includes("department_id") || (kind === 'positions' && Boolean(error) && !draft.departmentId)} required={kind === 'positions'}><SearchableSelect id="admin-department" label="Departamento" required={kind === 'positions'} value={draft.departmentId} onChange={(value) => setDraft({ ...draft, departmentId: value, positionId: '', capacity: '', capacityUnit: 'Mbps' })} options={departments.filter((item) => item.active || String(item.id) === draft.departmentId).map((item) => ({ value: String(item.id), label: item.name, disabled: !item.active }))} placeholder={kind === 'positions' ? 'Selecciona un departamento' : 'Sin asignar'} emptyMessage="No hay departamentos activos." noMatchMessage="Sin coincidencias." /></FormField>}
          {kind === 'responsibles' && <FormField id="admin-position" label="Puesto" describedBy={error ? "catalog-form-error" : undefined} invalid={apiInvalidFields.includes("position_id")}><SearchableSelect id="admin-position" label="Puesto" value={draft.positionId} disabled={!draft.departmentId} onChange={(value) => setDraft({ ...draft, positionId: value })} options={positions.filter((item) => String(item.department_id) === draft.departmentId && (item.active || String(item.id) === draft.positionId)).map((item) => ({ value: String(item.id), label: item.name, disabled: !item.active }))} placeholder="Sin asignar" emptyMessage="No hay puestos activos en este departamento." noMatchMessage="Sin coincidencias." /></FormField>}
          {kind === 'responsibles' && <label className="flex items-center gap-2"><input type="checkbox" checked={draft.operationalSelectable} onChange={e => setDraft({ ...draft, operationalSelectable: e.target.checked })} />Seleccionable en operaciones</label>}
          {kind === 'responsibles' && draft.id !== null && (() => { const item = items.find((row) => row.id === draft.id); return item && 'attention_level' in item && item.attention_level ? <p className="text-xs text-muted sm:col-span-2">Dato anterior conservado (solo lectura): {String(item.attention_level)}</p> : null })()}
          {(kind === 'positions' || kind === 'escalation-reasons' || kind === 'deactivation-reasons' || kind === 'providers' || kind === 'change-types' || kind === 'change-completion-types') && <FormField id="admin-detail" label="Descripción (opcional)"><input id="admin-detail" className="form-input" maxLength={10000} value={draft.detail} onChange={(event) => setDraft({ ...draft, detail: event.target.value })} /></FormField>}
          {kind === 'positions' && (() => {
            const availablePositions = (positions.length > 0 ? positions : (items as Position[])).filter(p => p.id !== draft.id)
            return (
              <div className="sm:col-span-2 mt-2 pt-4 border-t border-slate-700/60 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                    <ArrowUpRight size={16} className="text-sky-400" />
                    Escala a
                  </h3>
                  <span className="text-xs text-slate-400">Configuración opcional de recomendaciones</span>
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-medium text-slate-300">Puestos destino</label>
                  <div className="grid gap-2 sm:grid-cols-2 max-h-48 overflow-y-auto p-3 rounded-xl bg-slate-900/60 border border-slate-700/60">
                    {availablePositions.map(pos => {
                      const isSelected = draft.escalationDestinations.some(d => d.target_position_id === pos.id)
                      const isInactive = !pos.active
                      const disabled = isInactive && !isSelected
                      return (
                        <label
                          key={pos.id}
                          className={`flex items-center gap-2 text-xs p-2 rounded-lg cursor-pointer transition-colors ${
                            isSelected ? 'bg-sky-500/15 border border-sky-500/30 text-white' : 'hover:bg-slate-800/60 text-slate-300'
                          } ${disabled ? 'opacity-40 cursor-not-allowed' : ''}`}
                        >
                          <input
                            type="checkbox"
                            disabled={disabled}
                            checked={isSelected}
                            onChange={e => {
                              if (e.target.checked) {
                                setDraft({
                                  ...draft,
                                  escalationDestinations: [
                                    ...draft.escalationDestinations,
                                    { target_position_id: pos.id, time_minutes: '' }
                                  ]
                                })
                              } else {
                                setDraft({
                                  ...draft,
                                  escalationDestinations: draft.escalationDestinations.filter(d => d.target_position_id !== pos.id)
                                })
                              }
                            }}
                            className="rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/20"
                          />
                          <span className="truncate">{pos.name}</span>
                          {isInactive && (
                            <span className="text-[10px] text-amber-400/80 font-mono">(Inactivo)</span>
                          )}
                        </label>
                      )
                    })}
                    {availablePositions.length === 0 && (
                      <p className="text-xs text-slate-500 col-span-2 py-2 text-center">No hay otros puestos disponibles.</p>
                    )}
                  </div>
                </div>

                {draft.escalationDestinations.length > 0 && (
                  <div className="space-y-3 pt-2">
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-slate-300">Modalidad de tiempo</label>
                      <div className="flex gap-4">
                        <label className="flex items-center gap-2 text-xs text-slate-200 cursor-pointer">
                          <input
                            type="radio"
                            name="escalation-mode"
                            value="GENERAL"
                            checked={draft.escalationMode === 'GENERAL'}
                            onChange={() => setDraft({ ...draft, escalationMode: 'GENERAL' })}
                            className="text-sky-500 bg-slate-800 border-slate-600 focus:ring-sky-500/20"
                          />
                          Tiempo general (predeterminado)
                        </label>
                        <label className="flex items-center gap-2 text-xs text-slate-200 cursor-pointer">
                          <input
                            type="radio"
                            name="escalation-mode"
                            value="INDIVIDUAL"
                            checked={draft.escalationMode === 'INDIVIDUAL'}
                            onChange={() => setDraft({ ...draft, escalationMode: 'INDIVIDUAL' })}
                            className="text-sky-500 bg-slate-800 border-slate-600 focus:ring-sky-500/20"
                          />
                          Tiempo individual por destino
                        </label>
                      </div>
                    </div>

                    {draft.escalationMode === 'GENERAL' ? (
                      <FormField
                        id="admin-general-escalation-time"
                        label="Tiempo general de escalamiento (minutos)"
                        required
                        describedBy={error ? "catalog-form-error" : undefined}
                      >
                        <input
                          id="admin-general-escalation-time"
                          type="number"
                          min="1"
                          step="1"
                          className="form-input font-mono max-w-xs"
                          placeholder="Ej. 30"
                          value={draft.generalEscalationTime}
                          onChange={e => setDraft({ ...draft, generalEscalationTime: e.target.value })}
                        />
                      </FormField>
                    ) : (
                      <div className="space-y-2">
                        <label className="text-xs font-medium text-slate-300">Umbral por destino (minutos)</label>
                        <div className="grid gap-2 sm:grid-cols-2">
                          {draft.escalationDestinations.map(dest => {
                            const targetPos = availablePositions.find(p => p.id === dest.target_position_id)
                            return (
                              <div
                                key={dest.target_position_id}
                                className="flex items-center gap-3 p-2 rounded-xl bg-slate-900/60 border border-slate-700/60"
                              >
                                <span className="text-xs font-medium text-slate-200 flex-1 truncate">
                                  {targetPos?.name ?? `Puesto #${dest.target_position_id}`}
                                </span>
                                <input
                                  type="number"
                                  min="1"
                                  step="1"
                                  required
                                  placeholder="Minutos"
                                  value={dest.time_minutes}
                                  onChange={e => {
                                    const val = e.target.value
                                    setDraft({
                                      ...draft,
                                      escalationDestinations: draft.escalationDestinations.map(d =>
                                        d.target_position_id === dest.target_position_id ? { ...d, time_minutes: val } : d
                                      )
                                    })
                                  }}
                                  className="form-input font-mono text-xs w-24 py-1 px-2"
                                />
                                <span className="text-xs text-slate-400 font-mono">min</span>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    )}

                    <div className="p-3 rounded-xl bg-sky-500/5 border border-sky-500/20 text-xs">
                      <span className="font-semibold text-sky-400 block mb-1">Resumen de escalamiento:</span>
                      <p className="text-slate-300">
                        {draft.escalationMode === 'GENERAL' ? (
                          <>
                            Escala simultáneamente a {draft.escalationDestinations.length} destino(s) tras{' '}
                            <strong className="text-white font-mono">{draft.generalEscalationTime ? `${draft.generalEscalationTime} min` : '—'}</strong>:{' '}
                            {draft.escalationDestinations
                              .map(d => availablePositions.find(p => p.id === d.target_position_id)?.name ?? `#${d.target_position_id}`)
                              .join(', ')}.
                          </>
                        ) : (
                          <>
                            Escala individualmente a:{' '}
                            {draft.escalationDestinations
                              .map(d => {
                                const posName = availablePositions.find(p => p.id === d.target_position_id)?.name ?? `#${d.target_position_id}`
                                return `${posName} (${d.time_minutes ? `${d.time_minutes} min` : 'sin tiempo'})`
                              })
                              .join(', ')}.
                          </>
                        )}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )
          })()}
          {kind === 'circuits' && <FormField id="admin-sector" label="Sector" required describedBy={error ? "catalog-form-error" : undefined} invalid={Boolean(error && !draft.sectorId) || apiInvalidFields.includes("sector_id")}><select disabled={draft.id!==null&&!access.can("tickets.edit")} id="admin-sector" className="form-input" required value={draft.sectorId} onChange={event => setDraft({ ...draft, sectorId: event.target.value })}><option value="">Selecciona un sector</option>{sectors.filter(item => item.active || String(item.id) === draft.sectorId).map(item => <option key={item.id} value={item.id} disabled={!item.active}>{item.name}</option>)}</select></FormField>}
          {kind === 'circuits' && <FormField id="admin-service-type" label="Tipo de servicio" describedBy={error ? "catalog-form-error" : undefined} invalid={apiInvalidFields.includes("service_type_id")}><SearchableSelect id="admin-service-type" label="Tipo de servicio" value={draft.serviceTypeId} onChange={(value) => setDraft({ ...draft, serviceTypeId: value })} options={serviceTypes.filter((item) => item.active || String(item.id) === draft.serviceTypeId).map((item) => ({ value: String(item.id), label: item.name, disabled: !item.active }))} placeholder="Sin asignar" emptyMessage="No hay tipos de servicio activos." noMatchMessage="Sin coincidencias." /></FormField>}
          {kind === 'circuits' && <FormField id="admin-cpe-management-ip" label="IP de gestión CPE" describedBy={error ? "catalog-form-error" : undefined} invalid={apiInvalidFields.includes('cpe_management_ip')}><input id="admin-cpe-management-ip" className="form-input" type="text" placeholder="192.0.2.10" value={draft.cpeManagementIp} onChange={event => setDraft({ ...draft, cpeManagementIp: event.target.value })} /></FormField>}
          {kind === 'circuits' && <FormField id="admin-cpe-model" label="Modelo de CPE actual" describedBy={error ? "catalog-form-error" : undefined} invalid={apiInvalidFields.includes("cpe_model_id")}><SearchableSelect id="admin-cpe-model" label="Modelo de CPE actual" value={draft.cpeModelId} onChange={(value) => setDraft({ ...draft, cpeModelId: value })} options={cpeModels.filter((item) => item.active || String(item.id) === draft.cpeModelId).map((item) => ({ value: String(item.id), label: item.name, disabled: !item.active }))} placeholder="Sin asignar" emptyMessage="No hay modelos de CPE activos." noMatchMessage="Sin coincidencias." /></FormField>}
          {kind === 'circuits' && <div className="sm:col-span-2"><CapacityFields id="admin-initial-capacity" label="Capacidad inicial (opcional)" value={draft.capacity} unit={draft.capacityUnit} onChange={(capacity, capacityUnit) => setDraft({ ...draft, capacity, capacityUnit })} /></div>}
          {kind === 'change-completion-types' && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.appliesEfficiency} onChange={e=>setDraft({...draft,appliesEfficiency:e.target.checked})}/>Aplica para eficiencia</label>}
          <div className="flex items-center gap-2 self-end pb-3"><input aria-describedby={error ? "catalog-form-error" : undefined} aria-invalid={apiInvalidFields.includes("active") || undefined} id="admin-active" disabled={kind==='circuits'&&draft.id!==null&&!access.can(draft.active?"lifecycle.deactivate":"lifecycle.reactivate") || kind === 'responsibles' && draft.id !== null && items.some(p => p.id === draft.id && 'can_change_active' in p && p.can_change_active === false)} type="checkbox" checked={draft.active} onChange={(e) => setDraft({ ...draft, active: e.target.checked })} /><label htmlFor="admin-active" className="text-sm font-medium text-slate-200">Activo</label></div>
        </fieldset>
        <p className="mt-3 text-xs text-slate-400 font-mono">Desactivar conserva el registro y sus referencias históricas.</p>
        <div className="mt-4 flex justify-end gap-3">
          <button type="button" className="button-secondary rounded-full shadow-xs" disabled={busy || distributionOpen} onClick={() => { if (circuitEditor) circuitEditor.onCancel(); else { setDraft(null); setError(null); setApiInvalidFields([]) } }}>Cancelar</button>
          <button type="submit" className={`button-primary ${kind === 'customers' || kind === 'circuits' ? 'button-primary--blue' : 'button-primary--slate'} rounded-full shadow-sm`} disabled={busy || distributionOpen || Boolean(circuitEditor && (loading || loadError))}>{busy ? (draft.id === null ? 'Creando...' : 'Guardando...') : 'Guardar'}</button>
        </div>
      </form>
    )}
    {!circuitEditor && <>
    {kind === 'circuits' && (() => {
      // Cada chip quita solo su condición.
      const chips: FilterChipItem[] = [
        ...(params.get('search') ? [{ label: 'Búsqueda', value: params.get('search')!, onRemove: () => change({ search: '' }) }] : []),
        ...(params.get('customer_id') ? [{ label: 'Cliente', value: customerLabel(Number(params.get('customer_id'))), onRemove: () => change({ customer_id: '' }) }] : []),
        ...(params.get('sector_id') ? [{ label: 'Sector', value: sectors.find((item) => String(item.id) === params.get('sector_id'))?.name ?? `#${params.get('sector_id')}`, onRemove: () => change({ sector_id: '' }) }] : []),
        ...(params.get('node_id') ? [{ label: 'Nodo', value: nodes.find((item) => String(item.id) === params.get('node_id'))?.name ?? `#${params.get('node_id')}`, onRemove: () => change({ node_id: '' }) }] : []),
        ...(params.get('active') ? [{ label: 'Estado', value: params.get('active') === 'true' ? 'Activos' : params.get('active') === 'false' ? 'Inactivos' : params.get('active')!, onRemove: () => change({ active: '' }) }] : []),
      ]
      return (
        <FilterBar
          label="Filtros de circuitos"
          theme="blue"
          chips={chips}
          onClear={clear}
          search={<FormField id="circuit-search" label="Buscar circuitos"><input id="circuit-search" className="form-input" type="search" placeholder="Código o descripción..." value={search} onChange={(event) => setSearch(event.target.value)} /></FormField>}
          quick={<>
            <div className="filter-bar-quick"><FormField id="circuit-customer-filter" label="Filtrar por cliente"><SearchableSelect id="circuit-customer-filter" label="Cliente" value={params.get('customer_id') ?? ''} options={customers.map((item) => ({ value: String(item.id), label: `${item.customer_code} — ${item.name}` }))} onChange={(value) => change({ customer_id: value })} disabled={loading && !customers.length} placeholder="Todos los clientes" emptyMessage="No hay clientes." noMatchMessage="No se encontraron clientes." /></FormField></div>
            <div className="filter-bar-quick"><FormField id="circuit-sector-filter" label="Filtrar por sector"><SearchableSelect id="circuit-sector-filter" label="Sector" value={params.get('sector_id') ?? ''} options={sectors.map((item) => ({ value: String(item.id), label: item.name }))} onChange={(value) => change({ sector_id: value })} placeholder="Todos los sectores" emptyMessage="No hay sectores." noMatchMessage="No se encontraron sectores." /></FormField></div>
            <div className="filter-bar-quick"><FormField id="circuit-node-filter" label="Filtrar por nodo"><SearchableSelect id="circuit-node-filter" label="Nodo" value={params.get('node_id') ?? ''} options={nodes.map((item) => ({ value: String(item.id), label: item.name }))} onChange={(value) => change({ node_id: value })} placeholder="Todos los nodos" emptyMessage="No hay nodos." noMatchMessage="No se encontraron nodos." /></FormField></div>
          </>}
          primary={<FilterSegment label="Estado de circuitos" options={[['', 'Todos'], ['true', 'Activos'], ['false', 'Inactivos']]} value={params.get('active') ?? ''} onChange={(value) => change({ active: value })} />}
        />
      )
    })()}
    {kind === 'customers' && (
      <FilterBar
        label="Filtros de clientes"
        theme="blue"
        chips={search.trim() ? [{ label: 'Búsqueda', value: search.trim(), onRemove: () => setSearch('') }] : []}
        onClear={() => setSearch('')}
        search={<FormField id="admin-search" label="Buscar clientes"><input id="admin-search" type="search" placeholder="Buscar por código o nombre..." className="form-input" value={search} onChange={(e) => setSearch(e.target.value)} /></FormField>}
      />
    )}
    {kind === 'responsibles' && (
      <FilterBar
        label="Filtros de responsables"
        theme="slate"
        chips={search.trim() ? [{ label: 'Búsqueda', value: search.trim(), onRemove: () => setSearch('') }] : []}
        onClear={() => setSearch('')}
        search={<FormField id="admin-search" label="Buscar responsables"><input id="admin-search" type="search" placeholder="Buscar por nombre..." className="form-input" value={search} onChange={(e) => setSearch(e.target.value)} /></FormField>}
      />
    )}
    {(kind === 'nodes' || kind === 'positions') && (
      <FilterBar
        label={`Filtros de ${info.empty}`}
        theme="slate"
        chips={[
          ...(departmentFilter && kind === 'positions' ? [{ label: 'Departamento', value: departments.find(d => String(d.id) === departmentFilter)?.name ?? `#${departmentFilter}`, onRemove: () => setDepartmentFilter('') }] : []),
          ...(search.trim() ? [{ label: 'Búsqueda', value: search.trim(), onRemove: () => setSearch('') }] : []),
        ]}
        onClear={() => { setSearch(''); if (kind === 'positions') setDepartmentFilter('') }}
        search={<FormField id="admin-search" label={`Buscar ${info.empty}`}><input id="admin-search" type="search" className="form-input" placeholder="Buscar por nombre..." value={search} onChange={(e) => setSearch(e.target.value)} /></FormField>}
        quick={kind === 'positions' && (
          <div className="filter-bar-quick">
            <FormField id="position-department-filter" label="Filtrar por departamento">
              <SearchableSelect id="position-department-filter" label="Filtrar por departamento" value={departmentFilter} onChange={setDepartmentFilter} options={departments.map((item) => ({ value: String(item.id), label: item.name }))} placeholder="Todos los departamentos" emptyMessage="No hay departamentos." noMatchMessage="Sin coincidencias." />
            </FormField>
          </div>
        )}
      />
    )}
    {loading || loadError || !ordered.length ? <RequestState loading={loading} loadingText={`Cargando ${info.empty}...`} error={loadError ? `Error al cargar ${info.empty}: ${loadError}` : null} errorTitle="" onRetry={() => setRetry(retry + 1)} empty={!ordered.length} emptyTitle={items.length || (kind === 'circuits' && circuitFilterKeys.some((key) => params.has(key))) ? 'No hay coincidencias con la búsqueda.' : `No hay ${info.empty} registrados.`} emptyDescription="" compact={!refreshedModule && loading} /> : <div className={`panel table-surface overflow-x-auto rounded-2xl bg-[#0b1426] border ${kind === 'customers' || kind === 'circuits' ? 'border-sky-500/20' : 'table-surface--slate'} shadow-xl`}><table className="operation-table min-w-[650px]"><caption className="table-title">{info.title}</caption>
      <thead><tr>{[...(kind === 'customers' || kind === 'circuits' ? ['Código'] : []), ...(kind === 'circuits' ? ['Cliente', 'Nodo', 'Sector'] : []), kind === 'circuits' ? 'Descripción' : 'Nombre', ...(kind === 'change-types' ? ['Descripción'] : kind === 'change-completion-types' ? ['Descripción', 'Aplica para eficiencia'] : []), ...(kind === 'positions' || kind === 'responsibles' ? ['Departamento'] : []), ...(kind === 'positions' ? ['Escala a'] : []), ...(kind === 'responsibles' ? ['Puesto', 'Seleccionable en operaciones', ...(manageAccess ? ['Acceso a Ticketyn'] : [])] : []), 'Estado', 'Fecha de creación', 'Acciones'].map((label) => <th key={label} scope="col">{label}</th>)}</tr></thead>
      <tbody>{ordered.map((item) => <tr key={item.id}>
        {(kind === 'customers' || kind === 'circuits') && <th scope="row" className="record-code">{kind === 'circuits' ? <Link to={`/circuits/${item.id}`} className="font-mono font-bold text-sky-400 hover:text-sky-300 hover:underline tracking-wide">{code(item)}</Link> : <span className="font-mono font-bold text-sky-400 tracking-wide">{code(item)}</span>}</th>}
        {kind === 'circuits' && 'customer_id' in item && <td className="text-slate-300">{customerLabel(item.customer_id)}</td>}
        {kind === 'circuits' && 'circuit_code' in item && <td className="text-slate-400 font-mono text-xs">{item.node?.name ?? 'Sin asignar'}</td>}
        {kind === 'circuits' && 'circuit_code' in item && <td className="text-slate-400 font-mono text-xs">{item.sector?.name ?? 'Sin asignar'}</td>}
        <td className={kind === 'customers' || kind === 'circuits' ? 'font-semibold text-white' : undefined}>{name(item)}</td>{kind === 'change-types' && <td>{'description' in item ? String(item.description ?? '—') : '—'}</td>}{kind === 'change-completion-types' && <><td>{'description' in item ? String(item.description ?? '—') : '—'}</td><td>{'applies_efficiency' in item && item.applies_efficiency ? 'Sí' : 'No'}</td></>}{(kind === 'positions' || kind === 'responsibles') && <td>{'department' in item && item.department ? (item.department as NamedCatalog).name : 'Sin asignar'}</td>}{kind === 'positions' && <td className="text-xs text-slate-300">{(() => { const pos = item as Position; if (!pos.destinations || pos.destinations.length === 0) return <span className="text-slate-500 italic">Sin destinos</span>; if (pos.escalation_mode === 'GENERAL') return <span>{pos.destinations.map(d => d.target_position_name).join(', ')} <span className="text-sky-400 font-mono">({pos.general_escalation_time_minutes ?? '—'}m)</span></span>; return <span className="space-x-1">{pos.destinations.map(d => <span key={d.target_position_id} className="inline-block whitespace-nowrap">{d.target_position_name} <span className="text-sky-400 font-mono">({d.time_minutes ?? '—'}m)</span></span>)}</span> })()}</td>}{kind === 'responsibles' && <td>{'position' in item && item.position ? (item.position as NamedCatalog).name : 'Sin asignar'}</td>}{kind === 'responsibles' && <td>{'operational_selectable' in item && item.operational_selectable === false ? 'No' : 'Sí'}</td>}{manageAccess && <td>{(() => { const row = accessRows.find(p => p.id === item.id); return row ? <>{row.username ?? 'Sin acceso configurado'}<span className="block text-xs text-muted">{row.effective_access ? 'Habilitado' : row.access_granted && !row.active ? 'Bloqueado por inactividad' : 'Deshabilitado'}{row.role_name ? ` · ${row.role_name}` : ''}</span></> : 'Administración de acceso restringida' })()}</td>}<td><span className={`status-badge ${item.active ? 'status-active' : 'status-neutral'}`}>{item.active ? 'Activo' : 'Inactivo'}</span></td>
        <td className="whitespace-nowrap text-xs tabular-nums text-slate-400 font-mono"><time dateTime={item.created_at} title={formatDate(item.created_at)}>{formatTableDate(item.created_at)}</time></td><td><div className="table-actions">
          {manageAccess && accessRows.some(p => p.id === item.id) && <button type="button" className="button-secondary table-action rounded-full" disabled={busy || Boolean(draft)} onClick={() => setAccessId(item.id)} aria-label={`Administrar acceso de ${name(item)}`}>{accessRows.find(p => p.id === item.id)?.account_exists ? 'Administrar acceso' : 'Configurar acceso'}</button>}
          {kind === 'customers' && <><Can permission="circuits.view"><Link className="button-ghost table-action rounded-full text-sky-400 hover:text-sky-300 font-mono text-xs" to={`/circuits?customer_id=${item.id}`} aria-label={`Ver circuitos de ${code(item)}`}><Network size={13} aria-hidden="true" />Circuitos</Link></Can><Can permission="tickets.view"><Link className="button-ghost table-action rounded-full text-sky-400 hover:text-sky-300 font-mono text-xs" to={`/tickets?customer_id=${item.id}`} aria-label={`Ver tickets de ${code(item)}`}><Ticket size={13} aria-hidden="true" />Tickets</Link></Can></>}
          {kind === 'circuits' && 'circuit_code' in item ? <CircuitActions circuit={item} disabled={busy || Boolean(draft)} onEdit={() => edit(item)} onToggle={() => toggle(item)} onDelete={() => { setError(null); setNotice(null); setDeleting(item) }} /> : <>
          <Can permission={permissionModule+".edit"}><button type="button" className="button-secondary table-action rounded-full" disabled={busy || Boolean(draft)} onClick={() => edit(item)} aria-label={`Editar ${code(item) || name(item)}`}><Pencil size={13} aria-hidden="true" />Editar</button></Can><Can permission={permissionModule+".edit"}><button type="button" className={`${item.active ? 'button-danger' : 'button-secondary'} table-action rounded-full`} disabled={busy || Boolean(draft) || kind === 'responsibles' && 'can_change_active' in item && item.can_change_active === false} onClick={() => toggle(item)} aria-label={`${item.active ? 'Desactivar' : 'Activar'} ${code(item) || name(item)}`}><Power size={13} aria-hidden="true" />{item.active ? 'Desactivar' : 'Activar'}</button></Can>
          {('customer_code' in item) && <Can permission={permissionModule+".delete"}><button type="button" className="button-danger table-action rounded-full" disabled={busy || Boolean(draft)} aria-label={`Eliminar ${code(item)}`} onClick={() => { setError(null); setNotice(null); setDeleting(item) }}><Trash2 size={13} aria-hidden="true" />Eliminar</button></Can>}</>}</div></td>
      </tr>)}</tbody></table></div>}
    {deleting && access.can(permissionModule+".delete") && <CatalogDeleteConfirmation item={deleting} fallbackFocus={newRecordButton} onCancel={() => setDeleting(null)} onBusyChange={setBusy} onDeleted={() => {
      setItems((current) => current.filter((row) => row.id !== deleting.id))
      setBusy(false)
      setNotice('Registro eliminado correctamente.')
      setDeleting(null)
    }} />}
    </>}
    {quickNode && draft && <QuickCatalogCreate kind="node" onCancel={() => setQuickNode(false)} onCreated={(node) => { setNodes((current) => [...current, node]); setDraft(current => current ? { ...current, nodeId: String(node.id), distributionDeviceId: '', distributionPortId: '' } : current); setQuickNode(false) }} />}
  </>
}
