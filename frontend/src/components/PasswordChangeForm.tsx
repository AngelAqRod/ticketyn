import { useRef, useState, type FormEvent } from 'react'
import { postJson } from '../api/client'
import { useAuth, type Identity } from '../auth/context'
import { FeedbackMessage } from './FeedbackMessage'

export function PasswordChangeForm() {
  const auth = useAuth()
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const sending = useRef(false)
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (sending.current) return
    const form = event.currentTarget, data = new FormData(form), password = String(data.get('new_password') ?? '')
    setError(''); setNotice('')
    if (!password || new TextEncoder().encode(password).length > 4096) { setError('La contraseña debe contener entre 1 y 4096 bytes UTF-8'); return }
    if (password !== data.get('confirm')) { setError('Las contraseñas no coinciden'); return }
    sending.current = true; setBusy(true)
    try {
      auth?.accept(await postJson<Identity>('/api/auth/password', { current_password: data.get('current_password'), new_password: password }))
      form.reset(); setNotice('Contraseña cambiada. Las demás sesiones se cerraron.')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'No se pudo cambiar la contraseña') }
    finally { sending.current = false; setBusy(false) }
  }
  return <form onSubmit={submit} className="grid gap-4" aria-label="Cambiar contraseña">
    {error && <FeedbackMessage variant="error">{error}</FeedbackMessage>}
    {notice && <FeedbackMessage variant="success">{notice}</FeedbackMessage>}
    <fieldset disabled={busy} className="grid gap-3">
      <label>Contraseña actual<input className="form-input" type="password" name="current_password" autoComplete="current-password" required /></label>
      <label>Nueva contraseña<input className="form-input" type="password" name="new_password" autoComplete="new-password" required /></label>
      <label>Confirmar contraseña<input className="form-input" type="password" name="confirm" autoComplete="new-password" required /></label>
    </fieldset>
    <button disabled={busy} className="button-primary justify-self-start">{busy ? 'Guardando…' : 'Cambiar contraseña'}</button>
  </form>
}
