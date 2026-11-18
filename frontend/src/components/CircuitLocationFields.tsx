import { FormField } from './FormField'
import { GPS_EXAMPLE, formatGps, parseGps } from '../lib/gps'
import type { Circuit } from '../types/catalog'

/** Optional site data of a circuit. One shared piece for every circuit form (list, edit modal, quick create from Tickets and Orders). */
export type LocationDraft = { address: string; gps: string; notes: string }
export const blankLocation = (): LocationDraft => ({ address: '', gps: '', notes: '' })
export const locationDraft = (circuit?: Pick<Circuit, 'address' | 'latitude' | 'longitude' | 'additional_notes'> | null): LocationDraft => ({ address: circuit?.address ?? '', gps: formatGps(circuit?.latitude, circuit?.longitude), notes: circuit?.additional_notes ?? '' })
/** Empty fields become null so a stored value can be cleared. Throws the GPS message when the point is invalid. */
export function locationPayload(draft: LocationDraft) {
  const point = parseGps(draft.gps)
  return { address: draft.address.trim() || null, latitude: point?.latitude ?? null, longitude: point?.longitude ?? null, additional_notes: draft.notes.trim() || null }
}
export function CircuitLocationFields({ idPrefix, value, onChange, disabled = false, describedBy, invalidGps = false }: { idPrefix: string; value: LocationDraft; onChange: (value: LocationDraft) => void; disabled?: boolean; describedBy?: string; invalidGps?: boolean }) {
  const set = (patch: Partial<LocationDraft>) => onChange({ ...value, ...patch })
  return <>
    <div className="sm:col-span-2"><FormField id={`${idPrefix}-address`} label="Dirección (opcional)"><input id={`${idPrefix}-address`} className="form-input" maxLength={500} disabled={disabled} value={value.address} onChange={event => set({ address: event.target.value })} /></FormField></div>
    <FormField id={`${idPrefix}-gps`} label="Punto GPS (opcional)" describedBy={[`${idPrefix}-gps-hint`, describedBy].filter(Boolean).join(' ')} invalid={invalidGps}>
      <input id={`${idPrefix}-gps`} className="form-input" inputMode="decimal" autoComplete="off" spellCheck={false} placeholder={GPS_EXAMPLE} disabled={disabled} value={value.gps} onChange={event => set({ gps: event.target.value })} />
      <p id={`${idPrefix}-gps-hint`} className="mt-1 text-xs text-slate-400">Pega «latitud, longitud» desde Google Maps.</p>
    </FormField>
    <div className="sm:col-span-2"><FormField id={`${idPrefix}-notes`} label="Notas adicionales (opcional)"><textarea id={`${idPrefix}-notes`} className="form-input" rows={3} maxLength={5000} disabled={disabled} value={value.notes} onChange={event => set({ notes: event.target.value })} /></FormField></div>
  </>
}
