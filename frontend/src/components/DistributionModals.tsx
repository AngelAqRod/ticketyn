import { DeviceTemplateChoice, manualTemplate, templatePayload, templateReady, type TemplateChoice } from './DeviceTemplateChoice'
import '../styles/distribution.css'
import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { createPortal } from 'react-dom'
import { AlertTriangle, Trash2, ArrowRightLeft } from 'lucide-react'
import {
  createDistributionDevice,
  deleteDistributionDevice,
  deleteDistributionPort,
  moveDistributionDevice,
  moveDistributionPort,
  setDistributionDeviceStatus,
  setDistributionPortStatus,
  updateDistributionDevice,
  updateDistributionPort,
} from '../api/distribution'
import { ApiError } from '../api/client'
import type { Node } from '../types/catalog'
import type { DistributionDevice, DistributionPort } from '../types/distribution'
import { FeedbackMessage } from './FeedbackMessage'
import { PortCreateDialog } from './PortCreateDialog'
import { useDistributionDialog } from '../hooks/useDistributionDialog'
import { FormField } from './FormField'
import { SearchableSelect } from './SearchableSelect'

const message = (cause: unknown, fallback: string) =>
  cause instanceof ApiError ? cause.message : cause instanceof Error ? cause.message : fallback


export function DeviceFormModal({
  isOpen,
  device,
  nodes,
  onSaved,
  onClose,
}: {
  isOpen: boolean
  device?: DistributionDevice | null
  nodes: Node[]
  onSaved: (saved: DistributionDevice) => void
  onClose: () => void
}) {
  const id = useId()
  const dialogRef = useDistributionDialog(isOpen)
  const isEdit = Boolean(device)
  const [template, setTemplate] = useState<TemplateChoice>(manualTemplate)
  const [name, setName] = useState('')
  const [nodeId, setNodeId] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [invalidFields, setInvalidFields] = useState<string[]>([])
  const sending = useRef(false)

  useEffect(() => {
    if (isOpen) {
      setTemplate(manualTemplate)
      setName(device?.name ?? '')
      setNodeId(device ? String(device.node_id) : '')
      setDescription(device?.description ?? '')
      setError(null)
      setInvalidFields([])
      sending.current = false
      setSaving(false)
    }
  }, [isOpen, device])

  if (!isOpen) return null

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (sending.current || (!isEdit && !templateReady(template))) return
    setError(null)
    setInvalidFields([])

    const trimmedName = name.trim()
    const trimmedDesc = description.trim()
    const fields: string[] = []

    if (!trimmedName || Array.from(trimmedName).length > 255) {
      fields.push('name')
    }
    if (!isEdit && !nodeId) {
      fields.push('node_id')
    }
    if (Array.from(description).length > 10000) {
      fields.push('description')
    }

    if (fields.length > 0) {
      setInvalidFields(fields)
      setError('Verifica los campos obligatorios: nombre (hasta 255 caracteres) y nodo.')
      return
    }

    sending.current = true
    setSaving(true)
    try {
      if (isEdit && device) {
        const updated = await updateDistributionDevice(device.id, {
          name: trimmedName,
          description: trimmedDesc ? description : null,
        })
        onSaved(updated)
      } else {
        const created = await createDistributionDevice({
          ...templatePayload(template),
          node_id: Number(nodeId),
          name: trimmedName,
          description: trimmedDesc ? description : null,
        })
        onSaved(created)
      }
    } catch (cause) {
      setError(message(cause, 'No se pudo guardar el equipo de distribución.'))
      if (cause instanceof ApiError) {
        setInvalidFields(cause.fields)
      }
    } finally {
      sending.current = false
      setSaving(false)
    }
  }

  return createPortal(
    <dialog
      ref={dialogRef}
      aria-labelledby={`${id}-title`}
      className="distribution-theme quick-dialog fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto rounded-2xl border border-purple-500/25 bg-[#0b1426] p-6 text-slate-100 shadow-2xl backdrop:bg-slate-950/80"
      onCancel={(e) => {
        e.preventDefault()
        if (!saving) onClose()
      }}
    >
      <h2 id={`${id}-title`} className="text-xl font-bold text-purple-200">
        {isEdit ? 'Editar equipo de distribución' : 'Nuevo equipo de distribución'}
      </h2>
      <p className="mt-1 text-xs text-slate-400">
        {isEdit
          ? 'Actualiza el nombre o la descripción. El nodo administrativo se gestiona por traslado.'
          : 'Registra un nuevo equipo de distribución dentro de un nodo operativo.'}
      </p>

      <form onSubmit={submit} className="mt-4 space-y-4" noValidate>
        {!isEdit && <DeviceTemplateChoice value={template} onChange={setTemplate} disabled={saving} />}
        {!isEdit && (
          <FormField
            id={`${id}-node`}
            label="Nodo"
            required
            invalid={invalidFields.includes('node_id')}
          >
            <SearchableSelect
              id={`${id}-node`}
              label="Nodo"
              required
              value={nodeId}
              onChange={setNodeId}
              options={nodes
                .filter((n) => n.active)
                .map((n) => ({ value: String(n.id), label: n.name }))}
              placeholder="Selecciona un nodo"
              emptyMessage="No hay nodos activos."
              noMatchMessage="Sin coincidencias."
            />
          </FormField>
        )}

        <FormField
          id={`${id}-name`}
          label="Nombre"
          required
          invalid={invalidFields.includes('name')}
        >
          <input
            id={`${id}-name`}
            type="text"
            required
            autoFocus
            className="form-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Ej. Switch-Core-01, OLT-Huawei-N1"
          />
          <p className="mt-1 text-xs text-slate-400">De 1 a 255 caracteres. No se permiten nombres duplicados en el mismo nodo.</p>
        </FormField>

        <FormField
          id={`${id}-desc`}
          label="Descripción (opcional)"
          invalid={invalidFields.includes('description')}
        >
          <textarea
            id={`${id}-desc`}
            rows={3}
            className="form-input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Detalles sobre modelo, rack, ubicación o propósito..."
          />
          <p className="mt-1 text-xs text-slate-400">Hasta 10000 caracteres.</p>
        </FormField>

        {error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}

        <div className="mt-6 flex justify-end gap-3 pt-2">
          <button
            type="button"
            className="button-secondary rounded-full"
            disabled={saving}
            onClick={onClose}
          >
            Cancelar
          </button>
          <button
            type="submit"
            className="button-primary button-primary--purple rounded-full"
            disabled={saving || (!isEdit && !templateReady(template))}
          >
            {saving ? 'Guardando...' : isEdit ? 'Actualizar equipo' : 'Crear equipo'}
          </button>
        </div>
      </form>
    </dialog>,
    document.body,
  )
}

