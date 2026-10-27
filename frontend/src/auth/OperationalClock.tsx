import { useEffect, useState } from 'react'
import { Clock3 } from 'lucide-react'
import { ticketynTimezone } from '../lib/datetime'

const dateFormat = new Intl.DateTimeFormat('es', { weekday: 'short', day: 'numeric', month: 'short', timeZone: ticketynTimezone })
const timeFormat = new Intl.DateTimeFormat('es', { hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23', timeZone: ticketynTimezone })

/** Hora operativa de Ticketyn (no la del navegador). Tiene su propio estado: el formulario no se vuelve a renderizar cada segundo. */
export function OperationalClock() {
  const [now, setNow] = useState<Date | null>(null)
  useEffect(() => {
    const tick = () => setNow(new Date())
    tick()
    const timer = window.setInterval(tick, 1000)
    return () => window.clearInterval(timer)
  }, [])
  return (
    // Sin aria-live: anunciar la hora cada segundo sería ruido; el nombre accesible describe el reloj.
    <div role="timer" aria-label={`Hora operativa, ${ticketynTimezone}`} className="inline-flex max-w-full flex-wrap items-center gap-x-2 gap-y-0.5 rounded-full border border-[#1e2c4a] bg-[#0d172e] px-3 py-1.5 font-mono text-[11px] text-slate-400">
      <span aria-hidden="true" className="inline-flex flex-wrap items-center gap-x-2">
        <Clock3 size={13} className="text-cyan-400" />
        <span>{now ? dateFormat.format(now) : '---'}</span>
        <strong className="font-bold text-slate-100 tabular-nums">{now ? timeFormat.format(now) : '--:--:--'}</strong>
        <span>· {ticketynTimezone}</span>
      </span>
    </div>
  )
}
