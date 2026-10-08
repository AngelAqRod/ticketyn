import { useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { FileDown, FileText, Users } from 'lucide-react'
import { downloadFile } from '../api/client'
import { FeedbackMessage } from './FeedbackMessage'

export function TicketReportDownload({ ticketId }: { ticketId: number }) {
  const trigger = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)
  const menuId = useId()
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState({ top: 0, left: 0, width: 240, maxHeight: 0 })
  const sending = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function close(returnFocus = false) {
    setOpen(false)
    if (returnFocus) trigger.current?.focus()
  }

  useLayoutEffect(() => {
    if (!open) return
    const place = () => {
      const anchor = trigger.current?.getBoundingClientRect()
      if (!anchor) return
      const width = Math.min(240, Math.max(0, window.innerWidth - 32))
      const maxHeight = Math.max(0, window.innerHeight - 32)
      const height = Math.min(menu.current?.getBoundingClientRect().height || 100, maxHeight)
      const below = anchor.bottom + 8
      const above = anchor.top - height - 8
      setPosition({ width, maxHeight,
        left: Math.max(16, Math.min(anchor.right - width, window.innerWidth - width - 16)),
        top: Math.max(16, Math.min(below + height <= window.innerHeight - 16 ? below : above, window.innerHeight - height - 16)),
      })
    }
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !menu.current?.contains(event.target) && !trigger.current?.contains(event.target)) close()
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); close(true) }
    }
    place()
    menu.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus()
    document.addEventListener('pointerdown', outside)
    document.addEventListener('keydown', escape)
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('keydown', escape)
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [open])

  useLayoutEffect(() => {
    if (!open || !menu.current) return
    const height = Math.min(menu.current.getBoundingClientRect().height, position.maxHeight)
    if (position.top + height > window.innerHeight - 16) {
      setPosition((previous) => ({ ...previous, top: Math.max(16, window.innerHeight - height - 16) }))
    }
  }, [open, busy, error, position])

  async function download(audience: 'internal' | 'customer') {
    if (sending.current) return
    sending.current = true; setBusy(true); setError(null)
    try {
      const query = new URLSearchParams({ timezone: Intl.DateTimeFormat().resolvedOptions().timeZone })
      const name = audience === 'internal' ? 'interno' : 'cliente'
      await downloadFile(`/api/tickets/${ticketId}/reports/${audience}/pdf?${query}`, `ticketyn-ticket-${ticketId}-${name}.pdf`)
      close(Boolean(menu.current))
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'No se pudo descargar el reporte.') }
    finally { sending.current = false; setBusy(false) }
  }

  return <div className="min-w-0" aria-busy={busy}>
    <button ref={trigger} type="button" className="button-secondary" aria-expanded={open} aria-controls={open ? menuId : undefined}
      onClick={() => setOpen((value) => !value)} onKeyDown={(event) => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); setOpen(true) }
      }}><FileDown size={16} aria-hidden="true" />Exportar PDF</button>
    {open && createPortal(<div ref={menu} id={menuId} role="group" aria-label="Tipos de reporte PDF"
      className="panel fixed z-50 overflow-y-auto p-2" style={position}
      onBlur={(event) => {
        if (event.relatedTarget instanceof Node && !event.currentTarget.contains(event.relatedTarget) && !trigger.current?.contains(event.relatedTarget)) close()
      }} onKeyDown={(event) => {
        const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')]
        const index = buttons.indexOf(document.activeElement as HTMLButtonElement)
        if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key) && buttons.length) {
          event.preventDefault()
          const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length
          buttons[next]?.focus()
        }
        if (event.key === 'Tab' && ((event.shiftKey && index === 0) || (!event.shiftKey && index === buttons.length - 1))) {
          close(true)
          if (event.shiftKey) event.preventDefault()
        }
      }}>
      <button type="button" className="button-secondary w-full justify-start" disabled={busy} onClick={() => void download('internal')}><FileText size={16} aria-hidden="true" />Reporte técnico interno</button>
      <button type="button" className="button-secondary mt-2 w-full justify-start" disabled={busy} onClick={() => void download('customer')}><Users size={16} aria-hidden="true" />Reporte para cliente</button>
      {busy && <p role="status" className="mt-2 text-xs text-muted">Generando reporte...</p>}
      {error && <FeedbackMessage variant="error" className="mt-2">{error}</FeedbackMessage>}
    </div>, document.body)}
  </div>
}
