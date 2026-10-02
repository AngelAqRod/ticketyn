import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { createCircuit, createCustomer } from '../api'
import type { Circuit, Customer } from '../types/catalog'
import { FormField } from './FormField'

type Props = {
  onCancel: () => void
} & ({ kind: 'customer'; onCreated: (customer: Customer) => void } | {
  kind: 'circuit'; customer: Customer; onCreated: (circuit: Circuit) => void
})

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
  const title = customerMode ? 'Nuevo cliente' : 'Nuevo circuito'

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
    if (!code.trim() || !text.trim()) { setError('Completa los campos obligatorios.'); return }
    sending.current = true
    setSaving(true)
    const request = new AbortController()
    controller.current = request
    try {
      if (props.kind === 'customer') {
        const customer = await createCustomer({ customer_code: code.trim(), name: text.trim(), active: true }, request.signal)
        if (!request.signal.aborted) props.onCreated(customer)
      } else {
        const circuit = await createCircuit({ customer_id: props.customer.id, circuit_code: code.trim(), description: text.trim(), active: true }, request.signal)
        if (!request.signal.aborted) props.onCreated(circuit)
      }
    } catch (failure) {
      if (!request.signal.aborted) setError(failure instanceof Error ? failure.message : 'No se pudo crear el registro.')
    } finally {
      sending.current = false
      if (!request.signal.aborted) setSaving(false)
    }
  }

  return <dialog ref={dialog} aria-labelledby="quick-create-title" aria-describedby="quick-create-description" aria-modal="true"
    className="fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-md overflow-y-auto rounded-md border border-slate-200 bg-white p-5 text-slate-800 shadow-xl backdrop:bg-slate-900/30"
    onCancel={(event) => { event.preventDefault(); if (!sending.current) props.onCancel() }}>
    <h2 id="quick-create-title" className="text-xl font-semibold">{title}</h2>
    <p id="quick-create-description" className="mb-4 mt-2 text-sm text-slate-500">Se creará un registro activo. El ticket se guarda por separado.</p>
    {props.kind === 'circuit' && <p className="mb-4 text-sm"><span className="font-medium">Cliente: </span>{props.customer.customer_code} — {props.customer.name}</p>}
    <form aria-label={`Crear ${customerMode ? 'cliente' : 'circuito'} rápido`} onSubmit={submit} noValidate>
      <fieldset disabled={saving} className="space-y-3"><legend className="sr-only">Datos del registro</legend>
        <FormField id="quick-code" label={customerMode ? 'Código de cliente' : 'Código de circuito'} required><input ref={codeInput} id="quick-code" className="form-input" required value={code} onChange={(event) => setCode(event.target.value)} /></FormField>
        <FormField id="quick-text" label={customerMode ? 'Nombre' : 'Descripción'} required><input id="quick-text" className="form-input" required value={text} onChange={(event) => setText(event.target.value)} /></FormField>
      </fieldset>
      {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p>}
      <div className="mt-5 flex justify-end gap-3"><button type="button" className="button-secondary" disabled={saving} onClick={props.onCancel}>Cancelar</button><button type="submit" className="button-primary" disabled={saving}>{saving ? 'Creando...' : 'Guardar'}</button></div>
    </form>
  </dialog>
}
