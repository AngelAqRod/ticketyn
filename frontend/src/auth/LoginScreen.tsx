import type { FormEvent } from 'react'
import { ChevronRight, CircleAlert, Clock3, Eye, EyeOff, Info, Lock, ShieldCheck, User } from 'lucide-react'
import { identityFor } from '../components/moduleIdentity'
import { OperationalClock } from './OperationalClock'

// Solo presentación del login. La lógica (envío, token, sesión, errores) permanece en AuthGate.
export const SESSION_EXPIRED_NOTICE = 'Tu sesión venció o fue invalidada. Inicia sesión nuevamente.'

// Constelación decorativa: porcentajes del viewport del panel. «corners» deja solo algunos nodos de las esquinas.
const LINES: [number, number, number, number][] = [[8, 8, 22, 12], [22, 12, 18, 24], [18, 24, 28, 30], [78, 10, 92, 16], [92, 16, 84, 26], [84, 26, 72, 20], [72, 20, 65, 12], [5, 45, 14, 52], [14, 52, 8, 65], [88, 42, 95, 55], [95, 55, 86, 68], [12, 80, 25, 86], [25, 86, 38, 82], [38, 82, 48, 90], [62, 88, 75, 82], [75, 82, 88, 88]]
const NODES: [number, number, number, number][] = [[8, 8, 2, .4], [22, 12, 2.5, .6], [18, 24, 2, .5], [28, 30, 3, .7], [78, 10, 2.5, .5], [92, 16, 2, .4], [84, 26, 3, .8], [72, 20, 2, .5], [65, 12, 2.5, .6], [5, 45, 2, .4], [14, 52, 3, .7], [8, 65, 2.5, .5], [88, 42, 2.5, .6], [95, 55, 2, .4], [86, 68, 3, .75], [12, 80, 2, .4], [25, 86, 3, .7], [38, 82, 2, .5], [48, 90, 2.5, .6], [62, 88, 2, .4], [75, 82, 3, .7], [88, 88, 2.5, .5]]

function Constellation({ id, corners = false, className = '' }: { id: string; corners?: boolean; className?: string }) {
  const lines = corners ? LINES.filter((_, i) => [3, 4, 11, 12].includes(i)) : LINES
  const nodes = corners ? NODES.filter((_, i) => [4, 5, 6, 15, 16, 17].includes(i)) : NODES
  return (
    <svg className={`absolute inset-0 h-full w-full pointer-events-none ${className}`} xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={id} x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stopColor="#0879F8" stopOpacity="0.4" /><stop offset="100%" stopColor="#00D1FF" stopOpacity="0.15" /></linearGradient>
      </defs>
      <g stroke={`url(#${id})`} strokeWidth="0.85" fill="none">{lines.map(([x1, y1, x2, y2]) => <line key={`${x1}${y1}`} x1={`${x1}%`} y1={`${y1}%`} x2={`${x2}%`} y2={`${y2}%`} />)}</g>
      <g fill="#00D1FF">{nodes.map(([x, y, r, o]) => <circle key={`${x}${y}`} cx={`${x}%`} cy={`${y}%`} r={r} opacity={o} />)}</g>
    </svg>
  )
}

// Color de cada cápsula = tema del módulo en moduleIdentity (misma identidad que la navegación).
const capsules = [['/tickets', 'Tickets'], ['/internal-tickets', 'Tickets internos'], ['/changes', 'Control de cambios'], ['/activations', 'FMS']] as const