export function PortFormModal({
  isOpen,
  device,
  port,
  onSaved,
  onClose,
}: {
  isOpen: boolean
  device: DistributionDevice
  port?: DistributionPort | null
  onSaved: (saved: DistributionPort) => void
  onClose: () => void
}) {
  const id = useId()
  const dialogRef = useDistributionDialog(isOpen && Boolean(port))
  const isEdit = Boolean(port)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [invalidFields, setInvalidFields] = useState<string[]>([])
  const sending = useRef(false)

  useEffect(() => {
    if (isOpen) {
      setName(port?.name ?? '')
      setDescription(port?.description ?? '')
      setError(null)
      setInvalidFields([])
      sending.current = false
      setSaving(false)
    }
  }, [isOpen, port])

  if (!isOpen) return null
  if (!port) return <PortCreateDialog deviceId={device.id} deviceName={device.name} onCreated={rows => { if (rows[0]) onSaved(rows[0]); else onClose() }} onClose={onClose} />

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (sending.current) return
    setError(null)
    setInvalidFields([])

    const trimmedName = name.trim()
    const trimmedDesc = description.trim()
    const fields: string[] = []

    if (!trimmedName || Array.from(trimmedName).length > 255) {
      fields.push('name')
    }
    if (Array.from(description).length > 10000) {
      fields.push('description')
    }

    if (fields.length > 0) {
      setInvalidFields(fields)
      setError('Indica un nombre válido (1 a 255 caracteres).')
      return
    }

    sending.current = true
    setSaving(true)
    try {
      if (isEdit && port) {
        const updated = await updateDistributionPort(port.id, {
          name: trimmedName,
          description: trimmedDesc ? description : null,
        })
        onSaved(updated)
      }
    } catch (cause) {
      setError(message(cause, 'No se pudo guardar el puerto de distribución.'))
      if (cause instanceof ApiError) {
        setInvalidFields(cause.fields)
      }
    } finally {
      sending.current = false
      setSaving(false)
    }
  }

  return createPortal(
    <dialog
      ref={dialogRef}
      aria-labelledby={`${id}-title`}
      className="distribution-theme quick-dialog fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto rounded-2xl border border-purple-500/25 bg-[#0b1426] p-6 text-slate-100 shadow-2xl backdrop:bg-slate-950/80"
      onCancel={(e) => {
        e.preventDefault()
        if (!saving) onClose()
      }}
    >
      <h2 id={`${id}-title`} className="text-xl font-bold text-purple-200">
        {isEdit ? 'Editar puerto de distribución' : 'Nuevo puerto de distribución'}
      </h2>
      <p className="mt-1 text-xs text-slate-400">
        Equipo: <strong className="text-white">{device.name}</strong>
      </p>

      <form onSubmit={submit} className="mt-4 space-y-4" noValidate>
        <FormField
          id={`${id}-name`}
          label="Nombre del puerto"
          required
          invalid={invalidFields.includes('name')}
        >
          <input
            id={`${id}-name`}
            type="text"
            required
            autoFocus
            className="form-input"
            readOnly={Boolean(port?.nomenclature_id)}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Ej. eth1, ge-0/0/1, sfp+1, PON 1/1"
          />
          <p className="mt-1 text-xs text-slate-400">De 1 a 255 caracteres. No se permiten nombres duplicados en el mismo equipo.</p>
        </FormField>

        <FormField
          id={`${id}-desc`}
          label="Descripción (opcional)"
          invalid={invalidFields.includes('description')}
        >
          <textarea
            id={`${id}-desc`}
            rows={3}
            className="form-input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Detalles sobre tipo de fibra, conector, módulo SFP..."
          />
          <p className="mt-1 text-xs text-slate-400">Hasta 10000 caracteres.</p>
        </FormField>

        {error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}

        <div className="mt-6 flex justify-end gap-3 pt-2">
          <button
            type="button"
            className="button-secondary rounded-full"
            disabled={saving}
            onClick={onClose}
          >
            Cancelar
          </button>
          <button
            type="submit"
            className="button-primary button-primary--purple rounded-full"
            disabled={saving}
          >
            {saving ? 'Guardando...' : isEdit ? 'Actualizar puerto' : 'Crear puerto'}
          </button>
        </div>
      </form>
    </dialog>,
    document.body,
  )
}

