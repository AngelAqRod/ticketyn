import { useEffect, useState } from 'react'
import { listAdminRequestTypes, listCircuits, listCustomers, listResponsibles } from '../api'
import { FormField } from './FormField'
import type { AdminRequest } from '../types/adminRequests'
import type { Circuit, Customer, NamedCatalog, Responsible } from '../types/catalog'
import { ticketynDateTimeValue } from '../lib/datetime'

export interface AdminRequestValues { request_date: string; requester_id: string; customer_id: string; circuit_id: string; type_id: string; description: string; notes: string; application_start: string; application_end: string }
export const todayInTicketyn = () => ticketynDateTimeValue().slice(0, 10)
export const blankValues = (): AdminRequestValues => ({ request_date: todayInTicketyn(), requester_id: '', customer_id: '', circuit_id: '', type_id: '', description: '', notes: '', application_start: '', application_end: '' })
export const valuesFrom = (item: AdminRequest): AdminRequestValues => ({
  request_date: item.request_date, requester_id: String(item.requester_id), customer_id: item.customer_id ? String(item.customer_id) : '',
  circuit_id: item.circuit_id ? String(item.circuit_id) : '', type_id: String(item.type_id), description: item.description, notes: item.notes ?? '',
  application_start: item.application_start ?? '', application_end: item.application_end ?? '',
})
export const payloadFrom = (v: AdminRequestValues) => ({
  request_date: v.request_date, requester_id: Number(v.requester_id), type_id: Number(v.type_id), description: v.description.trim(),
  customer_id: v.customer_id ? Number(v.customer_id) : null, circuit_id: v.circuit_id ? Number(v.circuit_id) : null, notes: v.notes.trim() || null,
  application_start: v.application_start || null, application_end: v.application_end || null,
})

export const periodInvalid = (v: AdminRequestValues) => Boolean(v.application_start && v.application_end && v.application_end < v.application_start)

/** Active catalog rows, plus the value already saved (it may have become inactive or unselectable since). */
const usable = <T extends NamedCatalog & { operational_selectable?: boolean }>(rows: T[], current: string) =>
  rows.filter(row => (row.active && row.operational_selectable !== false) || String(row.id) === current)

export function AdminRequestFields({ value, onChange, disabled }: { value: AdminRequestValues; onChange: (value: AdminRequestValues) => void; disabled?: boolean }) {
  const [people, setPeople] = useState<Responsible[]>([]), [types, setTypes] = useState<NamedCatalog[]>([]), [customers, setCustomers] = useState<Customer[]>([]), [circuits, setCircuits] = useState<Circuit[]>([])
  useEffect(() => {
    const controller = new AbortController()
    Promise.all([listResponsibles(controller.signal, true), listAdminRequestTypes(controller.signal, true), listCustomers(controller.signal, true)])
      .then(([p, t, c]) => { if (!controller.signal.aborted) { setPeople(p); setTypes(t); setCustomers(c) } }).catch(() => {})
    return () => controller.abort()
  }, [])
  useEffect(() => {
    if (!value.customer_id) { setCircuits([]); return }
    const controller = new AbortController()
    listCircuits(Number(value.customer_id), controller.signal, true).then(rows => { if (!controller.signal.aborted) setCircuits(rows) }).catch(() => {})
    return () => controller.abort()
  }, [value.customer_id])
  const set = (patch: Partial<AdminRequestValues>) => onChange({ ...value, ...patch })
  return <div className="grid gap-4 md:grid-cols-2">
    <FormField id="ar-date" label="Fecha de solicitud"><input id="ar-date" className="form-input" type="date" required disabled={disabled} value={value.request_date} onChange={e => set({ request_date: e.target.value })} /></FormField>
    <FormField id="ar-type" label="Tipo de solicitud"><select id="ar-type" className="form-input" required disabled={disabled} value={value.type_id} onChange={e => set({ type_id: e.target.value })}><option value="">Selecciona un tipo</option>{usable(types, value.type_id).map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select></FormField>
    <FormField id="ar-requester" label="Solicitante"><select id="ar-requester" className="form-input" required disabled={disabled} value={value.requester_id} onChange={e => set({ requester_id: e.target.value })}><option value="">Selecciona un responsable</option>{usable(people, value.requester_id).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select></FormField>
    <FormField id="ar-customer" label="Cliente (opcional)"><select id="ar-customer" className="form-input" disabled={disabled} value={value.customer_id} onChange={e => set({ customer_id: e.target.value, circuit_id: '' })}><option value="">Sin cliente</option>{usable(customers, value.customer_id).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></FormField>
    <FormField id="ar-circuit" label="Circuito (opcional)"><select id="ar-circuit" className="form-input" disabled={disabled || !value.customer_id} value={value.circuit_id} onChange={e => set({ circuit_id: e.target.value })}><option value="">{value.customer_id ? 'Sin circuito' : 'Selecciona primero un cliente'}</option>{circuits.map(c => <option key={c.id} value={c.id}>{c.circuit_code}</option>)}</select></FormField>
    <div className="md:col-span-2"><FormField id="ar-description" label="Descripción del requerimiento"><textarea id="ar-description" className="form-input" rows={4} required maxLength={50000} disabled={disabled} value={value.description} onChange={e => set({ description: e.target.value })} /></FormField></div>
    <fieldset className="md:col-span-2 grid gap-4 md:grid-cols-2"><legend className="mb-2 text-sm font-semibold">Período de aplicación</legend>
      <FormField id="ar-start" label="Inicio del período (opcional)"><input id="ar-start" className="form-input" type="date" disabled={disabled} value={value.application_start} onChange={e => set({ application_start: e.target.value })} /></FormField>
      <FormField id="ar-end" label="Fin del período (opcional)"><input id="ar-end" className="form-input" type="date" disabled={disabled} min={value.application_start || undefined} aria-invalid={periodInvalid(value)} value={value.application_end} onChange={e => set({ application_end: e.target.value })} /></FormField>
      <p className="md:col-span-2 text-xs text-slate-400">Fechas informativas: no cambian el estado de la solicitud.</p>
      {periodInvalid(value) && <p role="alert" className="md:col-span-2 text-sm text-red-400">El fin del período no puede ser anterior a su inicio.</p>}
    </fieldset>
    <div className="md:col-span-2"><FormField id="ar-notes" label="Observaciones (opcional)"><textarea id="ar-notes" className="form-input" rows={3} maxLength={50000} disabled={disabled} value={value.notes} onChange={e => set({ notes: e.target.value })} /></FormField></div>
  </div>
}
