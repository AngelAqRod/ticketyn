import { MapPinned } from 'lucide-react'
import { formatGps, mapsUrl } from '../lib/gps'
import type { Circuit } from '../types/catalog'

type Site = Pick<Circuit, 'address' | 'latitude' | 'longitude' | 'additional_notes'>
const term = 'text-slate-400 font-mono uppercase tracking-wider text-[11px]'
const detail = 'mt-1 [overflow-wrap:anywhere] text-white font-medium text-sm'
/** Read-only site data of a circuit. Missing values say so instead of inventing text. */
export function CircuitLocationData({ site, title, showNotes = true }: { site: Site | null | undefined; title?: string; showNotes?: boolean }) {
  const link = mapsUrl(site?.latitude, site?.longitude)
  return <section aria-label={title ?? 'Ubicación y notas'}>{title && <h3 className="form-label">{title}</h3>}
    <dl className="grid gap-x-6 gap-y-3.5 sm:grid-cols-2 text-xs">
      <div className="min-w-0 sm:col-span-2"><dt className={term}>Dirección</dt><dd className={detail}>{site?.address || 'No disponible'}</dd></div>
      <div className="min-w-0"><dt className={term}>Punto GPS</dt><dd className={detail}>{link ? <><span className="block font-mono">{formatGps(site?.latitude, site?.longitude)}</span><a className="mt-1.5 inline-flex items-center gap-1.5 text-sky-400 hover:text-sky-300 underline" href={link} target="_blank" rel="noopener noreferrer"><MapPinned size={14} aria-hidden="true" className="shrink-0" />Ver en Google Maps</a></> : 'No disponible'}</dd></div>
      {showNotes && <div className="min-w-0 sm:col-span-2"><dt className={term}>Notas adicionales</dt><dd className={`${detail} whitespace-pre-wrap`}>{site?.additional_notes || 'No disponible'}</dd></div>}
    </dl>
  </section>
}
