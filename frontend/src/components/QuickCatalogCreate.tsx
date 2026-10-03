import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { createCircuit, createCustomer, createNode, listNodes } from '../api'
import type { Circuit, Customer, Node } from '../types/catalog'
import { SearchableSelect } from './SearchableSelect'
import { FormField } from './FormField'

type Props = {
  onCancel: () => void
} & ({ kind: 'customer'; onCreated: (customer: Customer) => void } | {
  kind: 'circuit'; customer: Customer; onCreated: (circuit: Circuit) => void
} | { kind: 'node'; onCreated: (node: Node) => void })

export function QuickCatalogCreate(props: Props) {
  const [code, setCode] = useState('')
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const sending = useRef(false)
  const dialog = useRef<HTMLDialogElement>(null)
  const codeInput = useRef<HTMLInputElement>(null)
  const controller = useRef<AbortController | null>(null)
  const customerMode = props.kind === 'customer'
  const nodeMode = props.kind === 'node'
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
    setError(null)
    if ((!nodeMode && !code.trim()) || !text.trim()) { setError('Completa los campos obligatorios.'); return }
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
        const circuit = await createCircuit({ customer_id: props.customer.id, circuit_code: code.trim(), description: text.trim(), active: true, node_id: nodeId ? Number(nodeId) : null }, request.signal)
        if (!request.signal.aborted) props.onCreated(circuit)
      }
    } catch (failure) {
      if (!request.signal.aborted) setError(failure instanceof Error ? failure.message : 'No se pudo crear el registro.')
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
    <form aria-label={`Crear ${nodeMode ? 'nodo' : customerMode ? 'cliente' : 'circuito'} rápido`} onSubmit={submit} noValidate>
      <fieldset disabled={saving} className="space-y-3"><legend className="sr-only">Datos del registro</legend>
        {!nodeMode && <FormField id="quick-code" label={customerMode ? 'Código de cliente' : 'Código de circuito'} required><input ref={codeInput} id="quick-code" className="form-input" required value={code} onChange={(event) => setCode(event.target.value)} /></FormField>}
        <FormField id={`quick-text-${props.kind}`} label={customerMode || nodeMode ? 'Nombre' : 'Descripción'} required><input ref={nodeMode ? codeInput : undefined} id={`quick-text-${props.kind}`} className="form-input" required value={text} onChange={(event) => setText(event.target.value)} /></FormField>
        {props.kind === 'circuit' && <FormField id="quick-node" label="Nodo de distribución"><div className="flex gap-2"><div className="min-w-0 flex-1"><SearchableSelect id="quick-node" label="Nodo de distribución" value={nodeId} onChange={setNodeId} options={nodes.map((item) => ({ value: String(item.id), label: item.name }))} disabled={nodeLoading || Boolean(nodeError)} placeholder="Sin asignar" emptyMessage="No hay nodos activos." noMatchMessage="No se encontraron nodos." /></div><button type="button" className="button-secondary" aria-label="Nuevo nodo" title="Nuevo nodo" onClick={() => setQuickNode(true)}>+</button></div>{nodeError && <p role="alert">{nodeError} <button type="button" onClick={() => setNodeRetry(nodeRetry + 1)}>Reintentar nodos</button></p>}</FormField>}
      </fieldset>
      {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      <div className="mt-5 flex justify-end gap-3"><button type="button" className="button-secondary" disabled={saving} onClick={props.onCancel}>Cancelar</button><button type="submit" className="button-primary" disabled={saving}>{saving ? 'Creando...' : 'Guardar'}</button></div>
    </form>
  </dialog>{quickNode && <QuickCatalogCreate kind="node" onCancel={() => setQuickNode(false)} onCreated={(node) => { setNodes((current) => [...current.filter((item) => item.id !== node.id), node]); setNodeId(String(node.id)); setQuickNode(false) }} />}</>
}
