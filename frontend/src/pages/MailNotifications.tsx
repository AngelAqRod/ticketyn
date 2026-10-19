import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { MailTransportControls } from '../components/MailTransportControls'
import { MailTemplateEditor } from '../components/MailTemplateEditor'
import { PageHeading } from '../components/PageHeading'
import { FormField } from '../components/FormField'
import { FeedbackMessage } from '../components/FeedbackMessage'
import { RequestState } from '../components/RequestState'
import { getMailEvents, getMailFields, getSmtpConfig, updateMailEvent, updateSmtpConfig } from '../api/mailNotifications'
import type { MailAuth, MailEvent, MailField, MailMode, MailProvider, MailSecurity, SmtpChanges, SmtpConfig } from '../api/mailNotifications'

const providers: [MailProvider, string][] = [['GMAIL', 'Gmail'], ['GOOGLE_WORKSPACE', 'Google Workspace'], ['OUTLOOK_COM', 'Outlook.com'], ['MICROSOFT_365', 'Microsoft 365']]
const temporalities: Record<string, string> = { HISTORICAL: 'Dato histórico de activación', HISTORICAL_REFERENCE_CURRENT_NAME: 'Referencia histórica; nombre actual del catálogo', CURRENT: 'Dato actual' }

export function MailNotifications({ section = 'configuration' }: { section?: 'configuration' | 'templates' }) {
  const templates = section === 'templates'
  const [data, setData] = useState<{ smtp: SmtpConfig | null; events: MailEvent[]; fields: MailField[] } | null>(null)
  const [loading, setLoading] = useState(true), [error, setError] = useState<string | null>(null), [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null)
    Promise.all([templates ? Promise.resolve(null) : getSmtpConfig(controller.signal), getMailEvents(controller.signal)]).then(async ([smtp, events]) => {
      const fields = templates ? (await Promise.all(events.map(event => getMailFields(event.event_key, controller.signal)))).flat() : []
      if (!controller.signal.aborted) { setData({ smtp, events, fields }); setLoading(false) }
    }).catch((failure: unknown) => { if (!controller.signal.aborted) { setError(failure instanceof Error ? failure.message : 'No se pudo cargar la configuración de correo.'); setLoading(false) } })
    return () => controller.abort()
  }, [retry, templates])
  return <>
    <PageHeading title={templates ? "Plantillas de correo" : "Configuración de correo"} description={templates ? "Asunto, cuerpo y vista previa con activaciones reales." : "Configuración de transporte, eventos y destinatarios."} />
    <p className="workspace-caption mb-4 text-sm">Las pruebas de correo son independientes de FMS. Automático solicita el envío al registrar una activación; Manual requiere solicitarlo desde el detalle. Desactivado no solicita envíos.</p>
    {loading || error || !data ? <RequestState loading={loading} error={error} onRetry={() => setRetry(retry + 1)} /> : <div className="space-y-5">
      {!templates && data.smtp && <SmtpSettings initial={data.smtp} />}
      {!templates && data.events.map(event => <EventSettings key={event.event_key} initial={event} />)}
      {templates && data.events.map(event => <MailTemplateEditor key={event.event_key} eventKey={event.event_key} fields={data.fields} />)}
      {templates && <section className="panel noc-panel p-5" aria-labelledby="mail-fields-title"><h2 id="mail-fields-title" className="noc-section-title mb-4">Campos dinámicos disponibles</h2><p className="mb-4 text-sm text-muted">Campos disponibles para el editor y su vista previa. Los datos históricos ausentes no se sustituyen por datos actuales.</p>
        <div className="grid gap-4 lg:grid-cols-3">{[...new Set(data.fields.map(field => field.group))].map(group => <div key={group} className="min-w-0"><h3 className="mb-3 font-semibold text-ink">{group}</h3><ul className="space-y-3">{data.fields.filter(field => field.group === group).map(field => <li key={field.id} className="border-b border-slate-200 pb-2"><p className="text-sm text-ink">{field.label}</p><p className="text-xs text-muted">{temporalities[field.temporality] ?? field.temporality}</p></li>)}</ul></div>)}</div>
      </section>}
    </div>}
  </>
}

