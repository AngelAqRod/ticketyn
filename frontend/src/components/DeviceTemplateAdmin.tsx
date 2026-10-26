import { useEffect, useId, useRef, useState } from 'react'
import { listDeviceTemplates, previewDeviceTemplate, saveDeviceTemplate, type DeviceTemplate, type TemplateGroup, type TemplateInput, type TemplatePreview } from '../api/deviceTemplates'
import { listPortNomenclatures, type NumberFormat, type PortNomenclature } from '../api/portNomenclatures'
import { usePermissions } from '../auth/permissions'
import { TemplateGroupsPreview } from './DeviceTemplateChoice'
import { FeedbackMessage } from './FeedbackMessage'
import { FormField } from './FormField'
import { SearchableSelect } from './SearchableSelect'
import { RequestState } from './RequestState'
import { PageHeading } from './PageHeading'

const scope = 'catalogs.distribution_device_templates'
const emptyGroup = (): TemplateGroup => ({ nomenclature_id: 0, numbering_format: 'N', positions: [], start: 1, end: 1 })
const initial = (): TemplateInput => ({ name: '', manufacturer: null, description: null, active: true, groups: [emptyGroup()] })
const errorText = (error: unknown) => error instanceof Error ? error.message : 'No se pudo completar la operación.'

export function DeviceTemplateAdmin() {
  const access = usePermissions(), id = useId(), sending = useRef(false)
  const [rows, setRows] = useState<DeviceTemplate[]>([]), [catalogs, setCatalogs] = useState<PortNomenclature[]>([])
  const [editing, setEditing] = useState<number | null | undefined>(undefined), [draft, setDraft] = useState<TemplateInput>(initial)
  const [preview, setPreview] = useState<{ key: string; value: TemplatePreview } | null>(null)
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [loading, setLoading] = useState(true)
  const [previewError, setPreviewError] = useState(''), [busy, setBusy] = useState(false), [retry, setRetry] = useState(0)
  const allowed = editing === null ? access.can(`${scope}.create`) : access.can(`${scope}.edit`)
  const key = JSON.stringify(draft)
  const total = draft.groups.reduce((sum, group) => sum + group.end - group.start + 1, 0)
  const valid = Boolean(draft.name.trim()) && draft.groups.length > 0 && draft.groups.length <= 16 && total <= 256 && draft.groups.every(g =>
    g.nomenclature_id > 0 && g.positions.length === g.numbering_format.split('/').length - 1 &&
    [...g.positions, g.start, g.end].every(n => Number.isSafeInteger(n) && n >= 0) && g.end >= g.start)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    Promise.all([listDeviceTemplates(controller.signal, true), listPortNomenclatures(controller.signal, true)])
      .then(([items, names]) => { if (!controller.signal.aborted) { setRows(items); setCatalogs(names) } })
      .catch(error => { if (!controller.signal.aborted) setError(errorText(error)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [retry])
  useEffect(() => {
    setPreview(null); setPreviewError('')
    if (editing === undefined || !allowed || !valid) return
    const controller = new AbortController()
    const timer = setTimeout(() => {
      previewDeviceTemplate(draft, editing ?? undefined, controller.signal).then(value => {
        if (!controller.signal.aborted) setPreview({ key, value })
      }).catch(error => { if (!controller.signal.aborted) setPreviewError(errorText(error)) })
    }, 250)
    return () => { clearTimeout(timer); controller.abort() }
  }, [key, editing, allowed, valid, retry])
  function groupChange(index: number, change: Partial<TemplateGroup>) {
    setDraft(current => ({ ...current, groups: current.groups.map((group, i) => i === index ? { ...group, ...change } : group) }))
  }
  function open(item?: DeviceTemplate) {
    setEditing(item?.id ?? null); setError(''); setNotice('')
    setDraft(item ? { name: item.name, manufacturer: item.manufacturer, description: item.description, active: item.active,
      groups: item.groups.map(({ nomenclature_id, numbering_format, positions, start, end }) => ({ nomenclature_id, numbering_format, positions, start, end })) } : initial())
  }
  async function save(event: React.FormEvent) {
    event.preventDefault()
    if (sending.current || !allowed || !valid || preview?.key !== key) return
    sending.current = true; setBusy(true); setError('')
    try {
      await saveDeviceTemplate({ ...draft, preview_token: preview.value.preview_token }, editing ?? undefined)
      setEditing(undefined); setNotice('Plantilla guardada. Los equipos existentes permanecen intactos.'); setRetry(n => n + 1)
    } catch (error) { setError(errorText(error)); setRetry(n => n + 1) }
    finally { sending.current = false; setBusy(false) }
  }
  return <section className="panel space-y-4 p-4">
    <PageHeading title="Plantillas de equipos" description="Definiciones reutilizables; no sincronizan equipos ya creados." theme="slate"
      action={access.can(`${scope}.create`) && editing === undefined && <button type="button" className="button-primary button-primary--blue rounded-full" onClick={() => open()}>Nueva plantilla</button>} />
    {notice && <FeedbackMessage variant="success">{notice}</FeedbackMessage>}
    {error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}
    <RequestState compact loading={loading} error={loading ? null : (rows.length ? null : error)} onRetry={() => setRetry(n => n + 1)} />
    {editing !== undefined && <form aria-label="Editar plantilla de equipo" onSubmit={save} className="space-y-4">
      <fieldset disabled={busy || !allowed} className="space-y-4"><legend className="font-semibold">Datos generales</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <FormField id={`${id}-name`} label="Nombre / modelo" required><input className="form-input" id={`${id}-name`} required maxLength={255} value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })} /></FormField>
          <FormField id={`${id}-manufacturer`} label="Fabricante (opcional)"><input className="form-input" id={`${id}-manufacturer`} maxLength={255} value={draft.manufacturer ?? ''} onChange={e => setDraft({ ...draft, manufacturer: e.target.value || null })} /></FormField>
        </div>
        <FormField id={`${id}-description`} label="Descripción (opcional)"><textarea className="form-input" id={`${id}-description`} maxLength={10000} value={draft.description ?? ''} onChange={e => setDraft({ ...draft, description: e.target.value || null })} /></FormField>
        <label className="flex gap-2"><input type="checkbox" checked={draft.active} onChange={e => setDraft({ ...draft, active: e.target.checked })} /> Activa</label>
        <h3 className="font-semibold">Grupos de interfaces</h3>
        {draft.groups.map((group, index) => {
          const selected = catalogs.find(c => c.id === group.nomenclature_id)
          const formats = [...new Set([...(selected?.formats ?? []), group.numbering_format])]
          return <fieldset key={index} className="space-y-3 rounded-xl border border-purple-500/25 p-3"><legend className="px-1">Grupo {index + 1}</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <FormField id={`${id}-catalog-${index}`} label="Nomenclatura" required><SearchableSelect id={`${id}-catalog-${index}`} label={`Nomenclatura del grupo ${index + 1}`} value={String(group.nomenclature_id || '')}
                options={catalogs.filter(c => c.active || c.id === group.nomenclature_id).map(c => ({ value: String(c.id), label: `${c.name} (${c.prefix})${c.active ? '' : ' · Inactiva'}`, disabled: !c.active }))}
                onChange={value => { const catalog = catalogs.find(c => c.id === Number(value)); const format = catalog?.formats[0] ?? 'N'; groupChange(index, { nomenclature_id: Number(value), numbering_format: format, positions: Array(format.split('/').length - 1).fill(0) }) }} emptyMessage="No hay nomenclaturas activas." noMatchMessage="Sin coincidencias." placeholder="Selecciona una nomenclatura" /></FormField>
              <FormField id={`${id}-format-${index}`} label="Formato" required><select className="form-input" id={`${id}-format-${index}`} disabled={!selected} value={group.numbering_format} onChange={e => { const format = e.target.value as NumberFormat; groupChange(index, { numbering_format: format, positions: Array(format.split('/').length - 1).fill(0) }) }}>
                {formats.map(format => <option key={format} value={format} disabled={!selected?.formats.includes(format)}>{format}</option>)}
              </select></FormField>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {group.positions.map((number, n) => <FormField key={n} id={`${id}-${index}-pos-${n}`} label={`Posición ${n + 1}`} required><input id={`${id}-${index}-pos-${n}`} className="form-input" type="number" min={0} step={1} required value={Number.isFinite(number) ? number : ''} onChange={e => groupChange(index, { positions: group.positions.map((p, i) => i === n ? e.target.valueAsNumber : p) })} /></FormField>)}
              {(['start', 'end'] as const).map(field => <FormField key={field} id={`${id}-${index}-${field}`} label={field === 'start' ? 'Número inicial' : 'Número final'} required><input id={`${id}-${index}-${field}`} className="form-input" type="number" min={0} step={1} required value={Number.isFinite(group[field]) ? group[field] : ''} onChange={e => groupChange(index, { [field]: e.target.valueAsNumber })} /></FormField>)}
            </div>
            <div className="flex items-center justify-between gap-2"><span className="text-sm">{Number.isFinite(group.end - group.start) && group.end >= group.start ? group.end - group.start + 1 : 0} puertos</span>
              <button className="button-secondary" type="button" disabled={draft.groups.length === 1} onClick={() => setDraft({ ...draft, groups: draft.groups.filter((_, i) => i !== index) })}>Quitar grupo {index + 1}</button></div>
          </fieldset>
        })}
        <button type="button" className="button-secondary" disabled={draft.groups.length >= 16} onClick={() => setDraft({ ...draft, groups: [...draft.groups, emptyGroup()] })}>Agregar grupo</button>
        <p className="text-sm">Total: {Number.isFinite(total) ? total : 0} puertos · Máximo 16 grupos y 256 puertos en toda la plantilla.</p>
        {previewError && <FeedbackMessage variant="error">{previewError}</FeedbackMessage>}
        {preview?.key === key && <TemplateGroupsPreview preview={preview.value} />}
        {!valid && <p role="status" className="text-sm text-amber-300">Completa los campos y revisa los rangos y el límite total antes de guardar.</p>}
      </fieldset>
      <div className="flex justify-end gap-3"><button type="button" className="button-secondary" disabled={busy} onClick={() => setEditing(undefined)}>Cancelar</button>
        <button className="button-primary button-primary--blue rounded-full" disabled={busy || !allowed || !valid || preview?.key !== key}>{busy ? 'Guardando…' : 'Guardar plantilla'}</button></div>
    </form>}
    <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr>{['Nombre / modelo', 'Fabricante', 'Grupos', 'Puertos', 'Estado', 'Acciones'].map(label => <th key={label} scope="col" className="p-2 text-left">{label}</th>)}</tr></thead>
      <tbody>{rows.map(item => <tr key={item.id} className="border-t border-slate-700/50"><td className="p-2">{item.name}{!item.usable && item.active && <p className="text-xs text-amber-300">Revisar nomenclaturas</p>}</td><td className="p-2">{item.manufacturer || 'No registrado'}</td><td className="p-2">{item.groups.length}</td><td className="p-2">{item.total_ports}</td><td className="p-2">{item.active ? 'Activa' : 'Inactiva'}</td><td className="p-2">{access.can(`${scope}.edit`) ? <button className="button-secondary" onClick={() => open(item)}>Editar {item.name}</button> : <details><summary>Consultar</summary><TemplateGroupsPreview preview={item} /></details>}</td></tr>)}</tbody>
    </table>{!loading && !error && !rows.length && <p className="p-3 text-sm text-slate-400">No hay plantillas registradas.</p>}</div>
  </section>
}
