import { Can, usePermissions } from '../auth/permissions'
import { useEffect, useRef, useState } from 'react'
import { getMailTemplate, saveMailTemplate, previewMailTemplate } from '../api/mailNotifications'
import type { BodyBlock, MailField, MailPreview, MailTemplate, SubjectBlock } from '../api/mailNotifications'
import { listOperations } from '../api/fms'
import type { Operation } from '../types/fms'
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Eye, FileCode2, FileText, Plus, RefreshCw, Save, Trash2 } from 'lucide-react'

export function MailTemplateEditor({ eventKey, fields }: { eventKey: string; fields: MailField[] }) {
  const access=usePermissions(), editable=access.can("mail.templates.edit"), mayPreview=access.can("mail.templates.preview")
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
    if(!mayPreview)return
    const controller = new AbortController(); setListLoading(true); setListError(''); setActivationId(''); setPreview(null)
    listOperations('activations', new URLSearchParams({ limit: '50', offset: String(offset) }), controller.signal).then(rows => { if (!controller.signal.aborted) { setActivations(rows); setListLoading(false) } }).catch(failure => { if (!controller.signal.aborted) { setListError(failure instanceof Error ? failure.message : 'No se pudieron consultar las activaciones.'); setListLoading(false) } })
    return () => controller.abort()
  }, [offset, activationRetry, mayPreview])
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
    return <div className="flex items-center gap-1 shrink-0">
      <button type="button" className="button-secondary rounded-full shadow-xs font-mono text-[11px] px-2.5 py-1 inline-flex items-center gap-1" aria-label={`Subir elemento de ${name} ${index + 1}`} disabled={index === 0} onClick={() => reorder(section, index, -1)}><ArrowUp size={12} />Subir</button>
      <button type="button" className="button-secondary rounded-full shadow-xs font-mono text-[11px] px-2.5 py-1 inline-flex items-center gap-1" aria-label={`Bajar elemento de ${name} ${index + 1}`} disabled={index === count - 1} onClick={() => reorder(section, index, 1)}><ArrowDown size={12} />Bajar</button>
      <button type="button" className="button-secondary rounded-full shadow-xs font-mono text-[11px] px-2.5 py-1 inline-flex items-center gap-1 text-rose-300 hover:text-rose-200" aria-label={`Eliminar elemento de ${name} ${index + 1}`} onClick={() => template && change(section === 'subject' ? { ...template, subject: template.subject.filter((_, i) => i !== index) } : { ...template, body: template.body.filter((_, i) => i !== index) })}><Trash2 size={12} />Eliminar</button>
    </div>
  }
  return <section className="panel noc-panel rounded-2xl border border-slate-700/60 bg-[#0b1426] p-6 shadow-xl min-w-0" aria-labelledby={`${prefix}-title`} aria-busy={busy}>
    <div className="flex flex-wrap items-center justify-between gap-3 pb-4 mb-5 border-b border-slate-800/80">
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-700 bg-slate-800/60 text-slate-300 shadow-inner">
          <FileCode2 size={18} />
        </span>
        <div>
          <h2 id={`${prefix}-title`} className="text-base font-bold tracking-tight text-white font-display">Plantilla del correo</h2>
          <p className="text-xs text-slate-400 font-mono">Plantilla de texto para Registro de activación FMS. La vista previa utiliza los cambios del editor, sin guardarlos ni enviar correos.</p>
        </div>
      </div>
      <span className="font-mono text-xs px-2.5 py-1 rounded-full border border-slate-700 bg-[#070d1a] text-slate-300">
        v{template?.version ?? 1}
      </span>
    </div>
    {error && <p role="alert" className="text-xs font-mono p-3.5 rounded-xl border border-red-900/60 bg-red-950/30 text-red-300 mb-4">{error}</p>}
    {message && <p role="status" className="text-xs font-mono p-3.5 rounded-xl border border-emerald-900/60 bg-emerald-950/30 text-emerald-300 mb-4">{message}</p>}
    {loading ? <p className="text-xs font-mono text-slate-400">Cargando plantilla…</p> : !template ? <button type="button" className="button-secondary rounded-full shadow-xs font-mono text-xs inline-flex items-center gap-2" onClick={() => setRetry(retry + 1)}><RefreshCw size={13} /><span>Reintentar plantilla</span></button> : <>
      <fieldset disabled={busy||!editable} className="min-w-0 space-y-6">
        <section aria-label="Editor de asunto" className="rounded-xl border border-slate-800 bg-[#091122] p-5">
          <div className="flex items-center gap-2 pb-2 mb-3 border-b border-slate-800">
            <h3 className="font-mono text-xs font-bold uppercase tracking-wider text-white">Asunto</h3>
          </div>
          <p className="text-xs font-mono text-slate-400 mb-3 leading-relaxed">Los elementos no vacíos se separan automáticamente con un espacio, en este orden. Puedes incluir separadores como |, - o / en el texto fijo. Los campos aportan solo su valor.</p>
          {template.subject.length === 0 && <p className="text-xs font-mono text-slate-500 italic p-3 rounded-lg bg-[#070d1a] border border-slate-800/80 mb-3">Sin elementos de asunto.</p>}
          <ol className="space-y-2">{template.subject.map((block, index) => <li key={index} className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 rounded-xl border border-slate-800 bg-[#070d1a] p-2 sm:px-3 sm:py-2 min-w-0">
            {block.type === 'text' ? (
              <label className="flex-1 flex flex-col sm:flex-row sm:items-center gap-1.5 sm:gap-3 text-xs font-mono font-semibold text-slate-300 min-w-0">
                <span className="shrink-0 text-slate-400 font-medium sm:w-32">Texto fijo {index + 1}</span>
                <input className="form-input font-mono flex-1 min-w-0 text-xs py-1.5" maxLength={998} value={block.text} onChange={e => subject(index, { ...block, text: e.target.value })} />
              </label>
            ) : (
              <label className="flex-1 flex flex-col sm:flex-row sm:items-center gap-1.5 sm:gap-3 text-xs font-mono font-semibold text-slate-300 min-w-0">
                <span className="shrink-0 text-slate-400 font-medium sm:w-32">Campo de asunto {index + 1}</span>
                <select className="form-input font-mono flex-1 min-w-0 text-xs py-1.5" value={block.field_id} onChange={e => subject(index, { ...block, field_id: e.target.value })}>{fieldOptions()}</select>
              </label>
            )}
            <div className="shrink-0 flex items-center justify-end self-end sm:self-auto">
              {controls('subject', index, template.subject.length)}
            </div>
          </li>)}</ol>
          <div className="flex flex-wrap gap-2 mt-4"><button type="button" className="button-secondary rounded-full shadow-xs font-mono text-xs px-4 py-2 inline-flex items-center gap-1.5" disabled={template.subject.length >= 50} onClick={() => change({ ...template, subject: [...template.subject, { type: 'text', text: '' }] })}><Plus size={13} />Agregar texto al asunto</button><button type="button" className="button-secondary rounded-full shadow-xs font-mono text-xs px-4 py-2 inline-flex items-center gap-1.5" disabled={template.subject.length >= 50} onClick={() => change({ ...template, subject: [...template.subject, { type: 'field', field_id: '' }] })}><Plus size={13} />Agregar campo al asunto</button></div>
        </section>
        <section aria-label="Editor de cuerpo" className="rounded-xl border border-slate-800 bg-[#091122] p-5">
          <div className="flex items-center gap-2 pb-2 mb-3 border-b border-slate-800">
            <h3 className="font-mono text-xs font-bold uppercase tracking-wider text-white">Cuerpo</h3>
          </div>
          {template.body.length === 0 && <p className="text-xs font-mono text-slate-500 italic p-3 rounded-lg bg-[#070d1a] border border-slate-800/80 mb-3">Sin bloques de cuerpo.</p>}
          <ol className="space-y-3">{template.body.map((block, index) => <li key={index} className="rounded-xl border border-slate-800 bg-[#070d1a] p-3 sm:p-4 min-w-0 space-y-3">
            <div className="flex items-center justify-between gap-2 pb-2 border-b border-slate-800/80">
              <span className="text-xs font-mono font-semibold text-slate-300 uppercase tracking-wide">
                {block.type === 'field' ? `Campo ${index + 1}` : block.type === 'introduction' ? `Introducción ${index + 1}` : `Firma ${index + 1}`}
              </span>
              {controls('body', index, template.body.length)}
            </div>
            {block.type === 'field' ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <div>
                  <label className="block text-xs font-mono font-semibold text-slate-300">
                    Campo de cuerpo {index + 1}
                    <select className="form-input font-mono mt-1 text-xs py-1.5" value={block.field_id} onChange={e => body(index, { ...block, field_id: e.target.value })}>{fieldOptions()}</select>
                  </label>
                </div>
                <div>
                  <label className="block text-xs font-mono font-semibold text-slate-300">
                    Etiqueta {index + 1}
                    <select className="form-input font-mono mt-1 text-xs py-1.5" value={block.label_mode} onChange={e => body(index, { ...block, label_mode: e.target.value as 'DEFAULT' | 'CUSTOM', custom_label: e.target.value === 'CUSTOM' ? '' : null })}><option value="DEFAULT">Por defecto</option><option value="CUSTOM">Personalizado</option></select>
                  </label>
                </div>
                {block.label_mode === 'CUSTOM' && (
                  <div>
                    <label className="block text-xs font-mono font-semibold text-slate-300">
                      Etiqueta personalizada {index + 1}
                      <input className="form-input font-mono mt-1 text-xs py-1.5" maxLength={100} value={block.custom_label ?? ''} onChange={e => body(index, { ...block, custom_label: e.target.value })} />
                    </label>
                  </div>
                )}
              </div>
            ) : (
              <div>
                <label className="block text-xs font-mono font-semibold text-slate-300">
                  {block.type === 'introduction' ? 'Introducción' : 'Firma'} {index + 1}
                  <textarea className="form-input font-mono mt-1 text-xs" rows={2} maxLength={10000} value={block.text} onChange={e => body(index, { ...block, text: e.target.value })} />
                </label>
              </div>
            )}
          </li>)}</ol>
          <div className="flex flex-wrap gap-2 mt-4">
            <button type="button" className="button-secondary rounded-full shadow-xs font-mono text-xs px-4 py-2 inline-flex items-center gap-1.5" disabled={template.body.length >= 50} onClick={() => change({ ...template, body: [...template.body, { type: 'introduction', text: '' }] })}><Plus size={13} />Agregar introducción</button>
            <button type="button" className="button-secondary rounded-full shadow-xs font-mono text-xs px-4 py-2 inline-flex items-center gap-1.5" disabled={template.body.length >= 50} onClick={() => change({ ...template, body: [...template.body, { type: 'field', field_id: '', label_mode: 'DEFAULT', custom_label: null }] })}><Plus size={13} />Agregar campo al cuerpo</button>
            <button type="button" className="button-secondary rounded-full shadow-xs font-mono text-xs px-4 py-2 inline-flex items-center gap-1.5" disabled={template.body.length >= 50} onClick={() => change({ ...template, body: [...template.body, { type: 'signature', text: '' }] })}><Plus size={13} />Agregar firma</button>
          </div>
        </section>
        {editable&&<div className="flex justify-end pt-2"><button type="button" className="button-primary button-primary--slate rounded-full shadow-sm font-mono text-xs px-5 py-2 inline-flex items-center gap-2" onClick={() => void execute('save')}><Save size={14} />{busy ? 'Procesando plantilla…' : 'Guardar plantilla'}</button></div>}
      </fieldset>
      <Can permission="mail.templates.preview"><section aria-label="Vista previa del correo" className="mt-6 border-t border-slate-800/80 pt-6 min-w-0">
        <div className="flex items-center gap-2 pb-2 mb-3 border-b border-slate-800">
          <Eye size={16} className="text-slate-400" />
          <h3 className="font-mono text-xs font-bold uppercase tracking-wider text-white">Vista previa</h3>
        </div>
        {listError ? <><p role="alert" className="text-xs font-mono text-red-400 mb-2">{listError}</p><button className="button-secondary rounded-full shadow-xs font-mono text-xs px-4 py-2 inline-flex items-center gap-1.5" onClick={() => setActivationRetry(activationRetry + 1)}><RefreshCw size={13} />Reintentar activaciones</button></> : listLoading ? <p className="text-xs font-mono text-slate-400">Cargando activaciones…</p> : activations.length === 0 ? <p className="text-xs font-mono text-slate-500 italic p-3 rounded-lg bg-[#070d1a] border border-slate-800/80">No hay activaciones disponibles en esta página.</p> : <label className="block text-xs font-mono font-semibold text-slate-300">Activación para vista previa<select className="form-input font-mono mt-1.5" disabled={busy} value={activationId} onChange={e => { setActivationId(e.target.value); setPreview(null) }}><option value="">Selecciona una activación</option>{activations.map(row => <option key={row.id} value={row.id}>{row.reference ?? 'Activación'} — {row.circuit.circuit_code}</option>)}</select></label>}
        <div className="flex flex-wrap gap-2 mt-4">
          <button type="button" className="button-secondary rounded-full shadow-xs font-mono text-xs px-4 py-2 inline-flex items-center gap-1.5" disabled={busy || listLoading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}><ChevronLeft size={13} />Activaciones anteriores</button>
          <button type="button" className="button-secondary rounded-full shadow-xs font-mono text-xs px-4 py-2 inline-flex items-center gap-1.5" disabled={busy || listLoading || !!listError || activations.length < 50} onClick={() => setOffset(offset + 50)}>Más activaciones<ChevronRight size={13} /></button>
          <button type="button" className="button-primary button-primary--slate rounded-full shadow-sm font-mono text-xs px-5 py-2 inline-flex items-center gap-2" disabled={busy || listLoading || !!listError || !activationId} onClick={() => void execute('preview')}><Eye size={14} />Generar vista previa</button>
        </div>
        {preview && <div className="mt-5 space-y-4 min-w-0">
          <div className="rounded-xl border border-slate-800 bg-[#070d1a] p-4">
            <h4 className="font-mono text-xs font-bold uppercase text-slate-400 mb-1.5">Asunto resultante</h4>
            <p className="font-mono text-sm text-slate-100 whitespace-pre-wrap break-words">{preview.subject || 'Asunto vacío'}</p>
          </div>
          {preview.html_body && <div className="space-y-2">
            <h4 className="font-mono text-xs font-bold uppercase text-slate-400">Presentación del correo</h4>
            <iframe title="Vista previa HTML del correo" srcDoc={preview.html_body} sandbox="" referrerPolicy="no-referrer" className="block w-full min-w-0 rounded-xl border border-slate-700 bg-white shadow-xl" style={{ height: 560 }} />
          </div>}
          <details open className="rounded-xl border border-slate-800 bg-[#070d1a] p-4 text-xs font-mono">
            <summary className="cursor-pointer font-bold text-slate-300">Contenido de texto plano</summary>
            <p className="mt-2.5 text-slate-400 whitespace-pre-wrap break-words">{preview.body || 'Cuerpo vacío'}</p>
          </details>
        </div>}
      </section></Can>
    </>}
  </section>
}
