import { useEffect, useRef } from 'react'
import type { Circuit } from '../types/catalog'
import { CatalogAdmin } from './CatalogAdmin'

/** Reuses the circuit editor from the list, including catalog validation. */
export function CircuitEditModal({ circuit, onSaved, onCancel }: { circuit: Circuit; onSaved: (circuit: Circuit) => void; onCancel: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null), busy = useRef(false)
  useEffect(() => {
    const element = dialog.current!, previous = document.activeElement
    element.showModal()
    return () => { element.close(); if (previous instanceof HTMLElement && previous.isConnected) previous.focus() }
  }, [])
  return <dialog ref={dialog} className="quick-dialog noc-modal fixed inset-0 m-auto max-h-[90vh] w-[calc(100%_-_2rem)] max-w-2xl overflow-y-auto bg-white p-5 text-ink backdrop:bg-slate-900/30" aria-label={`Editar circuito ${circuit.circuit_code}`} onCancel={(event) => { event.preventDefault(); if (!busy.current) onCancel() }}>
    <CatalogAdmin kind="circuits" circuitEditor={{ item: circuit, onSaved, onCancel, onBusyChange: (value) => { busy.current = value } }} />
  </dialog>
}
