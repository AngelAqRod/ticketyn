import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRightLeft,
  CheckCircle2,
  Filter,
  Layers3,
  Network,
  Pencil,
  Plus,
  Power,
  RotateCcw,
  Server,
  Trash2,
  XCircle,
} from 'lucide-react'
import {
  deleteDistributionDevice,
  deleteDistributionPort,
  getDistributionDevice,
  getDistributionDeviceCircuits,
  getDistributionDevices,
  getDistributionPorts,
  setDistributionDeviceStatus,
  setDistributionPortStatus,
} from '../api/distribution'
import { listNodes, listDistributionPorts } from '../api'
import { Can, usePermissions } from '../auth/permissions'
import {
  DeleteConfirmationModal,
  DeviceFormModal,
  DeviceMoveModal,
  PortFormModal,
  PortMoveModal,
  StatusConfirmationModal,
} from '../components/DistributionModals'
import { PortCreateDialog } from '../components/PortCreateDialog'
import { FeedbackMessage } from '../components/FeedbackMessage'
import { PageHeading } from '../components/PageHeading'
import { PaginationBar } from '../components/PaginationBar'
import { RequestState } from '../components/RequestState'
import type { Node } from '../types/catalog'
import type {
  DistributionCircuit,
  DistributionDevice,
  DistributionPort,
} from '../types/distribution'

const CIRCUITS_PAGE_SIZE = 50

