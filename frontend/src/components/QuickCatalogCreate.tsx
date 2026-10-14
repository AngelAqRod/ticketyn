import { capacityInMicroMbps } from '../lib/capacity'
import { CapacityFields } from './CapacityFields'
import { RequestState } from './RequestState'
import { FeedbackMessage } from './FeedbackMessage'
import { ApiError } from '../api/client'
import { useEffect, useId, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { createCircuit, createCustomer, createNode, listNodes, listServiceTypes, listSectors } from '../api'
import type { Circuit, Customer, Node, ServiceType } from '../types/catalog'
import { SearchableSelect } from './SearchableSelect'
import { FormField } from './FormField'

type Props = {
  onCancel: () => void
} & ({ kind: 'customer'; onCreated: (customer: Customer) => void } | {
  kind: 'circuit'; customer: Customer; onCreated: (circuit: Circuit) => void
} | { kind: 'node'; onCreated: (node: Node) => void })

export function QuickCatalogCreate(props: Props) {
  const errorId = useId()
  const nodeErrorId = useId()
  const [capacity, setCapacity] = useState(''), [capacityUnit, setCapacityUnit] = useState('Mbps')
  const [code, setCode] = useState('')
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [apiInvalidFields, setApiInvalidFields] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const sending = useRef(false)
  const dialog = useRef<HTMLDialogElement>(null)
  const codeInput = useRef<HTMLInputElement>(null)
  const controller = useRef<AbortController | null>(null)
  const customerMode = props.kind === 'customer'
  const nodeMode = props.kind === 'node'
  const [serviceTypes, setServiceTypes] = useState<ServiceType[]>([]), [serviceTypeId, setServiceTypeId] = useState(''), [serviceLoading, setServiceLoading] = useState(props.kind === 'circuit'), [serviceError, setServiceError] = useState<string | null>(null), [serviceRetry, setServiceRetry] = useState(0)
  const [sectors, setSectors] = useState<ServiceType[]>([]), [sectorId, setSectorId] = useState(''), [sectorError, setSectorError] = useState<string | null>(null), [sectorRetry, setSectorRetry] = useState(0)
  useEffect(() => {
    if (props.kind !== 'circuit') return
    const request = new AbortController(); setSectorError(null)
    listSectors(request.signal).then(rows => { if (!request.signal.aborted) setSectors(rows) }).catch(failure => { if (!request.signal.aborted) setSectorError(failure instanceof Error ? failure.message : 'No se pudieron cargar sectores.') })
    return () => request.abort()
  }, [props.kind, sectorRetry])
  const [nodes, setNodes] = useState<Node[]>([])
  const [nodeId, setNodeId] = useState('')
  const [nodeLoading, setNodeLoading] = useState(props.kind === 'circuit')
  const [nodeError, setNodeError] = useState<string | null>(null)
  const [nodeRetry, setNodeRetry] = useState(0)
  const [quickNode, setQuickNode] = useState(false)
  const title = nodeMode ? 'Nuevo nodo' : customerMode ? 'Nuevo cliente' : 'Nuevo circuito'
  useEffect(() => {
    if (props.kind !== 'circuit') return
    const request = new AbortController()
    setNodeLoading(true); setNodeError(null)
    listNodes(request.signal).then((rows) => { if (!request.signal.aborted) { setNodes((current) => [...rows, ...current.filter((item) => !rows.some((row) => row.id === item.id))]); setNodeLoading(false) } }).catch((failure: unknown) => { if (!request.signal.aborted) { setNodeLoading(false); setNodeError(failure instanceof Error ? failure.message : 'No se pudieron cargar nodos.') } })
    return () => request.abort()
  }, [props.kind, nodeRetry])

  useEffect(() => {
    if (props.kind !== 'circuit') return
    const request = new AbortController(); setServiceLoading(true); setServiceError(null)
    listServiceTypes(request.signal).then((rows) => { if (!request.signal.aborted) { setServiceTypes(rows); setServiceLoading(false) } }).catch((failure: unknown) => { if (!request.signal.aborted) { setServiceLoading(false); setServiceError(failure instanceof Error ? failure.message : 'No se pudieron cargar los tipos de servicio.') } })
    return () => request.abort()
  }, [props.kind, serviceRetry])

  useEffect(() => {
    const element = dialog.current!
    const previousFocus = document.activeElement
    element.showModal()
    codeInput.current?.focus()
    return () => {
      controller.current?.abort()
      element.close()
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus()
    }
  }, [])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (sending.current) return
    setError(null); setApiInvalidFields([])
    if ((!nodeMode && !code.trim()) || !text.trim()) { setError('Completa los campos obligatorios.'); return }
    if (props.kind === 'circuit' && (!nodeId || nodeError || nodeLoading)) { setError('Selecciona un Nodo antes de guardar.'); return }
    if (props.kind === 'circuit' && (!sectorId || sectorError)) { setError('Selecciona un Sector antes de guardar.'); return }
    if (props.kind === 'circuit' && capacity) { try { capacityInMicroMbps(capacity, capacityUnit) } catch (failure) { setError(failure instanceof Error ? failure.message : 'Capacidad inválida.'); return } }
    sending.current = true
    setSaving(true)
    const request = new AbortController()
    controller.current = request
    try {
      if (props.kind === 'customer') {
        const customer = await createCustomer({ customer_code: code.trim(), name: text.trim(), active: true }, request.signal)
        if (!request.signal.aborted) props.onCreated(customer)
      } else if (props.kind === 'node') {
        const node = await createNode({ name: text.trim(), active: true }, request.signal)
        if (!request.signal.aborted) props.onCreated(node)
      } else {
        const circuit = await createCircuit({ sector_id: Number(sectorId), ...(serviceTypeId ? { service_type_id: Number(serviceTypeId) } : {}), ...(capacity ? { initial_capacity: capacity, initial_capacity_unit: capacityUnit } : {}), customer_id: props.customer.id, circuit_code: code.trim(), description: text.trim(), active: true, node_id: Number(nodeId) }, request.signal)
        if (!request.signal.aborted) props.onCreated(circuit)
      }
    } catch (failure) {
      if (!request.signal.aborted) { setError(failure instanceof Error ? failure.message : 'No se pudo crear el registro.'); setApiInvalidFields(failure instanceof ApiError ? failure.fields : []) }
    } finally {
      sending.current = false
      if (!request.signal.aborted) setSaving(false)
    }
  }

  return <><dialog ref={dialog} aria-labelledby={`quick-create-title-${props.kind}`} aria-describedby={`quick-create-description-${props.kind}`} aria-modal="true"
    className="fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-md overflow-y-auto quick-dialog border border-slate-200 bg-white p-5 text-ink backdrop:bg-slate-900/30"
    onCancel={(event) => { event.preventDefault(); event.stopPropagation(); if (!sending.current && !quickNode) props.onCancel() }}>
    <div className="quick-dialog-header"><p className="module-eyebrow">Creación rápida</p><h2 id={`quick-create-title-${props.kind}`} className="text-xl font-semibold">{title}</h2>
    <p id={`quick-create-description-${props.kind}`} className="mb-4 mt-2 text-sm text-slate-500">Se creará un registro activo. El formulario principal se guarda por separado.</p></div>
    {props.kind === 'circuit' && <p className="mb-4 text-sm"><span className="font-medium">Cliente: </span>{props.customer.customer_code} — {props.customer.name}</p>}
    <form aria-label={`Crear ${nodeMode ? 'nodo' : customerMode ? 'cliente' : 'circuito'} rápido`} onSubmit={submit} noValidate aria-describedby={error ? errorId : undefined}>
      <fieldset disabled={saving} className="space-y-3"><legend className="sr-only">Datos del registro</legend>
        {!nodeMode && <FormField describedBy={error ? errorId : undefined} invalid={(error === "Completa los campos obligatorios." && !code.trim()) || apiInvalidFields.includes(customerMode ? "customer_code" : "circuit_code")} id="quick-code" label={customerMode ? 'Código de cliente' : 'Código de circuito'} required><input ref={codeInput} id="quick-code" className="form-input" required value={code} onChange={(event) => setCode(event.target.value)} /></FormField>}
        <FormField describedBy={error ? errorId : undefined} invalid={(error === "Completa los campos obligatorios." && !text.trim()) || apiInvalidFields.includes(props.kind === "circuit" ? "description" : "name")} id={`quick-text-${props.kind}`} label={customerMode || nodeMode ? 'Nombre' : 'Descripción'} required><input ref={nodeMode ? codeInput : undefined} id={`quick-text-${props.kind}`} className="form-input" required value={text} onChange={(event) => setText(event.target.value)} /></FormField>
        {props.kind === 'circuit' && <FormField id="quick-sector" label="Sector" required describedBy={error ? errorId : undefined} invalid={Boolean(error && !sectorId) || apiInvalidFields.includes("sector_id")}><select id="quick-sector" className="form-input" required value={sectorId} onChange={event => setSectorId(event.target.value)}><option value="">Selecciona un sector</option>{sectors.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select>{sectorError && <RequestState compact error={sectorError} onRetry={() => setSectorRetry(sectorRetry + 1)} />}</FormField>}
        {props.kind === 'circuit' && <FormField id="quick-service-type" label="Tipo de servicio" describedBy={error ? errorId : undefined} invalid={apiInvalidFields.includes('service_type_id')}><SearchableSelect id="quick-service-type" label="Tipo de servicio" value={serviceTypeId} onChange={setServiceTypeId} options={serviceTypes.map((item) => ({ value: String(item.id), label: item.name }))} disabled={serviceLoading || Boolean(serviceError)} placeholder="Sin asignar" emptyMessage="No hay tipos de servicio activos." noMatchMessage="Sin coincidencias." />{serviceError && <RequestState compact error={serviceError} errorTitle="" retryText="Reintentar tipos de servicio" onRetry={() => setServiceRetry(serviceRetry + 1)} />}</FormField>}
        {props.kind === 'circuit' && <CapacityFields id="quick-initial-capacity" label="Capacidad inicial (opcional)" value={capacity} unit={capacityUnit} onChange={(v, u) => { setCapacity(v); setCapacityUnit(u) }} />}
        {props.kind === 'circuit' && <FormField describedBy={[nodeError ? nodeErrorId : "", error ? errorId : ""].filter(Boolean).join(" ") || undefined} invalid={Boolean(error && !nodeId) || apiInvalidFields.includes("node_id")} id="quick-node" required label="Nodo"><div className="flex gap-2"><div className="min-w-0 flex-1"><SearchableSelect id="quick-node" required label="Nodo" value={nodeId} onChange={setNodeId} options={nodes.map((item) => ({ value: String(item.id), label: item.name }))} disabled={nodeLoading || Boolean(nodeError)} placeholder="Selecciona un nodo" emptyMessage="No hay nodos activos." noMatchMessage="No se encontraron nodos." /></div><button type="button" className="button-secondary" aria-label="Nuevo nodo" title="Nuevo nodo" onClick={() => setQuickNode(true)}>+</button></div>{nodeError && <RequestState id={nodeErrorId} compact error={nodeError} errorTitle="" retryText="Reintentar nodos" onRetry={() => setNodeRetry(nodeRetry + 1)} />}</FormField>}
      </fieldset>
      {error && <FeedbackMessage id={errorId} variant="error" className="mt-4">{error}</FeedbackMessage>}
      <div className="mt-5 flex justify-end gap-3"><button type="button" className="button-secondary" disabled={saving} onClick={props.onCancel}>Cancelar</button><button type="submit" className="button-primary" disabled={saving}>{saving ? 'Creando...' : 'Guardar'}</button></div>
    </form>
  </dialog>{quickNode && <QuickCatalogCreate kind="node" onCancel={() => setQuickNode(false)} onCreated={(node) => { setNodes((current) => [...current.filter((item) => item.id !== node.id), node]); setNodeId(String(node.id)); setQuickNode(false) }} />}</>
}
