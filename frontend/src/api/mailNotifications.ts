import { getJson, patchJson, postJson } from './client'

export type MailSecurity = 'STARTTLS' | 'IMPLICIT_TLS' | 'NONE'
export type MailAuth = 'NONE' | 'PASSWORD' | 'OAUTH2_DELEGATED' | 'OAUTH2_APPLICATION'
export type MailProvider = 'GMAIL' | 'GOOGLE_WORKSPACE' | 'OUTLOOK_COM' | 'MICROSOFT_365'
export interface SmtpConfig {
  host: string | null; port: number; security: MailSecurity; allow_unencrypted: boolean
  sender_email: string | null; sender_name: string; auth_method: MailAuth
  provider: MailProvider | null; username: string | null
  password_configured: boolean; oauth_credentials_configured: boolean; configured: boolean
}
export type SmtpChanges = Partial<Pick<SmtpConfig, 'host' | 'port' | 'security' | 'allow_unencrypted' | 'sender_email' | 'sender_name' | 'auth_method' | 'provider' | 'username'>> & { smtp_password?: string; clear_password?: boolean }
export type MailMode = 'AUTOMATIC' | 'MANUAL' | 'DISABLED'
export interface MailEvent { event_key: string; label: string; mode: MailMode; to: string[]; cc: string[]; bcc: string[] }
export interface MailField { id: string; group: string; label: string; format: string; temporality: string; source_paths: string[]; resolver: string }
const base = '/api/mail-notifications'
export const getSmtpConfig = (signal?: AbortSignal) => getJson<SmtpConfig>(`${base}/smtp`, signal)
export const updateSmtpConfig = (changes: SmtpChanges) => patchJson<SmtpConfig>(`${base}/smtp`, changes)
export const getMailEvents = (signal?: AbortSignal) => getJson<MailEvent[]>(`${base}/events`, signal)
export const updateMailEvent = (key: string, changes: Partial<Pick<MailEvent, 'mode' | 'to' | 'cc' | 'bcc'>>) => patchJson<MailEvent>(`${base}/events/${encodeURIComponent(key)}`, changes)
export const getMailFields = (key: string, signal?: AbortSignal) => getJson<MailField[]>(`${base}/events/${encodeURIComponent(key)}/fields`, signal)

export type SubjectBlock = { type: 'text'; text: string } | { type: 'field'; field_id: string }
export type BodyBlock = { type: 'introduction' | 'signature'; text: string } | { type: 'field'; field_id: string; label_mode: 'DEFAULT' | 'CUSTOM'; custom_label: string | null }
export interface MailTemplate { version: 1; subject: SubjectBlock[]; body: BodyBlock[] }
export interface MailPreview { subject: string; body: string }
export const getMailTemplate = (key: string, signal?: AbortSignal) => getJson<MailTemplate>(`${base}/events/${encodeURIComponent(key)}/template`, signal)
export const saveMailTemplate = (key: string, template: MailTemplate) => patchJson<MailTemplate>(`${base}/events/${encodeURIComponent(key)}/template`, template)
export const previewMailTemplate = (key: string, activation_id: number, template: MailTemplate) => postJson<MailPreview>(`${base}/events/${encodeURIComponent(key)}/preview`, { activation_id, template })

export interface OAuthConfig { client_id: string; tenant_id: string; redirect_uri: string | null; status: string; client_secret_configured: boolean; service_account_configured: boolean }
export interface OAuthChanges { client_id?: string; tenant_id?: string; client_secret?: string; service_account?: string }
export interface MailTestResult { status: string; message: string }
export const getMailOAuth = (signal?: AbortSignal) => getJson<OAuthConfig>(`${base}/oauth`, signal)
export const saveMailOAuth = (changes: OAuthChanges) => patchJson<OAuthConfig>(`${base}/oauth`, changes)
export const authorizeMailOAuth = () => postJson<{ authorization_url: string }>(`${base}/oauth/authorize`, {})
export const disconnectMailOAuth = () => postJson<OAuthConfig>(`${base}/oauth/disconnect`, {})
export const testMailTransport = (recipient: string) => postJson<MailTestResult>(`${base}/smtp/test`, { recipient })

export type NotificationState = 'PENDING' | 'PREPARING' | 'SENDING' | 'ACCEPTED' | 'FAILED' | 'PARTIAL' | 'UNCERTAIN' | 'CANCELLED'
export interface ActivationNotificationStatus {
  activation_id: number; mode: MailMode; state: NotificationState | null; revision: number
  processor_paused: boolean; can_request: boolean; configuration_error: string | null; message: string | null
}
export const getActivationNotification = (id: number, signal?: AbortSignal) => getJson<ActivationNotificationStatus>(`/api/activations/${id}/notification`, signal)
export const requestActivationNotification = (id: number, revision: number, confirm_uncertain: boolean) => postJson<ActivationNotificationStatus>(`/api/activations/${id}/notification`, { revision, confirm_uncertain })
