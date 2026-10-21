// Session token is never persisted in localStorage or a cookie.
const KEY = 'ticketyn.session'
export function sessionToken(): string | null { return sessionStorage.getItem(KEY) }
export function setSessionToken(value: string | null) {
  if (value) sessionStorage.setItem(KEY, value)
  else sessionStorage.removeItem(KEY)
}
export function authHeaders(headers?: HeadersInit): Headers {
  const result = new Headers(headers)
  const token = sessionToken()
  if (token) result.set('Authorization', `Bearer ${token}`)
  return result
}
export function expiredSession(expectedToken = sessionToken()) {
  if (sessionToken() !== expectedToken) return
  setSessionToken(null)
  window.dispatchEvent(new Event('ticketyn:unauthorized'))
}