export function DeviceMoveModal({
  isOpen,
  device,
  currentNodeName,
  nodes,
  onMoved,
  onClose,
}: {
  isOpen: boolean
  device: DistributionDevice
  currentNodeName: string
  nodes: Node[]
  onMoved: (updated: DistributionDevice) => void
  onClose: () => void
}) {
  const id = useId()
  const dialogRef = useDistributionDialog(isOpen)
  const [targetNodeId, setTargetNodeId] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sending = useRef(false)

  const hasCircuits = device.circuit_count > 0

  useEffect(() => {
    if (isOpen) {
      setTargetNodeId('')
      setError(null)
      sending.current = false
      setSaving(false)
    }
  }, [isOpen])

  if (!isOpen) return null

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (sending.current || hasCircuits || !targetNodeId) return

    sending.current = true
    setSaving(true)
    setError(null)
    try {
      const updated = await moveDistributionDevice(device.id, {
        node_id: Number(targetNodeId),
      })
      onMoved(updated)
    } catch (cause) {
      setError(message(cause, 'No se pudo trasladar el equipo de distribución.'))
    } finally {
      sending.current = false
      setSaving(false)
    }
  }

  const availableNodes = nodes.filter(
    (n) => n.active && n.id !== device.node_id,
  )

  return createPortal(
    <dialog
      ref={dialogRef}
      aria-labelledby={`${id}-title`}
      className="distribution-theme quick-dialog fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto rounded-2xl border border-purple-500/25 bg-[#0b1426] p-6 text-slate-100 shadow-2xl backdrop:bg-slate-950/80"
      onCancel={(e) => {
        e.preventDefault()
        if (!saving) onClose()
      }}
    >
      <div className="flex items-center gap-3 text-purple-400">
        <ArrowRightLeft size={20} aria-hidden="true" />
        <h2 id={`${id}-title`} className="text-xl font-bold text-white">
          Trasladar equipo de nodo
        </h2>
      </div>
      <p className="mt-1 text-xs text-slate-400">
        Equipo: <strong className="text-white">{device.name}</strong> · Nodo actual:{' '}
        <strong className="text-white">{currentNodeName}</strong>
      </p>

      <div className="my-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs text-amber-200">
        <div className="flex items-start gap-2">
          <AlertTriangle size={16} className="shrink-0 text-amber-400 mt-0.5" aria-hidden="true" />
          <div className="space-y-1">
            <p className="font-semibold text-amber-300">
              Advertencia de modificación estructural:
            </p>
            <p>
              Se modificará la ubicación administrativa del equipo de distribución. Los puertos sin
              asociaciones acompañarán al equipo.
            </p>
            {hasCircuits && (
              <p className="font-bold text-red-400">
                Bloqueado: El equipo tiene {device.circuit_count}{' '}
                {device.circuit_count === 1 ? 'circuito asociado' : 'circuitos asociados'}{' '}
                (incluidos inactivos). No se puede trasladar de nodo mientras conserve circuitos.
              </p>
            )}
          </div>
        </div>
      </div>

      <form onSubmit={submit} className="space-y-4" noValidate>
        <FormField id={`${id}-target-node`} label="Nodo destino" required>
          <SearchableSelect
            id={`${id}-target-node`}
            label="Nodo destino"
            required
            disabled={hasCircuits || saving}
            value={targetNodeId}
            onChange={setTargetNodeId}
            options={availableNodes.map((n) => ({ value: String(n.id), label: n.name }))}
            placeholder="Selecciona el nodo destino"
            emptyMessage="No hay otros nodos activos disponibles."
            noMatchMessage="Sin coincidencias."
          />
        </FormField>

        {error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}

        <div className="mt-6 flex justify-end gap-3 pt-2">
          <button
            type="button"
            className="button-secondary rounded-full"
            disabled={saving}
            onClick={onClose}
          >
            Cancelar
          </button>
          <button
            type="submit"
            className="button-primary button-primary--purple rounded-full"
            disabled={saving || hasCircuits || !targetNodeId}
          >
            {saving ? 'Trasladando...' : 'Confirmar traslado'}
          </button>
        </div>
      </form>
    </dialog>,
    document.body,
  )
}

