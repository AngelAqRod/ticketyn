import { useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { Trash2 } from 'lucide-react'
import { ApiError } from '../api/client'
import { deleteCustomer, deleteCircuit } from '../api'
import type { Circuit, Customer } from '../types/catalog'
import { FeedbackMessage } from './FeedbackMessage'

export function CatalogDeleteConfirmation({ item, onCancel, onDeleted, onBusyChange, fallbackFocus }: {
  item: Customer | Circuit; onCancel: () => void; onDeleted: () => void; onBusyChange: (busy: boolean) => void; fallbackFocus: RefObject<HTMLButtonElement | null>
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const cancel = useRef<HTMLButtonElement>(null)
  const sending = useRef(false)
  const controller = useRef<AbortController | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const customer = 'customer_code' in item
  const singular = customer ? 'cliente' : 'circuito'
  const code = customer ? item.customer_code : item.circuit_code
  const description = customer ? item.name : item.description

  useEffect(() => {
    const element = dialog.current!
    const previousFocus = document.activeElement
    element.showModal()
    cancel.current?.focus()
    return () => {
      controller.current?.abort()
      element.close()
      if (previousFocus instanceof HTMLElement && previousFocus !== document.body && previousFocus.isConnected) previousFocus.focus()
      else fallbackFocus.current?.focus()
    }
  }, [])

  async function remove() {
    if (sending.current) return
    sending.current = true
    setBusy(true); onBusyChange(true); setError(null)
    const request = new AbortController()
    controller.current = request
    try {
      await (customer ? deleteCustomer : deleteCircuit)(item.id, request.signal)
      if (!request.signal.aborted) onDeleted()
    } catch (failure) {
      if (!request.signal.aborted) {
        const detail = failure instanceof Error ? failure.message : 'No se pudo eliminar el registro.'
        setError(failure instanceof ApiError && failure.status === 409 && !detail.includes('desactiv')
          ? `${detail} Puedes desactivar el registro en lugar de eliminarlo.` : detail)
      }
    } finally {
      sending.current = false
      if (!request.signal.aborted) { setBusy(false); onBusyChange(false) }
    }
  }

  return <dialog ref={dialog} className="quick-dialog fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto bg-white text-ink backdrop:bg-slate-900/30" aria-modal="true" aria-labelledby="delete-catalog-title" aria-describedby="delete-catalog-record delete-catalog-description" onCancel={(event) => { event.preventDefault(); if (!sending.current) onCancel() }}>
    <div className="p-5">
      <h2 id="delete-catalog-title" className="text-lg font-semibold">Eliminar {singular}</h2>
      <div id="delete-catalog-record"><p className="mt-3 break-words font-semibold">{code}</p>
      <p className="mt-1 break-words text-sm text-slate-600">{description}</p></div>
      <p id="delete-catalog-description" className="mt-3 text-sm text-slate-600">Esta acción es definitiva. Solo se eliminará el {singular} si no tiene registros asociados. Para conservarlo, puedes desactivarlo.</p>
      {error && <FeedbackMessage variant="error" className="mt-3">{error}</FeedbackMessage>}
      <div className="mt-5 flex flex-wrap justify-end gap-2">
        <button ref={cancel} type="button" className="button-secondary" disabled={busy} onClick={onCancel}>Cancelar</button>
        <button type="button" className="button-danger" disabled={busy} onClick={() => void remove()}><Trash2 size={15} aria-hidden="true" />{busy ? 'Eliminando...' : 'Eliminar definitivamente'}</button>
      </div>
    </div>
  </dialog>
}
