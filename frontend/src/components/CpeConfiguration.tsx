import { useEffect, useRef, useState } from 'react'
import { getJson, patchJson } from '../api/client'
import { RequestState } from './RequestState'
import { FeedbackMessage } from './FeedbackMessage'
import { FormField } from './FormField'

export function CpeConfiguration({ circuitId }: { circuitId: number }) {
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
  if (loading || error && !editing) return <RequestState loading={loading} error={error} onRetry={() => setRetry(retry + 1)} />
  return <section className="panel p-5 min-w-0" aria-label="Configuración CPE">
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><h2 className="section-label">Configuración actual del CPE</h2>{!editing && <button ref={editButton} className="button-secondary" onClick={() => { setDraft(value ?? ''); setEditing(true); setNotice('') }}>Editar</button>}</div>
    {notice && <FeedbackMessage variant="success">{notice}</FeedbackMessage>}
    {editing ? <form onSubmit={(event) => { event.preventDefault(); void save() }}>
      <FormField id="cpe-configuration" label="Configuración actual del CPE" invalid={Boolean(error)} describedBy={error ? 'cpe-error' : undefined}><textarea ref={editor} id="cpe-configuration" className="form-input min-h-80 w-full font-mono text-xs whitespace-pre overflow-auto" wrap="off" spellCheck={false} autoCapitalize="off" autoCorrect="off" autoComplete="off" maxLength={500000} disabled={saving} value={draft} onChange={(event) => setDraft(event.target.value)} /></FormField>
      {error && <FeedbackMessage id="cpe-error" variant="error">{error}</FeedbackMessage>}
      <div className="mt-3 flex gap-2"><button className="button-primary" disabled={saving}>{saving ? 'Guardando...' : 'Guardar'}</button><button type="button" className="button-secondary" disabled={saving} onClick={() => { setEditing(false); setDraft(value ?? ''); setError(''); setTimeout(() => editButton.current?.focus(), 0) }}>Cancelar</button></div>
    </form> : value ? <pre className="max-h-[32rem] max-w-full overflow-auto whitespace-pre rounded-lg bg-slate-50 p-4 font-mono text-xs" tabIndex={0} aria-label="Configuración guardada">{value}</pre> : <p className="text-sm text-muted">Sin configuración registrada</p>}
  </section>
}