export function PortMoveModal({
  isOpen,
  port,
  currentDeviceName,
  devices,
  onMoved,
  onClose,
}: {
  isOpen: boolean
  port: DistributionPort
  currentDeviceName: string
  devices: DistributionDevice[]
  onMoved: (updated: DistributionPort) => void
  onClose: () => void
}) {
  const id = useId()
  const dialogRef = useDistributionDialog(isOpen)
  const [targetDeviceId, setTargetDeviceId] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sending = useRef(false)

  const hasCircuits = port.circuit_count > 0

  useEffect(() => {
    if (isOpen) {
      setTargetDeviceId('')
      setError(null)
      sending.current = false
      setSaving(false)
    }
  }, [isOpen])

  if (!isOpen) return null

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (sending.current || hasCircuits || !targetDeviceId) return

    sending.current = true
    setSaving(true)
    setError(null)
    try {
      const updated = await moveDistributionPort(port.id, {
        distribution_device_id: Number(targetDeviceId),
      })
      onMoved(updated)
    } catch (cause) {
      setError(message(cause, 'No se pudo trasladar el puerto de distribución.'))
    } finally {
      sending.current = false
      setSaving(false)
    }
  }

  const availableDevices = devices.filter(
    (d) => d.active && d.id !== port.distribution_device_id,
  )

  return createPortal(
    <dialog
      ref={dialogRef}
      aria-labelledby={`${id}-title`}
      className="distribution-theme quick-dialog fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto rounded-2xl border border-purple-500/25 bg-[#0b1426] p-6 text-slate-100 shadow-2xl backdrop:bg-slate-950/80"
      onCancel={(e) => {
        e.preventDefault()
        if (!saving) onClose()
      }}
    >
      <div className="flex items-center gap-3 text-purple-400">
        <ArrowRightLeft size={20} aria-hidden="true" />
        <h2 id={`${id}-title`} className="text-xl font-bold text-white">
          Trasladar puerto a otro equipo
        </h2>
      </div>
      <p className="mt-1 text-xs text-slate-400">
        Puerto: <strong className="text-white">{port.name}</strong> · Equipo actual:{' '}
        <strong className="text-white">{currentDeviceName}</strong>
      </p>

      <div className="my-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs text-amber-200">
        <div className="flex items-start gap-2">
          <AlertTriangle size={16} className="shrink-0 text-amber-400 mt-0.5" aria-hidden="true" />
          <div className="space-y-1">
            <p className="font-semibold text-amber-300">
              Advertencia de modificación estructural:
            </p>
            <p>
              Se modificará el equipo al que pertenece este puerto. El puerto conservará su historial y
              configuración siempre que no tenga circuitos asociados.
            </p>
            {hasCircuits && (
              <p className="font-bold text-red-400">
                Bloqueado: El puerto tiene {port.circuit_count}{' '}
                {port.circuit_count === 1 ? 'circuito asociado' : 'circuitos asociados'}. No se puede
                trasladar mientras conserve circuitos asociados.
              </p>
            )}
          </div>
        </div>
      </div>

      <form onSubmit={submit} className="space-y-4" noValidate>
        <FormField id={`${id}-target-device`} label="Equipo destino" required>
          <SearchableSelect
            id={`${id}-target-device`}
            label="Equipo destino"
            required
            disabled={hasCircuits || saving}
            value={targetDeviceId}
            onChange={setTargetDeviceId}
            options={availableDevices.map((d) => ({ value: String(d.id), label: d.name }))}
            placeholder="Selecciona el equipo destino"
            emptyMessage="No hay otros equipos activos disponibles."
            noMatchMessage="Sin coincidencias."
          />
        </FormField>

        {error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}

        <div className="mt-6 flex justify-end gap-3 pt-2">
          <button
            type="button"
            className="button-secondary rounded-full"
            disabled={saving}
            onClick={onClose}
          >
            Cancelar
          </button>
          <button
            type="submit"
            className="button-primary button-primary--purple rounded-full"
            disabled={saving || hasCircuits || !targetDeviceId}
          >
            {saving ? 'Trasladando...' : 'Confirmar traslado'}
          </button>
        </div>
      </form>
    </dialog>,
    document.body,
  )
}