function SmtpSettings({ initial }: { initial: SmtpConfig }) {
  const [config, setConfig] = useState(initial), [saved, setSaved] = useState(initial)
  const [password, setPassword] = useState(''), [clear, setClear] = useState(false)
  const [saving, setSaving] = useState(false), [error, setError] = useState<string | null>(null), [success, setSuccess] = useState(false)
  const sending = useRef(false), alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const oauth = config.auth_method.startsWith('OAUTH2')
  function change<T extends keyof SmtpConfig>(key: T, value: SmtpConfig[T]) { setConfig(current => ({ ...current, [key]: value })); setSuccess(false) }
  async function submit(event: FormEvent) {
    event.preventDefault(); if (sending.current) return
    setError(null); setSuccess(false)
    if (!config.host?.trim() || !config.sender_email?.trim() || !Number.isInteger(config.port) || config.port < 1 || config.port > 65535) { setError('Completa servidor, remitente y un puerto válido entre 1 y 65535.'); return }
    if (config.security === 'NONE' && !config.allow_unencrypted) { setError('Debes autorizar expresamente el uso de un relé local o confiable sin cifrado.'); return }
    if (config.security === 'NONE' && config.auth_method !== 'NONE') { setError('No se permiten credenciales ni tokens sobre SMTP sin cifrado.'); return }
    const changes: SmtpChanges = {}
    for (const key of ['host', 'port', 'security', 'allow_unencrypted', 'sender_email', 'sender_name', 'auth_method', 'provider', 'username'] as const) {
      if (config[key] !== saved[key]) Object.assign(changes, { [key]: config[key] })
    }
    if (config.auth_method === 'PASSWORD' && password) changes.smtp_password = password
    if (clear && config.auth_method !== 'PASSWORD') changes.clear_password = true
    sending.current = true; setSaving(true)
    try {
      const updated = await updateSmtpConfig(changes)
      if (alive.current) { setConfig(updated); setSaved(updated); setPassword(''); setClear(false); setSuccess(true) }
    } catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : 'No se pudo guardar la configuración SMTP.') }
    finally { sending.current = false; if (alive.current) setSaving(false) }
  }
  return <section className="panel noc-panel p-5" aria-labelledby="mail-smtp-title"><h2 id="mail-smtp-title" className="noc-section-title mb-4">Transporte SMTP</h2>
    <form aria-label="Configuración SMTP" aria-busy={saving} aria-describedby={error ? 'mail-smtp-error' : undefined} onSubmit={submit} noValidate>
      <fieldset disabled={saving} className="grid gap-4 sm:grid-cols-2">
        <FormField id="mail-host" label="Servidor SMTP" required><input id="mail-host" className="form-input" maxLength={253} value={config.host ?? ''} onChange={e => change('host', e.target.value)} /></FormField>
        <FormField id="mail-port" label="Puerto" required><input id="mail-port" className="form-input" type="number" min={1} max={65535} value={config.port} onChange={e => change('port', Number(e.target.value))} /></FormField>
        <FormField id="mail-security" label="Seguridad de conexión"><select id="mail-security" className="form-input" value={config.security} onChange={e => { change('security', e.target.value as MailSecurity); change('allow_unencrypted', false) }}><option value="STARTTLS">STARTTLS</option><option value="IMPLICIT_TLS">TLS implícito</option><option value="NONE">Sin cifrado (relé local o confiable)</option></select></FormField>
        <FormField id="mail-auth" label="Método de autenticación"><select id="mail-auth" className="form-input" value={config.auth_method} onChange={e => { change('auth_method', e.target.value as MailAuth); setPassword(''); setClear(false) }}><option value="NONE">Sin autenticación</option><option value="PASSWORD">Usuario y contraseña</option><option value="OAUTH2_DELEGATED">OAuth2 delegado</option><option value="OAUTH2_APPLICATION">OAuth2 de aplicación</option></select></FormField>
        <FormField id="mail-from" label="Dirección del remitente" required><input id="mail-from" className="form-input" type="email" maxLength={254} value={config.sender_email ?? ''} onChange={e => change('sender_email', e.target.value)} /></FormField>
        <FormField id="mail-from-name" label="Nombre visible del remitente"><input id="mail-from-name" className="form-input" maxLength={200} value={config.sender_name} onChange={e => change('sender_name', e.target.value)} /></FormField>
        {(config.auth_method === 'PASSWORD' || oauth) && <FormField id="mail-user" label="Usuario SMTP" required><input id="mail-user" className="form-input" autoComplete="off" maxLength={254} value={config.username ?? ''} onChange={e => change('username', e.target.value)} /></FormField>}
        {config.auth_method === 'PASSWORD' && <>
          <FormField id="mail-password" label="Contraseña SMTP" required={!saved.password_configured}><input id="mail-password" className="form-input" type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} placeholder={saved.password_configured ? 'Dejar vacío para conservar la contraseña guardada' : ''} /></FormField>
        </>}
        {oauth && <FormField id="mail-provider" label="Proveedor OAuth2" required><select id="mail-provider" className="form-input" value={config.provider ?? ''} onChange={e => change('provider', (e.target.value || null) as MailProvider | null)}><option value="">Selecciona un proveedor</option>{providers.filter(([key]) => config.auth_method !== 'OAUTH2_APPLICATION' || key === 'GOOGLE_WORKSPACE' || key === 'MICROSOFT_365').map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></FormField>}
        {config.security === 'NONE' && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={config.allow_unencrypted} onChange={e => change('allow_unencrypted', e.target.checked)} />Autorizo un relé local o confiable sin cifrado</label>}
        {saved.password_configured && config.auth_method !== 'PASSWORD' && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={clear} onChange={e => setClear(e.target.checked)} />Eliminar explícitamente la contraseña SMTP guardada</label>}
      </fieldset>
      <p className="mt-3 text-sm text-muted">Contraseña SMTP: {saved.password_configured ? 'configurada; su contenido no se devuelve' : 'sin configurar'}.</p>
      {oauth && <p className="mt-3 text-sm text-ink">Guarda primero el perfil SMTP y el buzón; luego configura y autoriza la aplicación OAuth2 en el panel inferior.</p>}
      {error && <FeedbackMessage variant="error" id="mail-smtp-error" className="mt-3">{error}</FeedbackMessage>}
      {success && <FeedbackMessage variant="success" className="mt-3">Configuración SMTP guardada. No se realizó ninguna conexión.</FeedbackMessage>}
      <div className="mt-4 flex justify-end"><button type="submit" className="button-primary" disabled={saving}>{saving ? 'Guardando...' : 'Guardar configuración SMTP'}</button></div>
    </form>
    <MailTransportControls key={`${saved.auth_method}:${saved.provider}:${saved.username}`} config={saved} />
  </section>
}

