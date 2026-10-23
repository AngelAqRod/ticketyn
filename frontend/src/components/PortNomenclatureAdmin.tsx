import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Pencil, Plus, Power } from 'lucide-react'
import { createPortNomenclature, listPortNomenclatures, numberFormats, updatePortNomenclature } from '../api/portNomenclatures'
import type { NomenclatureInput, NumberFormat, PortNomenclature } from '../api/portNomenclatures'
import { usePermissions } from '../auth/permissions'
import { confirmDeactivation } from '../lib/catalogActions'
import { FeedbackMessage } from './FeedbackMessage'
import { FormField } from './FormField'
import { PageHeading } from './PageHeading'
import { RequestState } from './RequestState'

const blank = (): NomenclatureInput => ({ name: '', prefix: '', formats: ['N'], active: true })
const message = (cause: unknown) => cause instanceof Error ? cause.message : 'No se pudo guardar la nomenclatura.'
export function PortNomenclatureAdmin() {
  const access = usePermissions(), sending = useRef(false)
  const [rows, setRows] = useState<PortNomenclature[]>([]), [draft, setDraft] = useState<NomenclatureInput | null>(null)
  const [editId, setEditId] = useState<number | null>(null), [loading, setLoading] = useState(true), [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null), [loadError, setLoadError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null), [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setLoadError(null)
    listPortNomenclatures(controller.signal, true).then(items => {
      if (!controller.signal.aborted) { setRows(items); setLoading(false) }
    }).catch(cause => { if (!controller.signal.aborted) { setLoadError(message(cause)); setLoading(false) } })
    return () => controller.abort()
  }, [retry])
  async function persist(input: NomenclatureInput, id: number | null) {
    if (sending.current) return
    if (!access.can(`catalogs.port_nomenclatures.${id === null ? 'create' : 'edit'}`)) return
    sending.current = true; setBusy(true); setError(null); setNotice(null)
    try {
      if (id === null) await createPortNomenclature(input)
      else await updatePortNomenclature(id, input)
      setDraft(null); setNotice('Nomenclatura guardada. Los puertos existentes conservan sus nombres y asociaciones.'); setRetry(value => value + 1)
    } catch (cause) { setError(message(cause)) }
    finally { sending.current = false; setBusy(false) }
  }
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!draft) return
    if (!draft.name.trim() || !draft.prefix.trim() || Array.from(draft.name.trim()).length > 255 || Array.from(draft.prefix).length > 200 || (draft.active && !draft.formats.length)) {
      setError('Indica nombre, prefijo y al menos un formato para una nomenclatura activa.'); return
    }
    if (!draft.active && (editId === null || rows.find(row => row.id === editId)?.active) && !confirmDeactivation()) return
    void persist({ ...draft, name: draft.name.trim() }, editId)
  }
  function toggleFormat(value: NumberFormat) {
    if (draft) setDraft({ ...draft, formats: draft.formats.includes(value) ? draft.formats.filter(item => item !== value) : numberFormats.filter(item => item === value || draft.formats.includes(item)) })
  }
  return <div className="space-y-4">
    <PageHeading title="Nomenclaturas de puertos de distribución" description="Catálogo global de prefijos y formatos. No configura velocidad, capacidad ni transceptores." theme="slate" action={access.can('catalogs.port_nomenclatures.create') && <button type="button" className="button-primary button-primary--blue rounded-full" disabled={busy} onClick={() => { setEditId(null); setDraft(blank()); setError(null) }}><Plus size={15} aria-hidden="true" />Nueva nomenclatura</button>} />
    {notice && <FeedbackMessage variant="success">{notice}</FeedbackMessage>}
    {error && <FeedbackMessage id="nomenclature-error" variant="error">{error}</FeedbackMessage>}
    {draft && <form onSubmit={submit} noValidate className="panel space-y-4 p-5" aria-label="Editar nomenclatura">
      <h2 className="text-lg font-semibold">{editId === null ? 'Nueva nomenclatura' : 'Editar nomenclatura'}</h2>
      <fieldset disabled={busy} className="grid gap-4 sm:grid-cols-2"><legend className="sr-only">Datos de nomenclatura</legend>
        <FormField id="nomenclature-name" label="Nombre descriptivo" required><input autoFocus id="nomenclature-name" className="form-input" maxLength={255} value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} /></FormField>
        <FormField id="nomenclature-prefix" label="Prefijo" required><input id="nomenclature-prefix" className="form-input font-mono" maxLength={200} value={draft.prefix} onChange={event => setDraft({ ...draft, prefix: event.target.value })} /><p className="mt-1 text-xs text-slate-300">Se conserva exactamente su escritura. El prefijo no puede cambiar si tiene puertos asociados.</p></FormField>
        <fieldset className="space-y-2"><legend className="form-label">Formatos numéricos habilitados</legend>{numberFormats.map(value => <label key={value} className="mr-4 inline-flex items-center gap-2"><input type="checkbox" checked={draft.formats.includes(value)} onChange={() => toggleFormat(value)} />{value}</label>)}</fieldset>
        <label className="inline-flex items-center gap-2"><input type="checkbox" checked={draft.active} onChange={event => setDraft({ ...draft, active: event.target.checked })} />Nomenclatura activa</label>
      </fieldset>
      <div className="flex justify-end gap-3"><button type="button" className="button-secondary rounded-full" disabled={busy} onClick={() => setDraft(null)}>Cancelar</button><button type="submit" className="button-primary button-primary--blue rounded-full" disabled={busy || !draft.name.trim() || !draft.prefix.trim() || (draft.active && draft.formats.length === 0)}>{busy ? 'Guardando...' : 'Guardar nomenclatura'}</button></div>
    </form>}
    <RequestState loading={loading} error={loadError} onRetry={() => setRetry(value => value + 1)} />
    {!loading && !loadError && (rows.length ? <div className="panel overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{['Nombre', 'Prefijo', 'Formatos', 'Estado', 'Acciones'].map(text => <th key={text} scope="col" className="p-3">{text}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.id} className="border-t border-slate-800">
      <td className="p-3">{row.name}</td><td className="p-3"><code>{row.prefix}</code></td><td className="p-3">{row.formats.join(', ') || 'Sin formatos'}</td><td className="p-3">{row.active ? 'Activa' : 'Inactiva'}</td>
      <td className="p-3">{access.can('catalogs.port_nomenclatures.edit') && <div className="flex gap-2"><button type="button" className="button-secondary" aria-label={`Editar ${row.name}`} disabled={busy} onClick={() => { setEditId(row.id); setDraft({ name: row.name, prefix: row.prefix, formats: row.formats, active: row.active }); setError(null) }}><Pencil size={14} aria-hidden="true" />Editar</button><button type="button" className="button-secondary" aria-label={`${row.active ? 'Desactivar' : 'Activar'} ${row.name}`} disabled={busy || (!row.active && !row.formats.length)} onClick={() => { if (!row.active || confirmDeactivation()) void persist({ name: row.name, prefix: row.prefix, formats: row.formats, active: !row.active }, row.id) }}><Power size={14} aria-hidden="true" />{row.active ? 'Desactivar' : 'Activar'}</button></div>}</td>
    </tr>)}</tbody></table></div> : <p className="panel p-5 text-slate-300">No hay nomenclaturas registradas. Crea la primera para habilitar la generación de puertos.</p>)}
  </div>
}