export function DeleteConfirmationModal({
  isOpen,
  title,
  itemName,
  itemType,
  canDelete,
  blockReason,
  onConfirm,
  onClose,
}: {
  isOpen: boolean
  title: string
  itemName: string
  itemType: 'equipo' | 'puerto'
  canDelete: boolean
  blockReason?: string
  onConfirm: () => Promise<void>
  onClose: () => void
}) {
  const id = useId()
  const dialogRef = useDistributionDialog(isOpen)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sending = useRef(false)

  useEffect(() => {
    if (isOpen) {
      setError(null)
      sending.current = false
      setBusy(false)
    }
  }, [isOpen])

  if (!isOpen) return null

  async function handleConfirm() {
    if (sending.current || !canDelete) return
    sending.current = true
    setBusy(true)
    setError(null)
    try {
      await onConfirm()
    } catch (cause) {
      setError(message(cause, `No se pudo eliminar el ${itemType}.`))
      sending.current = false
      setBusy(false)
    }
  }

  return createPortal(
    <dialog
      ref={dialogRef}
      aria-labelledby={`${id}-title`}
      className="distribution-theme quick-dialog fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-md overflow-y-auto rounded-2xl border border-red-500/30 bg-[#0b1426] p-6 text-slate-100 shadow-2xl backdrop:bg-slate-950/80"
      onCancel={(e) => {
        e.preventDefault()
        if (!busy) onClose()
      }}
    >
      <div className="flex items-center gap-3 text-red-400">
        <Trash2 size={22} aria-hidden="true" />
        <h2 id={`${id}-title`} className="text-xl font-bold text-white">
          {title}
        </h2>
      </div>

      <p className="mt-3 text-sm text-slate-300">
        ¿Estás seguro de que deseas eliminar permanentemente el {itemType}{' '}
        <strong className="text-white">«{itemName}»</strong>?
      </p>

      {!canDelete ? (
        <div className="my-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3.5 text-xs text-red-200">
          <p className="font-semibold text-red-300">Eliminación protegida:</p>
          <p className="mt-1">{blockReason}</p>
        </div>
      ) : (
        <p className="my-3 text-xs text-slate-400">
          Esta acción no se puede deshacer. Se registrará en la bitácora operativa de distribución.
        </p>
      )}

      {error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}

      <div className="mt-6 flex justify-end gap-3 pt-2">
        <button
          type="button"
          className="button-secondary rounded-full"
          disabled={busy}
          onClick={onClose}
        >
          {canDelete ? 'Cancelar' : 'Entendido'}
        </button>
        {canDelete && (
          <button
            type="button"
            className="rounded-full bg-red-600 px-4 py-2 font-mono text-xs font-bold text-white shadow-sm hover:bg-red-500 disabled:opacity-50"
            disabled={busy}
            onClick={handleConfirm}
          >
            {busy ? 'Eliminando...' : `Eliminar ${itemType}`}
          </button>
        )}
      </div>
    </dialog>,
    document.body,
  )
}