export function DistributionDeviceDetail() {
  const { id } = useParams()
  const deviceId = Number(id)
  const access = usePermissions()
  const navigate = useNavigate()

  // Main state
  const [device, setDevice] = useState<DistributionDevice | null>(null)
  const [nodes, setNodes] = useState<Node[]>([])
  const [allDevices, setAllDevices] = useState<DistributionDevice[]>([])
  const [ports, setPorts] = useState<DistributionPort[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [notice, setNotice] = useState<string | null>(null)

  // Circuits state
  const [circuits, setCircuits] = useState<DistributionCircuit[]>([])
  const [circuitsLoading, setCircuitsLoading] = useState(false)
  const [circuitsError, setCircuitsError] = useState<string | null>(null)
  const [circuitFilterPortId, setCircuitFilterPortId] = useState<number | null>(null)
  const [circuitFilterWithoutPort, setCircuitFilterWithoutPort] = useState(false)
  const [circuitsOffset, setCircuitsOffset] = useState(0)

  // Modals state
  const [editDeviceOpen, setEditDeviceOpen] = useState(false)
  const [moveDeviceOpen, setMoveDeviceOpen] = useState(false)
  const [statusDeviceOpen, setStatusDeviceOpen] = useState(false)
  const [deleteDeviceOpen, setDeleteDeviceOpen] = useState(false)

  const [createPortOpen, setCreatePortOpen] = useState(false)
  const [bulkPortOpen, setBulkPortOpen] = useState(false)
  const [editPort, setEditPort] = useState<DistributionPort | null>(null)
  const [movePort, setMovePort] = useState<DistributionPort | null>(null)
  const [statusPort, setStatusPort] = useState<DistributionPort | null>(null)
  const [deletePort, setDeletePort] = useState<DistributionPort | null>(null)

  // References for smooth scrolling
  const circuitsSectionRef = useRef<HTMLElement>(null)

  // Load device, nodes, and ports
  useEffect(() => {
    if (!deviceId || isNaN(deviceId)) {
      setError('Identificador de equipo inválido.')
      setLoading(false)
      return
    }

    const controller = new AbortController()
    setLoading(true)
    setError(null)

    Promise.all([
      getDistributionDevice(deviceId, controller.signal),
      listDistributionPorts(deviceId, controller.signal, true),
      listNodes(controller.signal, true),
      getDistributionDevices({ include_inactive: true, limit: 200 }, controller.signal),
    ])
      .then(([devData, portsData, nodesData, devicesData]) => {
        if (!controller.signal.aborted) {
          setDevice(devData)
          setPorts(portsData)
          setNodes(nodesData)
          setAllDevices(devicesData)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          setError(
            err instanceof Error
              ? err.message
              : 'No se pudo consultar el detalle del equipo de distribución.',
          )
          setLoading(false)
        }
      })

    return () => controller.abort()
  }, [deviceId, refreshKey])

  // Load circuits associated to the device
  const canViewCircuits = access.can('circuits.view')
  useEffect(() => {
    if (!deviceId || isNaN(deviceId) || !canViewCircuits) return

    const controller = new AbortController()
    setCircuitsLoading(true)
    setCircuitsError(null)

    getDistributionDeviceCircuits(
      deviceId,
      {
        port_id: circuitFilterPortId ?? undefined,
        without_port: circuitFilterWithoutPort,
        limit: CIRCUITS_PAGE_SIZE,
        offset: circuitsOffset,
      },
      controller.signal,
    )
      .then((rows) => {
        if (!controller.signal.aborted) {
          setCircuits(rows)
          setCircuitsLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          setCircuitsError(
            err instanceof Error ? err.message : 'No se pudo consultar los circuitos asociados.',
          )
          setCircuitsLoading(false)
        }
      })

    return () => controller.abort()
  }, [
    deviceId,
    circuitFilterPortId,
    circuitFilterWithoutPort,
    circuitsOffset,
    refreshKey,
    canViewCircuits,
  ])

  if (loading) {
    return <RequestState loading loadingText="Cargando ficha del equipo de distribución..." />
  }

  if (error || !device) {
    return (
      <RequestState
        error={error ?? 'Equipo no encontrado.'}
        onRetry={() => setRefreshKey((k) => k + 1)}
      />
    )
  }

  const nodeName = nodes.find((n) => n.id === device.node_id)?.name ?? `Nodo #${device.node_id}`

  // Operational metrics
  const totalPortsCount = device.port_count
  const portsWithoutCircuits = device.unassigned_port_count ?? ports.filter((p) => p.circuit_count === 0).length
  const portsWithCircuits = device.unassigned_port_count === undefined
    ? ports.filter((p) => p.circuit_count > 0).length
    : totalPortsCount - portsWithoutCircuits
  const totalCircuitsCount = device.circuit_count

  function selectPortFilter(portId: number) {
    setCircuitFilterWithoutPort(false)
    setCircuitFilterPortId(portId)
    setCircuitsOffset(0)
    circuitsSectionRef.current?.scrollIntoView?.({ behavior: 'smooth' })
  }

  function selectWithoutPortFilter() {
    setCircuitFilterPortId(null)
    setCircuitFilterWithoutPort(true)
    setCircuitsOffset(0)
    circuitsSectionRef.current?.scrollIntoView?.({ behavior: 'smooth' })
  }

  function clearCircuitFilters() {
    setCircuitFilterPortId(null)
    setCircuitFilterWithoutPort(false)
    setCircuitsOffset(0)
  }

  const circuitsPage = Math.floor(circuitsOffset / CIRCUITS_PAGE_SIZE) + 1

  return (
    <div className="distribution-theme space-y-6">
      {/* Back button */}
      <div>
        <Link
          to="/distribution-devices"
          className="button-ghost inline-flex items-center gap-1.5 text-xs text-purple-400 hover:text-purple-300 font-mono"
        >
          <ArrowLeft size={14} aria-hidden="true" />
          Volver a equipos de distribución
        </Link>
      </div>

      {notice && <FeedbackMessage variant="success">{notice}</FeedbackMessage>}

      {/* Header */}
      <PageHeading
        title={device.name}
        description={
          device.description
            ? `${device.description} (Nodo: ${nodeName})`
            : `Equipo de distribución en el nodo ${nodeName}`
        }
        theme="purple"
        badge={
          <span className={`status-badge ${device.active ? 'status-active' : 'status-neutral'}`}>
            {device.active ? 'Activo' : 'Inactivo'}
          </span>
        }
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Can permission="distribution_devices.edit">
              <button
                type="button"
                className="button-secondary rounded-full"
                onClick={() => setEditDeviceOpen(true)}
              >
                <Pencil size={14} aria-hidden="true" />
                Editar datos
              </button>
            </Can>

            <Can permission="distribution_devices.move">
              <button
                type="button"
                className="button-secondary rounded-full"
                onClick={() => setMoveDeviceOpen(true)}
              >
                <ArrowRightLeft size={14} aria-hidden="true" />
                Trasladar de nodo
              </button>
            </Can>

            <Can permission="distribution_devices.set_active">
              <button
                type="button"
                className={`button-secondary rounded-full ${
                  device.active ? 'hover:text-amber-400' : 'hover:text-emerald-400'
                }`}
                onClick={() => setStatusDeviceOpen(true)}
              >
                <Power size={14} aria-hidden="true" />
                {device.active ? 'Desactivar' : 'Activar'}
              </button>
            </Can>

            <Can permission="distribution_devices.delete">
              <button
                type="button"
                className="button-secondary text-red-400 hover:text-red-300 rounded-full"
                onClick={() => setDeleteDeviceOpen(true)}
              >
                <Trash2 size={14} aria-hidden="true" />
                Eliminar
              </button>
            </Can>
          </div>
        }
      />

      {/* Operational summary cards (Section 5) */}
      <section aria-label="Resumen operativo del equipo">
        <h2 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-400 mb-3">
          Resumen operativo del equipo
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="stat-card distribution-metric distribution-metric--blue p-4 rounded-2xl bg-[#0b1426] border shadow-lg">
            <span className="stat-card-label text-xs">Total de puertos</span>
            <div className="stat-card-value text-2xl font-mono font-bold mt-1">
              {totalPortsCount}
            </div>
            <span className="stat-card-caption text-[11px] text-slate-400 mt-1">
              Registrados en Ticketyn
            </span>
          </div>

          <div className="stat-card distribution-metric distribution-metric--cyan p-4 rounded-2xl bg-[#0b1426] border shadow-lg">
            <span className="stat-card-label text-xs">Con circuitos</span>
            <div className="stat-card-value text-2xl font-mono font-bold mt-1">
              {portsWithCircuits}
            </div>
            <span className="stat-card-caption text-[11px] text-slate-400 mt-1">
              Puertos con enlaces asociados
            </span>
          </div>

          <div className="stat-card distribution-metric distribution-metric--green p-4 rounded-2xl bg-[#0b1426] border shadow-lg">
            <span className="stat-card-label text-xs">Sin circuitos</span>
            <div className="stat-card-value text-2xl font-mono font-bold mt-1">
              {portsWithoutCircuits}
            </div>
            <span className="stat-card-caption text-[11px] text-slate-400 mt-1">
              Sin circuitos asociados
            </span>
          </div>

          <div className="stat-card distribution-metric p-4 rounded-2xl bg-[#0b1426] border shadow-lg">
            <span className="stat-card-label text-xs">Total de circuitos</span>
            <div className="stat-card-value text-2xl font-mono font-bold mt-1">
              {totalCircuitsCount}
            </div>
            <span className="stat-card-caption text-[11px] text-slate-400 mt-1">
              Enlaces asociados al equipo
            </span>
          </div>
        </div>
        <p className="mt-2 text-[11px] text-slate-400 italic">
          * Los conteos representan registros lógicos configurados en Ticketyn, no la disponibilidad
          o estado físico real de las interfaces de red.
        </p>
      </section>

      {/* Ports table (Section 5) */}
      <section
        aria-label="Puertos del equipo"
        className="panel p-5 rounded-2xl bg-[#0b1426] border border-purple-500/20 shadow-xl space-y-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-purple-500/15 pb-3">
          <div className="flex items-center gap-2">
            <Layers3 size={16} className="text-purple-400" aria-hidden="true" />
            <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
              Puertos del equipo ({ports.length})
            </h2>
          </div>

          <Can permission="distribution_ports.create">
            <div className="flex flex-wrap gap-2"><button type="button" className="button-secondary rounded-full text-xs" onClick={() => setBulkPortOpen(true)}>Crear puertos masivamente</button>
            <button
              type="button"
              className="button-primary button-primary--purple rounded-full text-xs shadow-sm"
              onClick={() => setCreatePortOpen(true)}
            >
              <Plus size={14} aria-hidden="true" />
              Nuevo puerto
            </button></div>
          </Can>
        </div>

        {ports.length === 0 ? (
          <div className="p-6 text-center text-slate-400 text-xs">
            <Layers3 size={24} className="mx-auto mb-2 text-slate-500" aria-hidden="true" />
            No hay puertos registrados para este equipo de distribución.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full text-left text-sm text-slate-200">
              <thead className="border-b border-slate-800 bg-[#070d1a] font-mono text-xs uppercase tracking-wider text-slate-400">
                <tr>
                  <th scope="col" className="px-4 py-2.5 font-semibold">
                    Nombre del puerto
                  </th>
                  <th scope="col" className="px-4 py-2.5 font-semibold">
                    Descripción
                  </th>
                  <th scope="col" className="px-4 py-2.5 text-center font-semibold">
                    Estado
                  </th>
                  <th scope="col" className="px-4 py-2.5 text-center font-semibold">
                    Circuitos asociados
                  </th>
                  <th scope="col" className="px-4 py-2.5 text-right font-semibold">
                    Acciones
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/80">
                {ports.map((port) => (
                  <tr key={port.id} className="hover:bg-purple-500/5 transition-colors">
                    <td className="px-4 py-3 font-mono font-bold text-white">
                      <span className="text-purple-300">{port.name}</span>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-400 max-w-xs truncate">
                      {port.description || '—'}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span
                        className={`status-badge ${
                          port.active ? 'status-active' : 'status-neutral'
                        }`}
                      >
                        {port.active ? 'Activo' : 'Inactivo'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center font-mono text-xs">
                      {port.circuit_count > 0 ? (
                        <button
                          type="button"
                          onClick={() => selectPortFilter(port.id)}
                          className="button-ghost chip-cyan font-bold hover:underline px-2 py-0.5 rounded"
                          title="Filtrar circuitos de este puerto"
                        >
                          {port.circuit_count}{' '}
                          {port.circuit_count === 1 ? 'circuito' : 'circuitos'}
                        </button>
                      ) : (
                        <span className="text-slate-400 italic">Sin circuitos asociados</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {port.circuit_count > 0 && (
                          <button
                            type="button"
                            className="button-ghost p-1 text-xs text-purple-400 hover:text-purple-300 rounded"
                            title="Consultar circuitos de este puerto"
                            aria-label={`Ver circuitos del puerto ${port.name}`}
                            onClick={() => selectPortFilter(port.id)}
                          >
                            Ver circuitos
                          </button>
                        )}

                        <Can permission="distribution_ports.edit">
                          <button
                            type="button"
                            className="button-ghost p-1.5 text-slate-300 hover:text-white rounded-lg hover:bg-slate-800"
                            title="Editar nombre y descripción"
                            aria-label={`Editar puerto ${port.name}`}
                            onClick={() => setEditPort(port)}
                          >
                            <Pencil size={14} aria-hidden="true" />
                          </button>
                        </Can>

                        <Can permission="distribution_ports.move">
                          <button
                            type="button"
                            className="button-ghost p-1.5 text-slate-300 hover:text-purple-400 rounded-lg hover:bg-slate-800"
                            title="Trasladar a otro equipo"
                            aria-label={`Trasladar puerto ${port.name}`}
                            onClick={() => setMovePort(port)}
                          >
                            <ArrowRightLeft size={14} aria-hidden="true" />
                          </button>
                        </Can>

                        <Can permission="distribution_ports.set_active">
                          <button
                            type="button"
                            className={`button-ghost p-1.5 rounded-lg hover:bg-slate-800 ${
                              port.active
                                ? 'text-amber-400 hover:text-amber-300'
                                : 'text-emerald-400 hover:text-emerald-300'
                            }`}
                            title={port.active ? 'Desactivar puerto' : 'Activar puerto'}
                            aria-label={`${port.active ? 'Desactivar' : 'Activar'} puerto ${port.name}`}
                            onClick={() => setStatusPort(port)}
                          >
                            <Power size={14} aria-hidden="true" />
                          </button>
                        </Can>

                        <Can permission="distribution_ports.delete">
                          <button
                            type="button"
                            className="button-ghost p-1.5 text-red-400 hover:text-red-300 rounded-lg hover:bg-red-500/10"
                            title="Eliminar puerto"
                            aria-label={`Eliminar puerto ${port.name}`}
                            onClick={() => setDeletePort(port)}
                          >
                            <Trash2 size={14} aria-hidden="true" />
                          </button>
                        </Can>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Associated Circuits / Services Section (Section 6) */}
      <section
        ref={circuitsSectionRef}
        aria-label="Servicios y circuitos asociados"
        className="panel p-5 rounded-2xl bg-[#0b1426] border border-purple-500/20 shadow-xl space-y-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-purple-500/15 pb-3">
          <div className="flex items-center gap-2">
            <Network size={16} className="text-purple-400" aria-hidden="true" />
            <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
              Servicios asociados al equipo ({device.circuit_count})
            </h2>
          </div>

          {/* Sub-filters for circuits */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className={`segment-button text-xs rounded-full px-3 py-1 font-mono ${
                circuitFilterPortId === null && !circuitFilterWithoutPort
                  ? 'distribution-selected text-white font-bold'
                  : 'text-slate-400 hover:text-white'
              }`}
              onClick={clearCircuitFilters}
            >
              Todos ({device.circuit_count})
            </button>

            <button
              type="button"
              className={`segment-button text-xs rounded-full px-3 py-1 font-mono ${
                circuitFilterWithoutPort
                  ? 'distribution-selected text-white font-bold'
                  : 'text-slate-400 hover:text-purple-300'
              }`}
              onClick={selectWithoutPortFilter}
            >
              Circuitos sin puerto asignado
            </button>

            {circuitFilterPortId !== null && (
              <span className="inline-flex items-center gap-1 rounded-full bg-purple-950/80 border border-purple-600 px-3 py-1 text-xs font-mono text-purple-300">
                Filtrando por puerto:{' '}
                <strong>
                  {ports.find((p) => p.id === circuitFilterPortId)?.name ?? `#${circuitFilterPortId}`}
                </strong>
                <button
                  type="button"
                  onClick={clearCircuitFilters}
                  className="ml-1 text-slate-400 hover:text-white"
                  title="Quitar filtro de puerto"
                  aria-label="Quitar filtro de puerto"
                >
                  ×
                </button>
              </span>
            )}
          </div>
        </div>

        {!canViewCircuits ? (
          <p className="p-4 text-xs font-mono text-slate-400">
            Sin permiso para consultar circuitos asociados.
          </p>
        ) : (
          <>
            <RequestState
              loading={circuitsLoading}
              loadingText="Cargando circuitos asociados..."
              error={circuitsError}
              onRetry={() => setRefreshKey((k) => k + 1)}
            />

            {!circuitsLoading && !circuitsError && circuits.length === 0 && (
              <div className="p-6 text-center text-slate-400 text-xs">
                {circuitFilterWithoutPort
                  ? 'No hay circuitos sin puerto asignado en este equipo.'
                  : circuitFilterPortId !== null
                  ? 'No hay circuitos asignados a este puerto.'
                  : 'No hay circuitos asociados a este equipo de distribución.'}
              </div>
            )}

            {!circuitsLoading && !circuitsError && circuits.length > 0 && (
              <div className="overflow-x-auto rounded-xl border border-slate-800">
                <table className="w-full text-left text-sm text-slate-200">
                  <thead className="border-b border-slate-800 bg-[#070d1a] font-mono text-xs uppercase tracking-wider text-slate-400">
                    <tr>
                      <th scope="col" className="px-4 py-2.5 font-semibold">
                        Código de circuito
                      </th>
                      <th scope="col" className="px-4 py-2.5 font-semibold">
                        Descripción
                      </th>
                      <th scope="col" className="px-4 py-2.5 font-semibold">
                        Cliente
                      </th>
                      <th scope="col" className="px-4 py-2.5 font-semibold">
                        Tipo de servicio
                      </th>
                      <th scope="col" className="px-4 py-2.5 font-semibold">
                        Puerto asignado
                      </th>
                      <th scope="col" className="px-4 py-2.5 text-center font-semibold">
                        Estado
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/80">
                    {circuits.map((c) => (
                      <tr key={c.id} className="hover:bg-purple-500/5 transition-colors">
                        <td className="px-4 py-3 font-mono font-bold text-white">
                          <Link
                            to={`/circuits/${c.id}`}
                            className="text-purple-400 hover:text-purple-300 hover:underline"
                          >
                            {c.circuit_code}
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-300 max-w-xs truncate">
                          {c.description || '—'}
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-300">
                          <span className="font-mono text-slate-400">{c.customer_code}</span> —{' '}
                          {c.customer_name}
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-400">
                          {c.service_type_name || 'Sin asignar'}
                        </td>
                        <td className="px-4 py-3 text-xs font-mono">
                          {c.distribution_port_name ? (
                            <span className="text-purple-300 font-semibold">
                              {c.distribution_port_name}
                            </span>
                          ) : (
                            <span className="text-amber-400 italic">
                              Circuitos sin puerto asignado
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-center">
                          <span
                            className={`status-badge ${
                              c.active ? 'status-active' : 'status-neutral'
                            }`}
                          >
                            {c.active ? 'Activo' : 'Inactivo'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <PaginationBar
                  page={circuitsPage}
                  info={`Mostrando página ${circuitsPage} (${circuits.length} circuitos)`}
                  previousDisabled={circuitsOffset === 0}
                  nextDisabled={circuits.length < CIRCUITS_PAGE_SIZE}
                  onPrevious={() =>
                    setCircuitsOffset((cur) => Math.max(0, cur - CIRCUITS_PAGE_SIZE))
                  }
                  onNext={() => setCircuitsOffset((cur) => cur + CIRCUITS_PAGE_SIZE)}
                  className="border-t border-slate-800 p-3"
                />
              </div>
            )}
          </>
        )}
      </section>

      {/* Device Edit Modal */}
      {editDeviceOpen && (
        <DeviceFormModal
          isOpen={editDeviceOpen}
          device={device}
          nodes={nodes}
          onSaved={(updated) => {
            setEditDeviceOpen(false)
            setDevice(updated)
            setNotice(`Se actualizaron los datos del equipo «${updated.name}».`)
          }}
          onClose={() => setEditDeviceOpen(false)}
        />
      )}

      {/* Device Move Modal */}
      {moveDeviceOpen && (
        <DeviceMoveModal
          isOpen={moveDeviceOpen}
          device={device}
          currentNodeName={nodeName}
          nodes={nodes}
          onMoved={(updated) => {
            setMoveDeviceOpen(false)
            setDevice(updated)
            setNotice(`Se trasladó el equipo «${updated.name}» de nodo.`)
            setRefreshKey((k) => k + 1)
          }}
          onClose={() => setMoveDeviceOpen(false)}
        />
      )}

      {/* Device Status Toggle Modal */}
      {statusDeviceOpen && (
        <StatusConfirmationModal
          isOpen={statusDeviceOpen}
          itemName={device.name}
          itemType="equipo"
          currentActive={device.active}
          canToggle={!device.active || device.circuit_count === 0}
          blockReason={
            device.active && device.circuit_count > 0
              ? `El equipo tiene ${device.circuit_count} circuitos asociados (incluidos inactivos). No se puede desactivar un equipo con circuitos.`
              : undefined
          }
          onConfirm={async () => {
            const updated = await setDistributionDeviceStatus(device.id, !device.active)
            setStatusDeviceOpen(false)
            setDevice(updated)
            setNotice(`Se ${updated.active ? 'activó' : 'desactivó'} el equipo «${updated.name}».`)
          }}
          onClose={() => setStatusDeviceOpen(false)}
        />
      )}

      {/* Device Delete Modal */}
      {deleteDeviceOpen && (
        <DeleteConfirmationModal
          isOpen={deleteDeviceOpen}
          title="Eliminar equipo de distribución"
          itemName={device.name}
          itemType="equipo"
          canDelete={device.port_count === 0 && device.circuit_count === 0}
          blockReason={
            device.port_count > 0
              ? `El equipo conserva ${device.port_count} puertos registrados. Elimine primero todos sus puertos.`
              : device.circuit_count > 0
              ? `El equipo tiene ${device.circuit_count} circuitos asociados. Reasigne o retire primero los circuitos.`
              : undefined
          }
          onConfirm={async () => {
            await deleteDistributionDevice(device.id)
            setDeleteDeviceOpen(false)
            navigate('/distribution-devices')
          }}
          onClose={() => setDeleteDeviceOpen(false)}
        />
      )}

      {bulkPortOpen && <PortCreateDialog deviceId={device.id} deviceName={device.name} initialMode="complete" onClose={() => setBulkPortOpen(false)} onCreated={created => {
        setBulkPortOpen(false); setNotice(`Se crearon ${created.length} puertos.`); setRefreshKey(value => value + 1)
      }} />}
      {/* Port Create Modal */}
      {createPortOpen && (
        <PortFormModal
          isOpen={createPortOpen}
          device={device}
          onSaved={(newPort) => {
            setCreatePortOpen(false)
            setNotice(`Se creó el puerto «${newPort.name}» con éxito.`)
            setRefreshKey((k) => k + 1)
          }}
          onClose={() => setCreatePortOpen(false)}
        />
      )}

      {/* Port Edit Modal */}
      {editPort && (
        <PortFormModal
          isOpen={Boolean(editPort)}
          device={device}
          port={editPort}
          onSaved={(updatedPort) => {
            setEditPort(null)
            setNotice(`Se actualizó el puerto «${updatedPort.name}».`)
            setRefreshKey((k) => k + 1)
          }}
          onClose={() => setEditPort(null)}
        />
      )}

      {/* Port Move Modal */}
      {movePort && (
        <PortMoveModal
          isOpen={Boolean(movePort)}
          port={movePort}
          currentDeviceName={device.name}
          devices={allDevices}
          onMoved={(updatedPort) => {
            setMovePort(null)
            setNotice(`Se trasladó el puerto «${updatedPort.name}» al nuevo equipo.`)
            setRefreshKey((k) => k + 1)
          }}
          onClose={() => setMovePort(null)}
        />
      )}

      {/* Port Status Toggle Modal */}
      {statusPort && (
        <StatusConfirmationModal
          isOpen={Boolean(statusPort)}
          itemName={statusPort.name}
          itemType="puerto"
          currentActive={statusPort.active}
          canToggle={!statusPort.active || statusPort.circuit_count === 0}
          blockReason={
            statusPort.active && statusPort.circuit_count > 0
              ? `El puerto tiene ${statusPort.circuit_count} circuitos asociados. No se puede desactivar un puerto con circuitos.`
              : undefined
          }
          onConfirm={async () => {
            await setDistributionPortStatus(statusPort.id, !statusPort.active)
            setStatusPort(null)
            setNotice(
              `Se ${statusPort.active ? 'desactivó' : 'activó'} el puerto «${statusPort.name}».`,
            )
            setRefreshKey((k) => k + 1)
          }}
          onClose={() => setStatusPort(null)}
        />
      )}

      {/* Port Delete Modal */}
      {deletePort && (
        <DeleteConfirmationModal
          isOpen={Boolean(deletePort)}
          title="Eliminar puerto de distribución"
          itemName={deletePort.name}
          itemType="puerto"
          canDelete={deletePort.circuit_count === 0}
          blockReason={
            deletePort.circuit_count > 0
              ? `El puerto tiene ${deletePort.circuit_count} circuitos asociados. Reasigne o retire primero los circuitos.`
              : undefined
          }
          onConfirm={async () => {
            await deleteDistributionPort(deletePort.id)
            setDeletePort(null)
            setNotice(`Se eliminó el puerto «${deletePort.name}» con éxito.`)
            setRefreshKey((k) => k + 1)
          }}
          onClose={() => setDeletePort(null)}
        />
      )}
    </div>
  )
}
