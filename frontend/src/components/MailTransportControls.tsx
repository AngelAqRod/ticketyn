import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { authorizeMailOAuth, disconnectMailOAuth, getMailOAuth, saveMailOAuth, testMailTransport } from '../api/mailNotifications'
import type { OAuthChanges, OAuthConfig, SmtpConfig } from '../api/mailNotifications'
import { FormField } from './FormField'

const statuses: Record<string, string> = { UNCONFIGURED: 'Sin configurar', CONFIGURED: 'Configurado', REQUIRES_AUTHORIZATION: 'Requiere autorización', AUTHORIZING: 'Autorización en curso', CONNECTED: 'Autorizado', AUTH_ERROR: 'Error de autenticación' }
export function MailTransportControls({ config }: { config: SmtpConfig }) {
  const oauth = config.auth_method.startsWith('OAUTH2')
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
  return <div className="mt-5 space-y-4 border-t border-slate-300 pt-4" aria-busy={busy}>
    <p className="text-sm text-ink">Estado: {testStatus === 'AUTH_ERROR' ? 'Error de autenticación' : oauth ? statuses[settings?.status ?? 'UNCONFIGURED'] ?? 'Sin configurar' : config.configured ? 'Configurado' : 'Sin configurar'}</p>
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    {message && <p role="status" className="text-sm text-ink">{message}</p>}
    {oauth && <section aria-label="Conexión OAuth2"><h3 className="noc-section-title mb-3">Autenticación OAuth2</h3>
      {!settings ? <button type="button" className="button-secondary" disabled={busy} onClick={() => setRetry(retry + 1)}>Consultar configuración OAuth2</button> : <>
        <form aria-label="Credenciales OAuth2" onSubmit={e => submit(e, 'save')}>
          <fieldset className="grid gap-4 sm:grid-cols-2" disabled={busy}>
            {!service && <FormField id="mail-oauth-client" label="Identificador de aplicación" required><input className="form-input" id="mail-oauth-client" maxLength={254} value={clientId} onChange={e => { setClientId(e.target.value); changed() }} /></FormField>}
            {config.provider === 'MICROSOFT_365' && <FormField id="mail-oauth-tenant" label="Identificador de tenant" required><input className="form-input" id="mail-oauth-tenant" maxLength={36} value={tenantId} onChange={e => { setTenantId(e.target.value); changed() }} /></FormField>}
            {!service && <FormField id="mail-oauth-secret" label="Secreto de aplicación" required={!settings.client_secret_configured}><input className="form-input" id="mail-oauth-secret" type="password" autoComplete="new-password" maxLength={4096} value={clientSecret} onChange={e => { setClientSecret(e.target.value); changed() }} placeholder={settings.client_secret_configured ? 'Dejar vacío para conservar el secreto guardado' : ''} /></FormField>}
            {service && <FormField id="mail-oauth-service" label="JSON de cuenta de servicio" required={!settings.service_account_configured}><textarea className="form-input" id="mail-oauth-service" autoComplete="off" rows={4} maxLength={20000} value={serviceAccount} onChange={e => { setServiceAccount(e.target.value); changed() }} placeholder={settings.service_account_configured ? 'Dejar vacío para conservar la credencial guardada' : ''} /></FormField>}
          </fieldset>
          <p className="text-sm text-muted mt-3">Credencial: {(service ? settings.service_account_configured : settings.client_secret_configured) ? 'guardada; no se muestra su contenido' : 'sin configurar'}.</p>
          {service && <p className="text-sm text-muted mt-2">Requiere delegación de dominio de Google Workspace para el buzón guardado como Usuario SMTP.</p>}
          {config.provider === 'MICROSOFT_365' && config.auth_method === 'OAUTH2_APPLICATION' && <p className="text-sm text-muted mt-2">Requiere SMTP.SendAsApp, consentimiento administrativo y autorización del buzón en Exchange Online.</p>}
          <button type="submit" className="button-primary mt-3" disabled={busy}>Guardar credenciales OAuth2</button>
        </form>
        {config.auth_method === 'OAUTH2_DELEGATED' && <div className="mt-4"><p className="text-sm text-muted break-words">URL de retorno: {settings.redirect_uri ?? 'No configurada en el servidor'}</p><button type="button" className="button-primary mt-3" disabled={busy || !settings.redirect_uri || !settings.client_secret_configured} onClick={() => void execute('authorize')}>Autorizar cuenta de correo</button></div>}
        <button type="button" className="button-secondary mt-3" disabled={busy} onClick={() => void execute('disconnect')}>Desconectar cuenta</button>
      </>}
    </section>}
    <form aria-label="Prueba SMTP" onSubmit={e => submit(e, 'test')}>
      <h3 className="noc-section-title mb-3">Enviar correo de prueba</h3>
      <fieldset disabled={busy || !config.configured}>
        <FormField id="mail-test-recipient" label="Destinatario temporal" required><input className="form-input" id="mail-test-recipient" type="email" maxLength={254} value={recipient} onChange={e => { setRecipient(e.target.value); changed() }} /></FormField>
        <p className="text-sm text-muted mt-2">Utiliza el transporte guardado. Una sola dirección, sin destinatarios ni plantillas FMS. Espera 30 segundos entre pruebas; aceptación SMTP no garantiza entrega.</p>
        <button type="submit" className="button-primary mt-3" disabled={busy || !recipient || !config.configured}>{busy ? 'Procesando correo…' : 'Enviar correo de prueba'}</button>
      </fieldset>
    </form>
  </div>
}