export function StatusConfirmationModal({
  isOpen,
  itemName,
  itemType,
  currentActive,
  canToggle,
  blockReason,
  onConfirm,
  onClose,
}: {
  isOpen: boolean
  itemName: string
  itemType: 'equipo' | 'puerto'
  currentActive: boolean
  canToggle: boolean
  blockReason?: string
  onConfirm: () => Promise<void>
  onClose: () => void
}) {
  const id = useId()
  const dialogRef = useDistributionDialog(isOpen)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sending = useRef(false)

  const actionVerb = currentActive ? 'desactivar' : 'activar'
  const actionTitle = currentActive ? `Desactivar ${itemType}` : `Activar ${itemType}`

  useEffect(() => {
    if (isOpen) {
      setError(null)
      sending.current = false
      setBusy(false)
    }
  }, [isOpen])

  if (!isOpen) return null

  async function handleConfirm() {
    if (sending.current || !canToggle) return
    sending.current = true
    setBusy(true)
    setError(null)
    try {
      await onConfirm()
    } catch (cause) {
      setError(message(cause, `No se pudo ${actionVerb} el ${itemType}.`))
      sending.current = false
      setBusy(false)
    }
  }

  return createPortal(
    <dialog
      ref={dialogRef}
      aria-labelledby={`${id}-title`}
      className="distribution-theme quick-dialog fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-md overflow-y-auto rounded-2xl border border-purple-500/25 bg-[#0b1426] p-6 text-slate-100 shadow-2xl backdrop:bg-slate-950/80"
      onCancel={(e) => {
        e.preventDefault()
        if (!busy) onClose()
      }}
    >
      <h2 id={`${id}-title`} className="text-xl font-bold text-white">
        {actionTitle}
      </h2>

      <p className="mt-3 text-sm text-slate-300">
        ¿Deseas {actionVerb} el {itemType} <strong className="text-white">«{itemName}»</strong>?
      </p>

      {!canToggle ? (
        <div className="my-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs text-amber-200">
          <p className="font-semibold text-amber-300">Operación no permitida:</p>
          <p className="mt-1">{blockReason}</p>
        </div>
      ) : (
        <p className="my-3 text-xs text-slate-400">
          {currentActive
            ? `Al desactivar el ${itemType}, no se podrán asociar nuevos circuitos ni puertos. Los registros existentes se conservan.`
            : `El ${itemType} volverá a estar disponible para asignaciones operativas.`}
        </p>
      )}

      {error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}

      <div className="mt-6 flex justify-end gap-3 pt-2">
        <button
          type="button"
          className="button-secondary rounded-full"
          disabled={busy}
          onClick={onClose}
        >
          {canToggle ? 'Cancelar' : 'Entendido'}
        </button>
        {canToggle && (
          <button
            type="button"
            className={`rounded-full px-4 py-2 font-mono text-xs font-bold text-white shadow-sm disabled:opacity-50 ${
              currentActive
                ? 'bg-amber-600 hover:bg-amber-500'
                : 'bg-emerald-600 hover:bg-emerald-500'
            }`}
            disabled={busy}
            onClick={handleConfirm}
          >
            {busy ? 'Guardando...' : `Confirmar ${actionVerb}`}
          </button>
        )}
      </div>
    </dialog>,
    document.body,
  )
}
