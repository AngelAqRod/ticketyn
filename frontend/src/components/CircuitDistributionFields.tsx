import { useEffect, useId, useState } from 'react'
import { listDistributionDevices, listDistributionPorts } from '../api'
import { usePermissions } from '../auth/permissions'
import type { Circuit, DistributionDevice, DistributionPort, DistributionSummary } from '../types/catalog'
import { FormField } from './FormField'
import { QuickDistributionCreate } from './QuickDistributionCreate'
import { PortCreateDialog } from './PortCreateDialog'
import { RequestState } from './RequestState'
import { SearchableSelect } from './SearchableSelect'

interface Props {
  nodeId: string
  nodeName: string
  deviceId: string
  portId: string
  original?: Circuit
  disabled?: boolean
  invalidFields?: string[]
  onChange: (deviceId: string, portId: string) => void
  onModalChange: (open: boolean) => void
}
type Catalog<T> = { parent: string; rows: T[]; loading: boolean; error: string | null }
const empty = <T,>(parent = ''): Catalog<T> => ({ parent, rows: [], loading: false, error: null })
const message = (cause: unknown) => cause instanceof Error ? cause.message : 'No se pudo consultar el catálogo.'

export function CircuitDistributionFields({ nodeId, nodeName, deviceId, portId, original, disabled = false, invalidFields = [], onChange, onModalChange }: Props) {
  const access = usePermissions(), id = useId()
  const readDevices = access.any('distribution_devices.lookup', 'distribution_devices.view')
  const readPorts = access.any('distribution_ports.lookup', 'distribution_ports.view')
  const editable = access.any('circuits.create', 'context.circuits.create', 'circuits.edit')
  const [devices, setDevices] = useState<Catalog<DistributionDevice>>(empty)
  const [ports, setPorts] = useState<Catalog<DistributionPort>>(empty)
  const [deviceRetry, setDeviceRetry] = useState(0), [portRetry, setPortRetry] = useState(0)
  const [quick, setQuick] = useState<{ kind: 'device' | 'port'; node: string; device: string } | null>(null)
  const historicalDevice = original?.node_id === Number(nodeId) && original?.distribution_device_id === Number(deviceId) ? original.distribution_device : null
  const historicalPort = historicalDevice && original?.distribution_port_id === Number(portId) ? original.distribution_port : null
  const currentDevices = devices.parent === nodeId ? devices : empty<DistributionDevice>(nodeId)
  const currentPorts = ports.parent === deviceId ? ports : empty<DistributionPort>(deviceId)
  const selectedDevice = currentDevices.rows.find(row => String(row.id) === deviceId) ?? historicalDevice
  const selectedPort = currentPorts.rows.find(row => String(row.id) === portId) ?? historicalPort
  const quickValid = quick && !disabled && editable && quick.node === nodeId && quick.device === deviceId
    && (quick.kind === 'device' ? readDevices && access.can('distribution_devices.create') : readPorts && access.can('distribution_ports.create'))
  useEffect(() => { onModalChange(Boolean(quickValid)); return () => onModalChange(false) }, [Boolean(quickValid), onModalChange])
  useEffect(() => { setQuick(null) }, [nodeId, deviceId])
  useEffect(() => {
    const controller = new AbortController()
    if (!nodeId || !readDevices || !editable) { setDevices(empty(nodeId)); return }
    setDevices({ parent: nodeId, rows: [], loading: true, error: null })
    listDistributionDevices(Number(nodeId), controller.signal).then(rows => {
      if (!controller.signal.aborted) setDevices({ parent: nodeId, rows: rows.filter(row => row.node_id === Number(nodeId) && row.active), loading: false, error: null })
    }).catch(cause => { if (!controller.signal.aborted) setDevices({ parent: nodeId, rows: [], loading: false, error: message(cause) }) })
    return () => controller.abort()
  }, [nodeId, deviceRetry, readDevices, editable])
  useEffect(() => {
    const controller = new AbortController()
    if (!deviceId || !readPorts || !editable) { setPorts(empty(deviceId)); return }
    setPorts({ parent: deviceId, rows: [], loading: true, error: null })
    listDistributionPorts(Number(deviceId), controller.signal, true).then(rows => {
      if (!controller.signal.aborted) setPorts({ parent: deviceId, rows: rows.filter(row => row.distribution_device_id === Number(deviceId)), loading: false, error: null })
    }).catch(cause => { if (!controller.signal.aborted) setPorts({ parent: deviceId, rows: [], loading: false, error: message(cause) }) })
    return () => controller.abort()
  }, [deviceId, portRetry, readPorts, editable])

  function options(rows: DistributionSummary[], selected: DistributionSummary | null | undefined) {
    const all = selected && !rows.some(row => row.id === selected.id) ? [...rows, selected] : rows
    return all.map(row => ({ value: String(row.id), label: row.name, disabled: !row.active }))
  }
  return <>
    <FormField id={`${id}-device`} label="Equipo de distribución" invalid={invalidFields.includes('distribution_device_id')}>
      <div className="flex gap-2"><div className="min-w-0 flex-1">
        <SearchableSelect id={`${id}-device`} label="Equipo de distribución" value={deviceId} options={options(currentDevices.rows, historicalDevice)}
          onChange={value => onChange(value, value === deviceId ? portId : '')} disabled={disabled || !editable || !nodeId || !readDevices || currentDevices.loading || Boolean(currentDevices.error)}
          placeholder={nodeId ? 'No asignado' : 'Selecciona un nodo primero'} emptyMessage="No hay equipos activos en este nodo." noMatchMessage="No se encontraron equipos." />
      </div><button type="button" className="button-secondary rounded-full" aria-label="Nuevo equipo de distribución" title="Nuevo equipo de distribución"
        disabled={disabled || !editable || !nodeId || !readDevices || !access.can('distribution_devices.create') || currentDevices.loading || Boolean(currentDevices.error)} onClick={() => setQuick({ kind: 'device', node: nodeId, device: deviceId })}>+</button></div>
      {!readDevices && <p className="mt-1 text-xs text-slate-300">Sin permiso para consultar equipos.</p>}
      {selectedDevice?.active === false && <p className="mt-1 text-xs text-slate-300">Equipo asignado inactivo. Puedes conservarlo o retirar la asignación.</p>}
      <RequestState compact loading={currentDevices.loading} loadingText="Cargando equipos del nodo..." error={currentDevices.error} errorTitle="" retryText="Reintentar equipos" onRetry={() => setDeviceRetry(value => value + 1)} />
    </FormField>
    <FormField id={`${id}-port`} label="Puerto de distribución" invalid={invalidFields.includes('distribution_port_id')}>
      <div className="flex gap-2"><div className="min-w-0 flex-1">
        <SearchableSelect id={`${id}-port`} label="Puerto de distribución" value={portId} options={options(currentPorts.rows.filter(row => row.active || row.id === historicalPort?.id), historicalPort).map(option => ({ ...option, disabled: option.disabled || selectedDevice?.active !== true }))}
          onChange={value => onChange(deviceId, value)} disabled={disabled || !editable || !deviceId || !readPorts || currentPorts.loading || Boolean(currentPorts.error)}
          placeholder={deviceId ? 'No asignado' : 'Selecciona un equipo primero'} emptyMessage="No hay puertos activos en este equipo." noMatchMessage="No se encontraron puertos." />
      </div><button type="button" className="button-secondary rounded-full" aria-label="Nuevo puerto de distribución" title="Nuevo puerto de distribución"
        disabled={disabled || !editable || !deviceId || selectedDevice?.active !== true || !readPorts || !access.can('distribution_ports.create') || currentPorts.loading || Boolean(currentPorts.error)} onClick={() => setQuick({ kind: 'port', node: nodeId, device: deviceId })}>+</button></div>
      {!readPorts && <p className="mt-1 text-xs text-slate-300">Sin permiso para consultar puertos.</p>}
      {selectedPort?.active === false && <p className="mt-1 text-xs text-slate-300">Puerto asignado inactivo. Puedes conservarlo o retirar la asignación.</p>}
      <RequestState compact loading={currentPorts.loading} loadingText="Cargando puertos del equipo..." error={currentPorts.error} errorTitle="" retryText="Reintentar puertos" onRetry={() => setPortRetry(value => value + 1)} />
    </FormField>
    {quickValid && quick.kind === 'device' && <QuickDistributionCreate key={`device-${quick.node}`} kind="device" parentId={Number(nodeId)} parentName={nodeName || `#${nodeId}`}
      onCancel={() => setQuick(null)} onCreated={item => {
        setDevices(current => ({ ...current, rows: [...current.rows.filter(row => row.id !== item.id), item] }))
        onChange(String(item.id), ''); setQuick(null)
      }} />}
    {quickValid && quick.kind === 'port' && <PortCreateDialog key={`port-${quick.device}`} deviceId={Number(deviceId)} deviceName={selectedDevice?.name || `#${deviceId}`} circuitContext
      onClose={() => setQuick(null)} onCreated={created => {
        setPortRetry(value => value + 1)
        if (created.length === 1) onChange(deviceId, String(created[0].id))
        setQuick(null)
      }} />}
  </>
}
