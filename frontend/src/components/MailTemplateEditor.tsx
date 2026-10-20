import { useEffect, useRef, useState } from 'react'
import { getMailTemplate, saveMailTemplate, previewMailTemplate } from '../api/mailNotifications'
import type { BodyBlock, MailField, MailPreview, MailTemplate, SubjectBlock } from '../api/mailNotifications'
import { listOperations } from '../api/fms'
import type { Operation } from '../types/fms'

export function MailTemplateEditor({ eventKey, fields }: { eventKey: string; fields: MailField[] }) {
  const [template, setTemplate] = useState<MailTemplate | null>(null)
  const [error, setError] = useState(''), [message, setMessage] = useState(''), [retry, setRetry] = useState(0)
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(true)
  const [activations, setActivations] = useState<Operation[]>([]), [offset, setOffset] = useState(0), [activationRetry, setActivationRetry] = useState(0)
  const [listLoading, setListLoading] = useState(false), [listError, setListError] = useState('')
  const [activationId, setActivationId] = useState(''), [preview, setPreview] = useState<MailPreview | null>(null)
  const sending = useRef(false), alive = useRef(true)
  const prefix = `mail-template-${eventKey}`
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('')
    getMailTemplate(eventKey, controller.signal).then(value => { if (!controller.signal.aborted) { setTemplate(value); setLoading(false) } }).catch(failure => { if (!controller.signal.aborted) { setError(failure instanceof Error ? failure.message : 'No se pudo cargar la plantilla.'); setLoading(false) } })
    return () => controller.abort()
  }, [eventKey, retry])
  useEffect(() => {
    const controller = new AbortController(); setListLoading(true); setListError(''); setActivationId(''); setPreview(null)
    listOperations('activations', new URLSearchParams({ limit: '50', offset: String(offset) }), controller.signal).then(rows => { if (!controller.signal.aborted) { setActivations(rows); setListLoading(false) } }).catch(failure => { if (!controller.signal.aborted) { setListError(failure instanceof Error ? failure.message : 'No se pudieron consultar las activaciones.'); setListLoading(false) } })
    return () => controller.abort()
  }, [offset, activationRetry])
  function change(next: MailTemplate) { setTemplate(next); setPreview(null); setMessage(''); setError('') }
  function subject(index: number, block: SubjectBlock) { if (template) change({ ...template, subject: template.subject.map((item, i) => i === index ? block : item) }) }
  function body(index: number, block: BodyBlock) { if (template) change({ ...template, body: template.body.map((item, i) => i === index ? block : item) }) }
  function reorder(section: 'subject' | 'body', index: number, delta: number) {
    if (!template) return
    if (section === 'subject') { const blocks = [...template.subject]; [blocks[index], blocks[index + delta]] = [blocks[index + delta], blocks[index]]; change({ ...template, subject: blocks }) }
    else { const blocks = [...template.body]; [blocks[index], blocks[index + delta]] = [blocks[index + delta], blocks[index]]; change({ ...template, body: blocks }) }
  }
  async function execute(action: 'save' | 'preview') {
    if (!template || sending.current) return
    sending.current = true; setBusy(true); setError(''); setMessage(''); setPreview(null)
    try {
      if (action === 'save') { const saved = await saveMailTemplate(eventKey, template); if (alive.current) { setTemplate(saved); setMessage('Plantilla guardada.'); } }
      else { const value = await previewMailTemplate(eventKey, Number(activationId), template); if (alive.current) setPreview(value) }
    } catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : 'No se pudo procesar la plantilla.') }
    finally { sending.current = false; if (alive.current) setBusy(false) }
  }
  function fieldOptions() { return <><option value="">Selecciona un campo</option>{[...new Set(fields.map(field => field.group))].map(group => <optgroup key={group} label={group}>{fields.filter(field => field.group === group).map(field => <option key={field.id} value={field.id}>{field.label}</option>)}</optgroup>)}</> }
  function controls(section: 'subject' | 'body', index: number, count: number) {
    const name = section === 'subject' ? 'asunto' : 'cuerpo'
    return <div className="flex flex-wrap gap-2 mt-2">
      <button type="button" className="button-secondary" aria-label={`Subir elemento de ${name} ${index + 1}`} disabled={index === 0} onClick={() => reorder(section, index, -1)}>↑ Subir</button>
      <button type="button" className="button-secondary" aria-label={`Bajar elemento de ${name} ${index + 1}`} disabled={index === count - 1} onClick={() => reorder(section, index, 1)}>↓ Bajar</button>
      <button type="button" className="button-secondary" aria-label={`Eliminar elemento de ${name} ${index + 1}`} onClick={() => template && change(section === 'subject' ? { ...template, subject: template.subject.filter((_, i) => i !== index) } : { ...template, body: template.body.filter((_, i) => i !== index) })}>Eliminar</button>
    </div>
  }
  return <section className="panel noc-panel p-5 min-w-0" aria-labelledby={`${prefix}-title`} aria-busy={busy}>
    <h2 id={`${prefix}-title`} className="noc-section-title mb-4">Plantilla del correo</h2>
    <p className="text-sm text-muted mb-4">Plantilla de texto para Registro de activación FMS. La vista previa utiliza los cambios del editor, sin guardarlos ni enviar correos.</p>
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    {message && <p role="status" className="text-sm text-ink">{message}</p>}
    {loading ? <p>Cargando plantilla…</p> : !template ? <button type="button" className="button-secondary" onClick={() => setRetry(retry + 1)}>Reintentar plantilla</button> : <>
      <fieldset disabled={busy} className="min-w-0 space-y-5">
        <section aria-label="Editor de asunto"><h3 className="font-semibold text-ink mb-2">Asunto</h3>
          <p className="text-sm text-muted mb-2">Los elementos no vacíos se separan automáticamente con un espacio, en este orden. Puedes incluir separadores como |, - o / en el texto fijo. Los campos aportan solo su valor.</p>
          {template.subject.length === 0 && <p className="text-sm text-muted">Sin elementos de asunto.</p>}
          <ol className="space-y-3">{template.subject.map((block, index) => <li key={index} className="rounded-xl border border-slate-300 p-3 min-w-0">
            {block.type === 'text' ? <label className="block text-sm text-ink">Texto fijo {index + 1}<input className="form-input" maxLength={998} value={block.text} onChange={e => subject(index, { ...block, text: e.target.value })} /></label> : <label className="block text-sm text-ink">Campo de asunto {index + 1}<select className="form-input" value={block.field_id} onChange={e => subject(index, { ...block, field_id: e.target.value })}>{fieldOptions()}</select></label>}
            {controls('subject', index, template.subject.length)}
          </li>)}</ol>
          <div className="flex flex-wrap gap-2 mt-3"><button type="button" className="button-secondary" disabled={template.subject.length >= 50} onClick={() => change({ ...template, subject: [...template.subject, { type: 'text', text: '' }] })}>Agregar texto al asunto</button><button type="button" className="button-secondary" disabled={template.subject.length >= 50} onClick={() => change({ ...template, subject: [...template.subject, { type: 'field', field_id: '' }] })}>Agregar campo al asunto</button></div>
        </section>
        <section aria-label="Editor de cuerpo"><h3 className="font-semibold text-ink mb-2">Cuerpo</h3>
          {template.body.length === 0 && <p className="text-sm text-muted">Sin bloques de cuerpo.</p>}
          <ol className="space-y-3">{template.body.map((block, index) => <li key={index} className="rounded-xl border border-slate-300 p-3 min-w-0">
            {block.type === 'field' ? <>
              <label className="block text-sm text-ink">Campo de cuerpo {index + 1}<select className="form-input" value={block.field_id} onChange={e => body(index, { ...block, field_id: e.target.value })}>{fieldOptions()}</select></label>
              <label className="block text-sm text-ink mt-2">Etiqueta {index + 1}<select className="form-input" value={block.label_mode} onChange={e => body(index, { ...block, label_mode: e.target.value as 'DEFAULT' | 'CUSTOM', custom_label: e.target.value === 'CUSTOM' ? '' : null })}><option value="DEFAULT">Por defecto</option><option value="CUSTOM">Personalizado</option></select></label>
              {block.label_mode === 'CUSTOM' && <label className="block text-sm text-ink mt-2">Etiqueta personalizada {index + 1}<input className="form-input" maxLength={100} value={block.custom_label ?? ''} onChange={e => body(index, { ...block, custom_label: e.target.value })} /></label>}
            </> : <label className="block text-sm text-ink">{block.type === 'introduction' ? 'Introducción' : 'Firma'} {index + 1}<textarea className="form-input" rows={3} maxLength={10000} value={block.text} onChange={e => body(index, { ...block, text: e.target.value })} /></label>}
            {controls('body', index, template.body.length)}
          </li>)}</ol>
          <div className="flex flex-wrap gap-2 mt-3">
            <button type="button" className="button-secondary" disabled={template.body.length >= 50} onClick={() => change({ ...template, body: [...template.body, { type: 'introduction', text: '' }] })}>Agregar introducción</button>
            <button type="button" className="button-secondary" disabled={template.body.length >= 50} onClick={() => change({ ...template, body: [...template.body, { type: 'field', field_id: '', label_mode: 'DEFAULT', custom_label: null }] })}>Agregar campo al cuerpo</button>
            <button type="button" className="button-secondary" disabled={template.body.length >= 50} onClick={() => change({ ...template, body: [...template.body, { type: 'signature', text: '' }] })}>Agregar firma</button>
          </div>
        </section>
        <button type="button" className="button-primary" onClick={() => void execute('save')}>{busy ? 'Procesando plantilla…' : 'Guardar plantilla'}</button>
      </fieldset>
      <section aria-label="Vista previa del correo" className="mt-5 border-t border-slate-300 pt-4 min-w-0">
        <h3 className="font-semibold text-ink mb-2">Vista previa</h3>
        {listError ? <><p role="alert">{listError}</p><button className="button-secondary" onClick={() => setActivationRetry(activationRetry + 1)}>Reintentar activaciones</button></> : listLoading ? <p>Cargando activaciones…</p> : activations.length === 0 ? <p>No hay activaciones disponibles en esta página.</p> : <label className="block text-sm text-ink">Activación para vista previa<select className="form-input" disabled={busy} value={activationId} onChange={e => { setActivationId(e.target.value); setPreview(null) }}><option value="">Selecciona una activación</option>{activations.map(row => <option key={row.id} value={row.id}>{row.reference ?? 'Activación'} — {row.circuit.circuit_code}</option>)}</select></label>}
        <div className="flex flex-wrap gap-2 mt-3">
          <button type="button" className="button-secondary" disabled={busy || listLoading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Activaciones anteriores</button>
          <button type="button" className="button-secondary" disabled={busy || listLoading || !!listError || activations.length < 50} onClick={() => setOffset(offset + 50)}>Más activaciones</button>
          <button type="button" className="button-primary" disabled={busy || listLoading || !!listError || !activationId} onClick={() => void execute('preview')}>Generar vista previa</button>
        </div>
        {preview && <div className="mt-4 space-y-3 text-ink min-w-0"><h4 className="font-semibold">Asunto resultante</h4><p className="whitespace-pre-wrap break-words">{preview.subject || 'Asunto vacío'}</p>
          {preview.html_body && <><h4 className="font-semibold">Presentación del correo</h4><iframe title="Vista previa HTML del correo" srcDoc={preview.html_body} sandbox="" referrerPolicy="no-referrer" className="block w-full min-w-0 rounded-xl border border-slate-300 bg-white" style={{ height: 560 }} /></>}
          <details open><summary className="cursor-pointer font-semibold">Contenido de texto plano</summary><p className="mt-2 whitespace-pre-wrap break-words">{preview.body || 'Cuerpo vacío'}</p></details>
        </div>}
      </section>
    </>}
  </section>
}
