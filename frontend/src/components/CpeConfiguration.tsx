import { Can, usePermissions } from '../auth/permissions'
import { useEffect, useRef, useState } from 'react'
import { Cpu, Pencil } from 'lucide-react'
import { getJson, patchJson } from '../api/client'
import { RequestState } from './RequestState'
import { FeedbackMessage } from './FeedbackMessage'
import { FormField } from './FormField'

export function CpeConfiguration({ circuitId }: { circuitId: number }) {
  const editable=usePermissions().can("cpe.edit")
  const [value, setValue] = useState<string | null>(null), [draft, setDraft] = useState(''), [editing, setEditing] = useState(false), [loading, setLoading] = useState(true), [saving, setSaving] = useState(false), [error, setError] = useState(''), [retry, setRetry] = useState(0), [notice, setNotice] = useState('')
  const sending = useRef(false), editButton = useRef<HTMLButtonElement>(null), editor = useRef<HTMLTextAreaElement>(null)
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(''); setEditing(false)
    getJson<{ configuration: string | null }>(`/api/circuits/${circuitId}/cpe-configuration`, controller.signal).then((data) => { if (!controller.signal.aborted) { setValue(data.configuration); setLoading(false) } }).catch((failure: unknown) => { if (!controller.signal.aborted) { setError(failure instanceof Error ? failure.message : 'No se pudo cargar la configuración.'); setLoading(false) } })
    return () => controller.abort()
  }, [circuitId, retry])
  useEffect(() => { if (editing) editor.current?.focus() }, [editing])
  async function save() {
    if (sending.current) return
    sending.current = true; setSaving(true); setError(''); setNotice('')
    try {
      const data = await patchJson<{ configuration: string | null }>(`/api/circuits/${circuitId}/cpe-configuration`, { configuration: draft })
      setValue(data.configuration); setEditing(false); setNotice('Configuración guardada correctamente.'); setTimeout(() => editButton.current?.focus(), 0)
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'No se pudo guardar la configuración.') }
    finally { sending.current = false; setSaving(false) }
  }
  if (loading || error && !editing) return <RequestState className="p-8 rounded-2xl bg-[#0b1426] border border-slate-800/80 shadow-xl text-center" loading={loading} error={error} onRetry={() => setRetry(retry + 1)} />
  return <section className="panel p-6 rounded-2xl bg-[#0b1426] border border-sky-500/20 shadow-xl min-w-0" aria-label="Configuración CPE">
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-sky-500/15 pb-3">
      <div className="flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 text-xs" aria-hidden="true">
          <Cpu size={14} />
        </span>
        <h2 className="text-xs font-bold font-mono text-white uppercase tracking-wider">
          Configuración actual del CPE
        </h2>
      </div>
      {!editing && editable && (
        <button ref={editButton} className="button-secondary rounded-full shadow-xs text-xs" onClick={() => { setDraft(value ?? ''); setEditing(true); setNotice('') }}>
          <Pencil size={13} aria-hidden="true" />
          Editar
        </button>
      )}
    </div>
    {notice && <FeedbackMessage variant="success" className="mb-3">{notice}</FeedbackMessage>}
    {editing && editable ? <form onSubmit={(event) => { event.preventDefault(); void save() }}>
      <FormField id="cpe-configuration" label="Configuración actual del CPE" invalid={Boolean(error)} describedBy={error ? 'cpe-error' : undefined}>
        <textarea ref={editor} id="cpe-configuration" className="form-input min-h-80 w-full font-mono text-xs whitespace-pre overflow-auto rounded-xl bg-[#070d1a] border-slate-800 text-sky-200" wrap="off" spellCheck={false} autoCapitalize="off" autoCorrect="off" autoComplete="off" maxLength={500000} disabled={saving} value={draft} onChange={(event) => setDraft(event.target.value)} />
      </FormField>
      {error && <FeedbackMessage id="cpe-error" variant="error" className="mt-3">{error}</FeedbackMessage>}
      <div className="mt-4 flex gap-2.5">
        <button className="button-primary button-primary--blue rounded-full shadow-sm" disabled={saving}>{saving ? 'Guardando...' : 'Guardar'}</button>
        <button type="button" className="button-secondary rounded-full shadow-xs" disabled={saving} onClick={() => { setEditing(false); setDraft(value ?? ''); setError(''); setTimeout(() => editButton.current?.focus(), 0) }}>Cancelar</button>
      </div>
    </form> : value ? <pre className="max-h-[32rem] max-w-full overflow-auto whitespace-pre rounded-xl bg-[#070d1a] border border-slate-800 p-4 font-mono text-xs text-sky-200" tabIndex={0} aria-label="Configuración guardada">{value}</pre> : <p className="text-sm text-slate-400 font-mono">Sin configuración registrada</p>}
  </section>
}
