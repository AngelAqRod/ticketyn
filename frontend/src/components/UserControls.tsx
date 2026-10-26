import { useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router'
import { LogOut, UserRound } from 'lucide-react'
import { useAuth } from '../auth/context'
import { LcdOperatorAvatar } from './LcdOperatorAvatar'

export function UserControls() {
  const auth = useAuth(), id = useId(), root = useRef<HTMLDivElement>(null), trigger = useRef<HTMLButtonElement>(null)
  const [compact, setCompact] = useState(() => window.matchMedia?.('(max-width: 1023px)').matches ?? false)
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const query = window.matchMedia?.('(max-width: 1023px)')
    const update = () => { setCompact(query?.matches ?? false); setOpen(false) }
    query?.addEventListener?.('change', update)
    return () => query?.removeEventListener?.('change', update)
  }, [])
  useEffect(() => {
    if (!open) return
    const outside = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false) }
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') { setOpen(false); trigger.current?.focus() } }
    document.addEventListener('pointerdown', outside); document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('pointerdown', outside); document.removeEventListener('keydown', escape) }
  }, [open])
  if (!auth) return null
  const actions = <>
    <span className="header-user-name" title={auth.identity.name}>{auth.identity.name}</span>
    <Link className="button-secondary header-user-action" to="/profile" aria-label="Mi perfil" title="Mi perfil" onClick={() => setOpen(false)}><UserRound size={14} aria-hidden="true" /><span>Mi perfil</span></Link>
    <button className="button-secondary header-user-action header-user-logout" disabled={auth.busy} onClick={() => { setOpen(false); void auth.logout() }} aria-label="Cerrar sesión" title="Cerrar sesión"><LogOut size={14} aria-hidden="true" /><span>Cerrar sesión</span></button>
  </>
  return <div ref={root} className="header-user-controls" aria-label="Sesión actual">
    {compact ? <>
      <button ref={trigger} type="button" className="header-user-trigger" aria-label={`Menú de ${auth.identity.name}`} aria-expanded={open} aria-controls={id} onClick={() => setOpen(value => !value)}>
        <LcdOperatorAvatar name={auth.identity.name} username={auth.identity.username} size="compact" />
      </button>
      {open && <div id={id} className="header-user-popover" role="group" aria-label="Controles de usuario">{actions}</div>}
    </> : <><LcdOperatorAvatar name={auth.identity.name} username={auth.identity.username} size="compact" />{actions}</>}
  </div>
}
