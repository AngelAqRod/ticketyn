import { Can, usePermissions } from '../auth/permissions'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { authorizeMailOAuth, disconnectMailOAuth, getMailOAuth, saveMailOAuth, testMailTransport } from '../api/mailNotifications'
import type { OAuthChanges, OAuthConfig, SmtpConfig } from '../api/mailNotifications'
import { FormField } from './FormField'
import { KeyRound, Link2, RefreshCw, Save, Send, Unlink } from 'lucide-react'

const statuses: Record<string, string> = { UNCONFIGURED: 'Sin configurar', CONFIGURED: 'Configurado', REQUIRES_AUTHORIZATION: 'Requiere autorización', AUTHORIZING: 'Autorización en curso', CONNECTED: 'Autorizado', AUTH_ERROR: 'Error de autenticación' }
export function MailTransportControls({ config }: { config: SmtpConfig }) {
  const access=usePermissions()
  const oauth = config.auth_method.startsWith('OAUTH2') && access.can('mail.oauth.view')
  const service = config.auth_method === 'OAUTH2_APPLICATION' && config.provider === 'GOOGLE_WORKSPACE'
  const [settings, setSettings] = useState<OAuthConfig | null>(null)
  const [clientId, setClientId] = useState(''), [tenantId, setTenantId] = useState(''), [clientSecret, setClientSecret] = useState(''), [serviceAccount, setServiceAccount] = useState('')
  const [testStatus, setTestStatus] = useState('')
  const [recipient, setRecipient] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState(''), [message, setMessage] = useState(''), [retry, setRetry] = useState(0)
  const running = useRef(false), alive = useRef(true), currentConfig = useRef(config)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => { currentConfig.current = config; setTestStatus(''); setError(''); setMessage('') }, [config])
  useEffect(() => {
    if (!oauth) return
    const controller = new AbortController()
    getMailOAuth(controller.signal).then(value => { if (!controller.signal.aborted) { setSettings(value); setClientId(value.client_id); setTenantId(value.tenant_id); setError('') } }).catch(failure => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : 'No se pudo consultar OAuth2.') })
    return () => controller.abort()
  }, [oauth, retry])
  function changed() { setError(''); setMessage('') }
  async function execute(action: 'save' | 'authorize' | 'disconnect' | 'test') {
    if (running.current) return
    running.current = true; setBusy(true); changed()
    try {
      if (action === 'save') {
        const changes: OAuthChanges = {}
        if (clientId !== settings?.client_id && !service) changes.client_id = clientId
        if (tenantId !== settings?.tenant_id && config.provider === 'MICROSOFT_365') changes.tenant_id = tenantId
        if (clientSecret && !service) changes.client_secret = clientSecret
        if (serviceAccount && service) changes.service_account = serviceAccount
        const saved = await saveMailOAuth(changes)
        if (alive.current) { setSettings(saved); setClientId(saved.client_id); setTenantId(saved.tenant_id); setClientSecret(''); setServiceAccount(''); setTestStatus(''); setMessage('Configuración OAuth2 guardada sin revelar credenciales.') }
      } else if (action === 'authorize') {
        const result = await authorizeMailOAuth()
        const url = new URL(result.authorization_url)
        if (url.protocol !== 'https:' || !['accounts.google.com', 'login.microsoftonline.com'].includes(url.hostname)) throw new Error('La URL de autorización no es válida.')
        window.location.assign(result.authorization_url)
      } else if (action === 'disconnect') {
        const value = await disconnectMailOAuth()
        if (alive.current) { setSettings(value); setTestStatus(''); setMessage('Conexión local desconectada. Para revocar el consentimiento, utiliza la administración del proveedor.') }
      } else {
        const result = await testMailTransport(recipient)
        if (alive.current && currentConfig.current === config) {
          setRecipient(''); setTestStatus(result.status)
          if (result.status === 'ACCEPTED') setMessage(result.message)
          else setError(result.message)
          if (settings && (result.status === 'AUTH_ERROR' || result.status === 'ACCEPTED')) setSettings({ ...settings, status: result.status === 'AUTH_ERROR' ? 'AUTH_ERROR' : 'CONNECTED' })
        }
      }
    } catch (failure) { if (alive.current && (action !== 'test' || currentConfig.current === config)) setError(failure instanceof Error ? failure.message : 'No se pudo completar la operación de correo.') }
    finally { running.current = false; if (alive.current) setBusy(false) }
  }
  function submit(event: FormEvent, action: 'save' | 'test') { event.preventDefault(); void execute(action) }
  return <div className="mt-6 space-y-5 border-t border-slate-800/80 pt-6" aria-busy={busy}>
    <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 rounded-xl border border-slate-800 bg-[#070d1a]">
      <div className="flex items-center gap-2.5">
        <span className={`flex h-2.5 w-2.5 rounded-full ${
          testStatus === 'AUTH_ERROR' || settings?.status === 'AUTH_ERROR'
            ? 'bg-red-500 shadow-[0_0_8px_#ef4444]'
            : settings?.status === 'CONNECTED'
            ? 'bg-emerald-400 shadow-[0_0_8px_#10b981]'
            : config.configured
            ? 'bg-sky-400 shadow-[0_0_8px_#38bdf8]'
            : 'bg-slate-500'
        }`} />
        <p className="text-xs font-mono font-semibold text-slate-200">
          Estado: {testStatus === 'AUTH_ERROR' ? 'Error de autenticación' : oauth ? statuses[settings?.status ?? 'UNCONFIGURED'] ?? 'Sin configurar' : config.configured ? 'Configurado' : 'Sin configurar'}
        </p>
      </div>
      {oauth && config.provider && (
        <span className="text-[11px] font-mono uppercase tracking-wider px-2.5 py-0.5 rounded-full border border-slate-700 bg-slate-800/80 text-slate-300">
          OAuth2 {config.provider}
        </span>
      )}
    </div>
    {error && <p role="alert" className="text-xs font-mono p-3.5 rounded-xl border border-red-900/60 bg-red-950/30 text-red-300">{error}</p>}
    {message && <p role="status" className="text-xs font-mono p-3.5 rounded-xl border border-emerald-900/60 bg-emerald-950/30 text-emerald-300">{message}</p>}
    {oauth && <section aria-label="Conexión OAuth2" className="rounded-xl border border-slate-800 bg-[#091122] p-5"><div className="flex items-center gap-2.5 pb-3 mb-4 border-b border-slate-800"><KeyRound size={16} className="text-slate-400" /><h3 className="noc-section-title">Autenticación OAuth2</h3></div>
      {!settings ? <button type="button" className="button-secondary rounded-full shadow-xs font-mono text-xs inline-flex items-center gap-2" disabled={busy} onClick={() => setRetry(retry + 1)}><RefreshCw size={13} /><span>Consultar configuración OAuth2</span></button> : <>
        <form aria-label="Credenciales OAuth2" onSubmit={e => submit(e, 'save')}>
          <fieldset className="grid gap-4 sm:grid-cols-2" disabled={busy||!access.can("mail.oauth.edit")}>
            {!service && <FormField id="mail-oauth-client" label="Identificador de aplicación" required><input className="form-input" id="mail-oauth-client" maxLength={254} value={clientId} onChange={e => { setClientId(e.target.value); changed() }} /></FormField>}
            {config.provider === 'MICROSOFT_365' && <FormField id="mail-oauth-tenant" label="Identificador de tenant" required><input className="form-input" id="mail-oauth-tenant" maxLength={36} value={tenantId} onChange={e => { setTenantId(e.target.value); changed() }} /></FormField>}
            {!service && <FormField id="mail-oauth-secret" label="Secreto de aplicación" required={!settings.client_secret_configured}><input className="form-input" id="mail-oauth-secret" type="password" autoComplete="new-password" maxLength={4096} value={clientSecret} onChange={e => { setClientSecret(e.target.value); changed() }} placeholder={settings.client_secret_configured ? 'Dejar vacío para conservar el secreto guardado' : ''} /></FormField>}
            {service && <FormField id="mail-oauth-service" label="JSON de cuenta de servicio" required={!settings.service_account_configured}><textarea className="form-input" id="mail-oauth-service" autoComplete="off" rows={4} maxLength={20000} value={serviceAccount} onChange={e => { setServiceAccount(e.target.value); changed() }} placeholder={settings.service_account_configured ? 'Dejar vacío para conservar la credencial guardada' : ''} /></FormField>}
          </fieldset>
          <div className="mt-3 space-y-1.5">
            <p className="text-xs font-mono text-slate-400">Credencial: {(service ? settings.service_account_configured : settings.client_secret_configured) ? 'guardada; no se muestra su contenido' : 'sin configurar'}.</p>
            {service && <p className="text-xs font-mono text-slate-400">Requiere delegación de dominio de Google Workspace para el buzón guardado como Usuario SMTP.</p>}
            {config.provider === 'MICROSOFT_365' && config.auth_method === 'OAUTH2_APPLICATION' && <p className="text-xs font-mono text-slate-400">Requiere SMTP.SendAsApp, consentimiento administrativo y autorización del buzón en Exchange Online.</p>}
          </div>
          <div className="mt-4"><Can permission="mail.oauth.edit"><button type="submit" className="button-primary button-primary--slate rounded-full shadow-sm font-mono text-xs px-5 py-2 inline-flex items-center gap-2" disabled={busy}><Save size={14} /><span>Guardar credenciales OAuth2</span></button></Can></div>
        </form>
        {config.auth_method === 'OAUTH2_DELEGATED' && <div className="mt-5 pt-4 border-t border-slate-800"><p className="text-xs font-mono text-slate-400 break-words">URL de retorno: <span className="text-slate-300">{settings.redirect_uri ?? 'No configurada en el servidor'}</span></p><div className="mt-3"><Can permission="mail.oauth.authorize"><button type="button" className="button-primary button-primary--slate rounded-full shadow-sm font-mono text-xs px-5 py-2 inline-flex items-center gap-2" disabled={busy || !settings.redirect_uri || !settings.client_secret_configured} onClick={() => void execute('authorize')}><Link2 size={14} /><span>Autorizar cuenta de correo</span></button></Can></div></div>}
        <div className="mt-3"><Can permission="mail.oauth.authorize"><button type="button" className="button-secondary rounded-full shadow-xs font-mono text-xs px-4 py-2 inline-flex items-center gap-2" disabled={busy} onClick={() => void execute('disconnect')}><Unlink size={14} /><span>Desconectar cuenta</span></button></Can></div>
      </>}
    </section>}
    <Can permission="mail.transport.test"><form aria-label="Prueba SMTP" onSubmit={e => submit(e, 'test')} className="rounded-xl border border-slate-800 bg-[#091122] p-5">
      <div className="flex items-center gap-2.5 pb-3 mb-4 border-b border-slate-800"><Send size={16} className="text-slate-400" /><h3 className="noc-section-title">Enviar correo de prueba</h3></div>
      <fieldset disabled={busy || !config.configured} className="space-y-3">
        <FormField id="mail-test-recipient" label="Destinatario temporal" required><input className="form-input font-mono" id="mail-test-recipient" type="email" maxLength={254} value={recipient} onChange={e => { setRecipient(e.target.value); changed() }} placeholder="ejemplo@dominio.com" /></FormField>
        <p className="text-xs font-mono text-slate-400 leading-relaxed">Utiliza el transporte guardado. Una sola dirección, sin destinatarios ni plantillas FMS. Espera 30 segundos entre pruebas; aceptación SMTP no garantiza entrega.</p>
        <div className="pt-1"><button type="submit" className="button-primary button-primary--slate rounded-full shadow-sm font-mono text-xs px-5 py-2 inline-flex items-center gap-2" disabled={busy || !recipient || !config.configured}><Send size={14} /><span>{busy ? 'Procesando correo…' : 'Enviar correo de prueba'}</span></button></div>
      </fieldset>
    </form></Can>
  </div>
}