interface Props {
  notice: { kind: 'info' | 'error'; text: string } | null
  busy: boolean
  showPassword: boolean
  onTogglePassword: () => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

export function LoginScreen({ notice, busy, showPassword, onTogglePassword, onSubmit }: Props) {
  const inputClass = 'form-input font-mono w-full bg-[#070d1a] border border-[#1e2c4a] rounded-xl pl-11 py-3 text-sm text-slate-100 placeholder:text-slate-400 placeholder:opacity-100 focus:outline-none input-focused-glow transition duration-150'
  return (
    <div className="min-h-screen overflow-x-hidden bg-[#070c18] text-slate-100 select-none md:grid md:grid-cols-2">
      {/* Panel de marca: compacto en móvil, a altura completa desde md. */}
      <section className="relative flex items-center justify-center overflow-hidden border-b border-[#1e2c4a] bg-[#070c18] px-4 py-8 md:min-h-screen md:border-b-0 md:border-r md:py-12">
        <Constellation id="netGradBrand" className="opacity-40" />
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center overflow-hidden" aria-hidden="true">
          <div className="h-[420px] w-[420px] rounded-full bg-[#0879F8]/10 blur-[120px] md:h-[600px] md:w-[600px]" />
        </div>
        <div className="relative z-10 flex w-full flex-col items-center text-center">
          <div className="relative flex h-44 w-44 items-center justify-center md:h-[260px] md:w-[260px]">
            <svg className="absolute inset-0 h-full w-full pointer-events-none radar-pulse" viewBox="0 0 220 220" aria-hidden="true" focusable="false">
              <circle cx="110" cy="110" r="100" fill="none" stroke="rgba(8, 121, 248, 0.16)" strokeWidth="1" />
              <circle cx="110" cy="110" r="76" fill="none" stroke="rgba(0, 209, 255, 0.22)" strokeWidth="1" strokeDasharray="4,5" />
              <circle cx="110" cy="110" r="54" fill="none" stroke="rgba(8, 121, 248, 0.3)" strokeWidth="1" strokeDasharray="3,3" />
              <circle cx="178" cy="62" r="3" fill="#00D1FF" opacity="0.85" />
              <circle cx="42" cy="145" r="2.5" fill="#0879F8" opacity="0.75" />
              <circle cx="132" cy="184" r="3" fill="#00D1FF" opacity="0.85" />
              <circle cx="68" cy="48" r="2" fill="#0879F8" opacity="0.7" />
              <line x1="32" y1="188" x2="188" y2="32" stroke="rgba(0, 209, 255, 0.16)" strokeWidth="1" strokeDasharray="3,4" />
            </svg>
            <img src="/branding/isotipo_oscuro.svg" alt="" aria-hidden="true" className="relative z-10 h-20 w-20 md:h-[130px] md:w-[130px] drop-shadow-[0_0_30px_rgba(0,209,255,0.45)]" />
          </div>
          <img src="/branding/logotipo_oscuro.svg" alt="Ticketyn" className="mt-1 h-11 w-auto md:mt-2 md:h-[62px] drop-shadow-[0_4px_18px_rgba(8,121,248,0.4)]" />
          <p className="mt-3 flex items-center justify-center gap-2 font-mono text-[11px] uppercase tracking-[0.2em] text-slate-400 md:text-xs">
            <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 shadow-[0_0_6px_#00D1FF]" aria-hidden="true" />
            <span>Centro de Operaciones de Red</span>
          </p>
          {/* Cápsulas solo decorativas: sin enlaces, sin clic, sin foco. */}
          <div className="mt-6 flex max-w-sm flex-wrap justify-center gap-2" aria-hidden="true">
            {capsules.map(([path, label]) => (
              <span key={label} className={`login-capsule login-capsule--${identityFor(path)?.theme}`}><span className="login-capsule-dot" />{label}</span>
            ))}
          </div>
        </div>
      </section>

      {/* Panel de acceso */}
      <section className="relative flex flex-col overflow-hidden bg-[#0b1426] px-4 py-6 sm:px-8 md:min-h-screen">
        <Constellation id="netGradAccess" corners className="opacity-50" />
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-cyan-400/10 blur-[100px]" aria-hidden="true" />
        <div className="relative z-10 flex flex-wrap items-center justify-between gap-3">
          <span className="font-mono text-[11px] font-bold uppercase tracking-[0.2em] text-slate-400">Acceso al sistema</span>
          <OperationalClock />
        </div>

        <div className="relative z-10 flex flex-1 items-center justify-center py-8">
          <main className="panel relative w-full max-w-[420px] rounded-3xl border border-[#1e2c4a] bg-[#0d172e] p-6 shadow-[0_20px_50px_rgba(0,0,0,0.6)] sm:p-8">
            <div className="absolute -top-px left-12 right-12 h-px bg-gradient-to-r from-transparent via-cyan-400/60 to-transparent" aria-hidden="true" />
            <div className="mb-6">
              <h1 className="font-display text-2xl font-bold tracking-tight text-white">Iniciar sesión</h1>
              <p className="mt-1.5 font-mono text-xs text-slate-400">Ingresa tus credenciales para continuar</p>
              <div className="mt-3 h-px w-8 bg-cyan-400/60" aria-hidden="true" />
            </div>

            {notice?.kind === 'info' && (
              <p role="status" className="mb-5 flex items-start gap-2.5 rounded-xl border border-[rgba(245,158,11,.35)] bg-[rgba(245,158,11,.08)] p-3.5 font-mono text-xs leading-relaxed text-[#fde68a]">
                <Info size={15} className="mt-0.5 shrink-0" aria-hidden="true" />{notice.text}
              </p>
            )}
            {notice?.kind === 'error' && (
              <p role="alert" className="mb-5 flex items-start gap-2.5 rounded-xl border border-[rgba(239,68,68,.45)] bg-[rgba(239,68,68,.1)] p-3.5 font-mono text-xs leading-relaxed text-[#fecaca]">
                <CircleAlert size={15} className="mt-0.5 shrink-0" aria-hidden="true" />{notice.text}
              </p>
            )}

            <form onSubmit={onSubmit} className="space-y-5">
              <div>
                <label className="mb-2 block font-mono text-xs font-bold uppercase tracking-wider text-slate-300">
                  Usuario
                  <div className="relative mt-1 flex items-center">
                    <span className="absolute left-4 pointer-events-none text-slate-400" aria-hidden="true"><User size={16} /></span>
                    <input className={`${inputClass} pr-4`} name="username" autoComplete="username" required maxLength={100} placeholder="Ej. operador.noc" />
                  </div>
                </label>
              </div>
              <div>
                <label className="mb-2 block font-mono text-xs font-bold uppercase tracking-wider text-slate-300">
                  Contraseña
                  <div className="relative mt-1 flex items-center">
                    <span className="absolute left-4 pointer-events-none text-slate-400" aria-hidden="true"><Lock size={16} /></span>
                    <input className={`${inputClass} pr-11`} name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" required />
                    <button type="button" aria-label={showPassword ? 'Ocultar contraseña' : 'Ver contraseña'} onClick={onTogglePassword} className="absolute right-3.5 text-slate-400 transition hover:text-slate-200">
                      {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </label>
              </div>
              <div className="pt-2">
                <button className="button-primary btn-gradient-electric flex w-full cursor-pointer items-center justify-center gap-2 rounded-full px-6 py-3.5 font-mono text-xs font-bold uppercase tracking-wider transition-all duration-200 sm:text-sm" disabled={busy}>
                  <span>{busy ? 'Iniciando…' : 'Iniciar sesión'}</span>
                  <ChevronRight size={16} aria-hidden="true" />
                </button>
              </div>
            </form>
            <p className="mt-5 text-center font-mono text-xs text-slate-400">¿Sin acceso? Contacta a un administrador de Ticketyn.</p>
          </main>
        </div>

        <div className="relative z-10 border-t border-[#1e2c4a] pt-4 font-mono text-xs text-slate-400">
          {/* El tiempo es el configurado en el backend (idle_seconds = 1800); este texto es fijo y debe revisarse si cambia la política. */}
          <p className="flex items-center gap-2"><Clock3 size={14} className="shrink-0 text-cyan-400" aria-hidden="true" />La sesión se cierra tras 30 minutos de inactividad.</p>
          <p className="mt-2 flex items-center gap-2"><ShieldCheck size={14} className="shrink-0 text-cyan-400" aria-hidden="true" />Lo que ves al entrar depende de los permisos de tu rol.</p>
          <p className="mt-4 uppercase tracking-wider">Acceso autorizado</p>
        </div>
      </section>
    </div>
  )
}