function EventSettings({ initial }: { initial: MailEvent }) {
  const [mode, setMode] = useState(initial.mode), [to, setTo] = useState(initial.to.join('\n')), [cc, setCc] = useState(initial.cc.join('\n')), [bcc, setBcc] = useState(initial.bcc.join('\n'))
  const [saving, setSaving] = useState(false), [error, setError] = useState<string | null>(null), [success, setSuccess] = useState(false)
  const sending = useRef(false), alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  async function submit(event: FormEvent) {
    event.preventDefault(); if (sending.current) return
    setError(null); setSuccess(false); sending.current = true; setSaving(true)
    const addresses = (text: string) => text.split(/[\n,;]/).map(value => value.trim()).filter(Boolean)
    try {
      const updated = await updateMailEvent(initial.event_key, { mode, to: addresses(to), cc: addresses(cc), bcc: addresses(bcc) })
      if (alive.current) { setMode(updated.mode); setTo(updated.to.join('\n')); setCc(updated.cc.join('\n')); setBcc(updated.bcc.join('\n')); setSuccess(true) }
    } catch (failure) { if (alive.current) setError(failure instanceof Error ? failure.message : 'No se pudo guardar el evento.') }
    finally { sending.current = false; if (alive.current) setSaving(false) }
  }
  return <section className="panel noc-panel p-5" aria-labelledby="mail-event-title"><h2 id="mail-event-title" className="noc-section-title mb-4">{initial.label}</h2>
    <form aria-label="Configuración del evento de activación" aria-busy={saving} aria-describedby={error ? 'mail-event-error' : undefined} onSubmit={submit} noValidate>
      <fieldset disabled={saving} className="grid gap-4 sm:grid-cols-3">
        <FormField id="mail-event-mode" label="Modalidad"><select id="mail-event-mode" className="form-input" value={mode} onChange={e => { setMode(e.target.value as MailMode); setSuccess(false) }}><option value="DISABLED">Desactivado</option><option value="MANUAL">Manual</option><option value="AUTOMATIC">Automático</option></select></FormField>
        <div className="sm:col-span-3 text-sm text-muted">Una dirección por línea; también puedes separarlas mediante comas o punto y coma. Cada grupo se guarda independientemente.</div>
        <FormField id="mail-event-to" label="Para"><textarea id="mail-event-to" className="form-input" rows={3} value={to} onChange={e => { setTo(e.target.value); setSuccess(false) }} /></FormField>
        <FormField id="mail-event-cc" label="CC"><textarea id="mail-event-cc" className="form-input" rows={3} value={cc} onChange={e => { setCc(e.target.value); setSuccess(false) }} /></FormField>
        <FormField id="mail-event-bcc" label="CCO"><textarea id="mail-event-bcc" className="form-input" rows={3} value={bcc} onChange={e => { setBcc(e.target.value); setSuccess(false) }} /></FormField>
      </fieldset>
      <p className="mt-3 text-sm text-muted">Los envíos utilizan los destinatarios y la plantilla vigentes al procesar la solicitud.</p>
      {error && <FeedbackMessage variant="error" id="mail-event-error" className="mt-3">{error}</FeedbackMessage>}
      {success && <FeedbackMessage variant="success" className="mt-3">Modalidad y destinatarios guardados.</FeedbackMessage>}
      <div className="mt-4 flex justify-end"><button type="submit" className="button-primary" disabled={saving}>{saving ? 'Guardando...' : 'Guardar evento'}</button></div>
    </form>
  </section>
}
