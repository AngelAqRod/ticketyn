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

  return <dialog ref={dialog} className="quick-dialog fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto bg-[#0b1426] text-white border border-red-500/30 rounded-2xl shadow-2xl backdrop:bg-slate-950/70 p-0" aria-modal="true" aria-labelledby="delete-catalog-title" aria-describedby="delete-catalog-record delete-catalog-description" onCancel={(event) => { event.preventDefault(); if (!sending.current) onCancel() }}>
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-2.5 border-b border-red-500/20 pb-3">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-red-500/10 border border-red-500/30 text-red-400" aria-hidden="true">
          <Trash2 size={15} />
        </span>
        <h2 id="delete-catalog-title" className="text-base font-bold font-mono text-white uppercase tracking-wider">Eliminar {singular}</h2>
      </div>
      <div id="delete-catalog-record" className="p-3.5 rounded-xl bg-[#070d1a] border border-slate-800">
        <p className="break-words font-mono font-bold text-white text-base">{code}</p>
        <p className="mt-1 break-words text-sm text-slate-300">{description}</p>
      </div>
      <p id="delete-catalog-description" className="text-xs text-slate-400 font-mono leading-relaxed">Esta acción es definitiva. Solo se eliminará el {singular} si no tiene registros asociados. Para conservarlo, puedes desactivarlo.</p>
      {error && <FeedbackMessage variant="error" className="mt-3">{error}</FeedbackMessage>}
      <div className="mt-5 flex flex-wrap justify-end gap-2.5 pt-2">
        <button ref={cancel} type="button" className="button-secondary rounded-full shadow-xs" disabled={busy} onClick={onCancel}>Cancelar</button>
        <button type="button" className="button-danger rounded-full shadow-sm" disabled={busy} onClick={() => void remove()}><Trash2 size={14} aria-hidden="true" />{busy ? 'Eliminando...' : 'Eliminar definitivamente'}</button>
      </div>
    </div>
  </dialog>
}
