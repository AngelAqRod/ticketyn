import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import {
  ArrowRightLeft,
  Filter,
  Network,
  Pencil,
  Plus,
  Power,
  RotateCcw,
  Search,
  Server,
  Trash2,
} from 'lucide-react'
import {
  deleteDistributionDevice,
  getDistributionDevices,
  setDistributionDeviceStatus,
} from '../api/distribution'
import { listNodes } from '../api'
import { Can, usePermissions } from '../auth/permissions'
import { CircuitsNavigation } from '../components/CircuitsNavigation'
import {
  DeleteConfirmationModal,
  DeviceFormModal,
  DeviceMoveModal,
  StatusConfirmationModal,
} from '../components/DistributionModals'
import { FeedbackMessage } from '../components/FeedbackMessage'
import { PageHeading } from '../components/PageHeading'
import { PaginationBar } from '../components/PaginationBar'
import { RequestState } from '../components/RequestState'
import { SearchableSelect } from '../components/SearchableSelect'
import { useUrlFilters } from '../hooks/useUrlFilters'
import type { Node } from '../types/catalog'
import type { DistributionDevice } from '../types/distribution'

const PAGE_SIZE = 50

export function DistributionDevices() {
  const access = usePermissions()
  const navigate = useNavigate()
  const { params, change, clear } = useUrlFilters(['search', 'node_id', 'active'])

  const [items, setItems] = useState<DistributionDevice[]>([])
  const [nodes, setNodes] = useState<Node[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  // Modals state
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [editDevice, setEditDevice] = useState<DistributionDevice | null>(null)
  const [moveDevice, setMoveDevice] = useState<DistributionDevice | null>(null)
  const [statusDevice, setStatusDevice] = useState<DistributionDevice | null>(null)
  const [deleteDevice, setDeleteDevice] = useState<DistributionDevice | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const offset = Math.max(0, Number(params.get('offset') ?? 0) || 0)
  const search = params.get('search') ?? ''
  const nodeId = params.get('node_id') ?? ''
  const activeParam = params.get('active') ?? ''

  // Load nodes catalog once
  useEffect(() => {
    const controller = new AbortController()
    listNodes(controller.signal, true)
      .then((data) => {
        if (!controller.signal.aborted) setNodes(data)
      })
      .catch(() => {
        // Ignored; nodes fallback to IDs if load fails
      })
    return () => controller.abort()
  }, [])

  // Load devices list with filters & pagination
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)

    const activeFilter =
      activeParam === 'true' ? true : activeParam === 'false' ? false : undefined

    getDistributionDevices(
      {
        node_id: nodeId ? Number(nodeId) : undefined,
        search: search.trim() || undefined,
        active: activeFilter,
        include_inactive: true,
        limit: PAGE_SIZE,
        offset,
      },
      controller.signal,
    )
      .then((rows) => {
        if (!controller.signal.aborted) {
          setItems(rows)
          setLoading(false)
        }
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : 'No se pudo consultar el listado de equipos.')
          setLoading(false)
        }
      })

    return () => controller.abort()
  }, [search, nodeId, activeParam, offset, refreshKey])

  function handleFilterChange(key: string, value: string) {
    change({ [key]: value, offset: '0' })
  }

  function handleClearFilters() {
    clear()
  }

  const nodesMap = new Map(nodes.map((n) => [n.id, n.name]))

  // Active / total counts for telemetry
  const activeCount = items.filter((d) => d.active).length
  const page = Math.floor(offset / PAGE_SIZE) + 1

  return (
    <div className="distribution-theme space-y-4">
      <PageHeading
        title="Equipos de distribución"
        description="Gestión e inventario de switches, routers y OLTs de distribución por nodo operativo."
        theme="purple"
        telemetry={
          !loading &&
          !error && (
            <span className="heading-telemetry">
              <span>Equipos en vista:</span>
              <strong className="telemetry-value--purple">{items.length}</strong>
              <span className="text-slate-600">·</span>
              <span>Activos:</span>
              <strong className="text-emerald-400">{activeCount}</strong>
            </span>
          )
        }
        action={
          <Can permission="distribution_devices.create">
            <button
              type="button"
              className="button-primary button-primary--purple rounded-full shadow-sm"
              onClick={() => setCreateModalOpen(true)}
            >
              <Plus size={15} aria-hidden="true" />
              Nuevo equipo
            </button>
          </Can>
        }
      />

      <CircuitsNavigation />

      {notice && (
        <FeedbackMessage variant="success" className="mb-4">
          {notice}
        </FeedbackMessage>
      )}

      {/* Filters section */}
      <section
        aria-label="Filtros de equipos de distribución"
        className="panel filter-toolbar--purple p-4 rounded-2xl bg-[#0b1426] border border-purple-500/20 shadow-lg space-y-3"
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-purple-500/15 pb-2.5">
          <div className="flex items-center gap-2">
            <Filter size={14} className="text-purple-400" aria-hidden="true" />
            <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
              Filtros de búsqueda
            </h2>
          </div>
          {(search || nodeId || activeParam) && (
            <button
              type="button"
              onClick={handleClearFilters}
              className="button-ghost text-xs text-purple-400 hover:text-purple-300 font-mono inline-flex items-center gap-1"
            >
              <RotateCcw size={12} aria-hidden="true" />
              Limpiar filtros
            </button>
          )}
        </div>

        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <label htmlFor="device-search" className="form-label text-xs">
              Buscar por nombre o descripción
            </label>
            <div className="relative mt-1">
              <input
                id="device-search"
                type="text"
                className="form-input pl-8"
                placeholder="Ej. Switch-Core, Huawei, OLT..."
                value={search}
                onChange={(e) => handleFilterChange('search', e.target.value)}
              />
              <Search
                size={14}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"
                aria-hidden="true"
              />
            </div>
          </div>

          <div>
            <label id="device-node-label" className="form-label text-xs">
              Filtrar por nodo
            </label>
            <div className="mt-1">
              <SearchableSelect
                id="device-node"
                label="Filtrar por nodo"
                value={nodeId}
                onChange={(val) => handleFilterChange('node_id', val)}
                options={nodes.map((n) => ({
                  value: String(n.id),
                  label: `${n.name}${n.active ? '' : ' (Inactivo)'}`,
                }))}
                placeholder="Todos los nodos"
                emptyMessage="No hay nodos disponibles."
                noMatchMessage="Sin coincidencias."
              />
            </div>
          </div>

          <div>
            <label htmlFor="device-status" className="form-label text-xs">
              Estado administrativo
            </label>
            <select
              id="device-status"
              className="form-input mt-1"
              value={activeParam}
              onChange={(e) => handleFilterChange('active', e.target.value)}
            >
              <option value="">Todos los estados</option>
              <option value="true">Solo activos</option>
              <option value="false">Solo inactivos</option>
            </select>
          </div>
        </div>
      </section>

      {/* Devices table */}
      <section aria-label="Listado de equipos de distribución">
        <RequestState
          loading={loading}
          loadingText="Consultando equipos de distribución..."
          error={error}
          onRetry={() => setRefreshKey((k) => k + 1)}
        />

        {!loading && !error && items.length === 0 && (
          <div className="panel p-8 text-center rounded-2xl bg-[#0b1426] border border-purple-500/20 text-slate-400">
            <Server size={32} className="mx-auto mb-2 text-purple-400/50" aria-hidden="true" />
            <p className="font-semibold text-white">No se encontraron equipos de distribución.</p>
            <p className="text-xs mt-1 text-slate-400">
              {search || nodeId || activeParam
                ? 'Intenta ajustar los criterios de búsqueda o limpiar los filtros.'
                : 'Registra el primer equipo de distribución para comenzar a asignar puertos y circuitos.'}
            </p>
          </div>
        )}

        {!loading && !error && items.length > 0 && (
          <div className="table-surface--purple overflow-x-auto rounded-2xl border border-purple-500/20 bg-[#0b1426] shadow-xl">
            <table className="w-full text-left text-sm text-slate-200">
              <thead className="border-b border-purple-500/15 bg-[#070d1a] font-mono text-xs uppercase tracking-wider text-slate-400">
                <tr>
                  <th scope="col" className="px-4 py-3 font-semibold">
                    Equipo
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold">
                    Nodo
                  </th>
                  <th scope="col" className="px-4 py-3 font-semibold">
                    Descripción
                  </th>
                  <th scope="col" className="px-4 py-3 text-center font-semibold">
                    Puertos
                  </th>
                  <th scope="col" className="px-4 py-3 text-center font-semibold">
                    Puertos sin circuitos
                  </th>
                  <th scope="col" className="px-4 py-3 text-center font-semibold">
                    Circuitos
                  </th>
                  <th scope="col" className="px-4 py-3 text-center font-semibold">
                    Estado
                  </th>
                  <th scope="col" className="px-4 py-3 text-right font-semibold">
                    Acciones
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/80">
                {items.map((dev) => (
                  <tr key={dev.id} className="hover:bg-purple-500/5 transition-colors">
                    <td className="px-4 py-3 font-medium text-white">
                      <Link
                        to={`/distribution-devices/${dev.id}`}
                        className="text-purple-400 hover:text-purple-300 font-mono font-bold hover:underline inline-flex items-center gap-1.5"
                      >
                        <Server size={14} className="shrink-0 text-purple-400/80" aria-hidden="true" />
                        <span>{dev.name}</span>
                      </Link>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-300">
                      {nodesMap.get(dev.node_id) ?? `Nodo #${dev.node_id}`}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-400 max-w-xs truncate">
                      {dev.description || '—'}
                    </td>
                    <td className="px-4 py-3 text-center font-mono text-xs text-blue-400 font-bold">
                      {dev.port_count}
                    </td>
                    <td className="px-4 py-3 text-center font-mono text-xs text-emerald-400 font-bold" title="Puertos registrados sin asociaciones; no indica disponibilidad física">
                      {dev.unassigned_port_count ?? <span className="text-slate-400" aria-label="Dato no disponible">—</span>}
                    </td>
                    <td className="px-4 py-3 text-center font-mono text-xs text-purple-300 font-bold">
                      {dev.circuit_count}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span
                        className={`status-badge ${
                          dev.active ? 'status-active' : 'status-neutral'
                        }`}
                      >
                        {dev.active ? 'Activo' : 'Inactivo'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <Link
                          to={`/distribution-devices/${dev.id}`}
                          className="button-ghost p-1.5 text-xs text-purple-400 hover:text-purple-300 rounded-lg hover:bg-purple-500/10"
                          title="Ver detalle y puertos"
                          aria-label={`Ver detalle del equipo ${dev.name}`}
                        >
                          Ver ficha →
                        </Link>

                        <Can permission="distribution_devices.edit">
                          <button
                            type="button"
                            className="button-ghost p-1.5 text-slate-300 hover:text-white rounded-lg hover:bg-slate-800"
                            title="Editar nombre y descripción"
                            aria-label={`Editar equipo ${dev.name}`}
                            onClick={() => setEditDevice(dev)}
                          >
                            <Pencil size={14} aria-hidden="true" />
                          </button>
                        </Can>

                        <Can permission="distribution_devices.move">
                          <button
                            type="button"
                            className="button-ghost p-1.5 text-slate-300 hover:text-purple-400 rounded-lg hover:bg-slate-800"
                            title="Trasladar de nodo"
                            aria-label={`Trasladar equipo ${dev.name}`}
                            onClick={() => setMoveDevice(dev)}
                          >
                            <ArrowRightLeft size={14} aria-hidden="true" />
                          </button>
                        </Can>

                        <Can permission="distribution_devices.set_active">
                          <button
                            type="button"
                            className={`button-ghost p-1.5 rounded-lg hover:bg-slate-800 ${
                              dev.active
                                ? 'text-amber-400 hover:text-amber-300'
                                : 'text-emerald-400 hover:text-emerald-300'
                            }`}
                            title={dev.active ? 'Desactivar equipo' : 'Activar equipo'}
                            aria-label={`${dev.active ? 'Desactivar' : 'Activar'} equipo ${dev.name}`}
                            onClick={() => setStatusDevice(dev)}
                          >
                            <Power size={14} aria-hidden="true" />
                          </button>
                        </Can>

                        <Can permission="distribution_devices.delete">
                          <button
                            type="button"
                            className="button-ghost p-1.5 text-red-400 hover:text-red-300 rounded-lg hover:bg-red-500/10"
                            title="Eliminar equipo"
                            aria-label={`Eliminar equipo ${dev.name}`}
                            onClick={() => setDeleteDevice(dev)}
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

            <PaginationBar
              page={page}
              info={`Mostrando página ${page} (${items.length} equipos)`}
              previousDisabled={offset === 0}
              nextDisabled={items.length < PAGE_SIZE}
              onPrevious={() => change({ offset: String(Math.max(0, offset - PAGE_SIZE)) })}
              onNext={() => change({ offset: String(offset + PAGE_SIZE) })}
              className="border-t border-slate-800 p-3"
            />
          </div>
        )}
      </section>

      {/* Create Device Modal */}
      <DeviceFormModal
        isOpen={createModalOpen}
        nodes={nodes}
        onSaved={(created) => {
          setCreateModalOpen(false)
          setNotice(`Se creó el equipo «${created.name}» con éxito.`)
          setRefreshKey((k) => k + 1)
        }}
        onClose={() => setCreateModalOpen(false)}
      />

      {/* Edit Device Modal */}
      {editDevice && (
        <DeviceFormModal
          isOpen={Boolean(editDevice)}
          device={editDevice}
          nodes={nodes}
          onSaved={(updated) => {
            setEditDevice(null)
            setNotice(`Se actualizó el equipo «${updated.name}».`)
            setRefreshKey((k) => k + 1)
          }}
          onClose={() => setEditDevice(null)}
        />
      )}

      {/* Move Device Modal */}
      {moveDevice && (
        <DeviceMoveModal
          isOpen={Boolean(moveDevice)}
          device={moveDevice}
          currentNodeName={nodesMap.get(moveDevice.node_id) ?? `Nodo #${moveDevice.node_id}`}
          nodes={nodes}
          onMoved={(updated) => {
            setMoveDevice(null)
            setNotice(`Se trasladó el equipo «${updated.name}» al nuevo nodo.`)
            setRefreshKey((k) => k + 1)
          }}
          onClose={() => setMoveDevice(null)}
        />
      )}

      {/* Status Toggle Modal */}
      {statusDevice && (
        <StatusConfirmationModal
          isOpen={Boolean(statusDevice)}
          itemName={statusDevice.name}
          itemType="equipo"
          currentActive={statusDevice.active}
          canToggle={!statusDevice.active || statusDevice.circuit_count === 0}
          blockReason={
            statusDevice.active && statusDevice.circuit_count > 0
              ? `El equipo tiene ${statusDevice.circuit_count} circuitos asociados (incluidos inactivos). No se puede desactivar un equipo con circuitos.`
              : undefined
          }
          onConfirm={async () => {
            await setDistributionDeviceStatus(statusDevice.id, !statusDevice.active)
            setStatusDevice(null)
            setNotice(
              `Se ${statusDevice.active ? 'desactivó' : 'activó'} el equipo «${statusDevice.name}».`,
            )
            setRefreshKey((k) => k + 1)
          }}
          onClose={() => setStatusDevice(null)}
        />
      )}

      {/* Delete Device Modal */}
      {deleteDevice && (
        <DeleteConfirmationModal
          isOpen={Boolean(deleteDevice)}
          title="Eliminar equipo de distribución"
          itemName={deleteDevice.name}
          itemType="equipo"
          canDelete={deleteDevice.port_count === 0 && deleteDevice.circuit_count === 0}
          blockReason={
            deleteDevice.port_count > 0
              ? `El equipo conserva ${deleteDevice.port_count} puertos registrados. Debe eliminar todos sus puertos antes de eliminar el equipo.`
              : deleteDevice.circuit_count > 0
              ? `El equipo tiene ${deleteDevice.circuit_count} circuitos asociados. Debe reasignar o retirar los circuitos antes de eliminar el equipo.`
              : undefined
          }
          onConfirm={async () => {
            await deleteDistributionDevice(deleteDevice.id)
            setDeleteDevice(null)
            setNotice(`Se eliminó el equipo «${deleteDevice.name}» con éxito.`)
            setRefreshKey((k) => k + 1)
          }}
          onClose={() => setDeleteDevice(null)}
        />
      )}
    </div>
  )
}
