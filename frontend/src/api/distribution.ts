import { deleteResource, getJson, patchJson, postJson } from './client'
import type {
  DeviceCreateInput,
  DeviceMoveInput,
  DistributionCircuit,
  DistributionDevice,
  DistributionDeviceFilter,
  DistributionEditInput,
  DistributionPort,
  DistributionPortFilter,
  PortCreateInput,
  PortMoveInput,
} from '../types/distribution'

export function getDistributionDevices(
  filters: DistributionDeviceFilter = {},
  signal?: AbortSignal,
): Promise<DistributionDevice[]> {
  const query = new URLSearchParams()
  if (filters.node_id !== undefined) query.set('node_id', String(filters.node_id))
  if (filters.search) query.set('search', filters.search)
  if (filters.active !== undefined) query.set('active', String(filters.active))
  if (filters.include_inactive !== undefined) query.set('include_inactive', String(filters.include_inactive))
  if (filters.limit !== undefined) query.set('limit', String(filters.limit))
  if (filters.offset !== undefined) query.set('offset', String(filters.offset))

  const qs = query.toString()
  return getJson<DistributionDevice[]>(`/api/distribution-devices${qs ? `?${qs}` : ''}`, signal)
}

export function getDistributionDevice(id: number, signal?: AbortSignal): Promise<DistributionDevice> {
  return getJson<DistributionDevice>(`/api/distribution-devices/${id}`, signal)
}

export function createDistributionDevice(
  payload: DeviceCreateInput,
  signal?: AbortSignal,
): Promise<DistributionDevice> {
  return postJson<DistributionDevice>('/api/distribution-devices', payload, signal)
}

export function updateDistributionDevice(
  id: number,
  payload: DistributionEditInput,
  signal?: AbortSignal,
): Promise<DistributionDevice> {
  return patchJson<DistributionDevice>(`/api/distribution-devices/${id}`, payload, signal)
}

export function moveDistributionDevice(
  id: number,
  payload: DeviceMoveInput,
  signal?: AbortSignal,
): Promise<DistributionDevice> {
  return postJson<DistributionDevice>(`/api/distribution-devices/${id}/move`, payload, signal)
}

export function setDistributionDeviceStatus(
  id: number,
  active: boolean,
  signal?: AbortSignal,
): Promise<DistributionDevice> {
  return patchJson<DistributionDevice>(`/api/distribution-devices/${id}/status`, { active }, signal)
}

export function deleteDistributionDevice(id: number, signal?: AbortSignal): Promise<void> {
  return deleteResource(`/api/distribution-devices/${id}`, signal)
}

export function getDistributionPorts(
  filters: DistributionPortFilter = {},
  signal?: AbortSignal,
): Promise<DistributionPort[]> {
  const query = new URLSearchParams()
  if (filters.distribution_device_id !== undefined) {
    query.set('distribution_device_id', String(filters.distribution_device_id))
  }
  if (filters.search) query.set('search', filters.search)
  if (filters.active !== undefined) query.set('active', String(filters.active))
  if (filters.include_inactive !== undefined) query.set('include_inactive', String(filters.include_inactive))
  if (filters.limit !== undefined) query.set('limit', String(filters.limit))
  if (filters.offset !== undefined) query.set('offset', String(filters.offset))

  const qs = query.toString()
  return getJson<DistributionPort[]>(`/api/distribution-ports${qs ? `?${qs}` : ''}`, signal)
}

export function getDistributionPort(id: number, signal?: AbortSignal): Promise<DistributionPort> {
  return getJson<DistributionPort>(`/api/distribution-ports/${id}`, signal)
}

export function createDistributionPort(
  payload: PortCreateInput,
  signal?: AbortSignal,
): Promise<DistributionPort> {
  return postJson<DistributionPort>('/api/distribution-ports', payload, signal)
}

export function updateDistributionPort(
  id: number,
  payload: DistributionEditInput,
  signal?: AbortSignal,
): Promise<DistributionPort> {
  return patchJson<DistributionPort>(`/api/distribution-ports/${id}`, payload, signal)
}

export function moveDistributionPort(
  id: number,
  payload: PortMoveInput,
  signal?: AbortSignal,
): Promise<DistributionPort> {
  return postJson<DistributionPort>(`/api/distribution-ports/${id}/move`, payload, signal)
}

export function setDistributionPortStatus(
  id: number,
  active: boolean,
  signal?: AbortSignal,
): Promise<DistributionPort> {
  return patchJson<DistributionPort>(`/api/distribution-ports/${id}/status`, { active }, signal)
}

export function deleteDistributionPort(id: number, signal?: AbortSignal): Promise<void> {
  return deleteResource(`/api/distribution-ports/${id}`, signal)
}

export function getDistributionDeviceCircuits(
  deviceId: number,
  params: { port_id?: number; without_port?: boolean; limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<DistributionCircuit[]> {
  const query = new URLSearchParams()
  if (params.port_id !== undefined) query.set('port_id', String(params.port_id))
  if (params.without_port) query.set('without_port', 'true')
  if (params.limit !== undefined) query.set('limit', String(params.limit))
  if (params.offset !== undefined) query.set('offset', String(params.offset))

  const qs = query.toString()
  return getJson<DistributionCircuit[]>(
    `/api/distribution-devices/${deviceId}/circuits${qs ? `?${qs}` : ''}`,
    signal,
  )
}
