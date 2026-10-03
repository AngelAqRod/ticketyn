import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router'
import { LayoutDashboard, Ticket, Users, Network, Layers3, ChartNoAxesCombined, Settings, Menu, X } from 'lucide-react'
import { getHealth } from '../api'
import { identityFor, moduleIdentity } from './moduleIdentity'

const icons = [LayoutDashboard, Ticket, Users, Network, ChartNoAxesCombined, Layers3, Settings]
const navigation = moduleIdentity.map((item, index) => ({ ...item, icon: icons[index] }))


export function Layout() {
  const context = identityFor(useLocation().pathname)
  const ContextIcon = navigation.find((item) => item.path === context?.path)?.icon ?? Ticket
  const [menuOpen, setMenuOpen] = useState(false)
  const [health, setHealth] = useState<'loading' | 'connected' | 'unavailable'>('loading')
  const [healthError, setHealthError] = useState<string | undefined>()
  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal).then(() => {
      if (!controller.signal.aborted) setHealth('connected')
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) {
        setHealth('unavailable')
        setHealthError(error instanceof Error ? error.message : 'Error al comprobar la API.')
      }
    })
    return () => controller.abort()
  }, [])

  return <div className="min-h-screen">
    <a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-white focus:p-3">Saltar al contenido</a>
    <header className="app-header">
      <div className="header-brand">
        <div className="brand-mark"><Ticket size={21} aria-hidden="true" /></div>
        <div><span className="text-xl font-bold tracking-tight">Ticketyn</span><span className="hidden text-[9px] tracking-[.1em] text-blue-200 uppercase sm:block">Incident management</span></div>
      </div>
      <div className="header-context" aria-label="Contexto del módulo">
        <span className="header-context-icon" aria-hidden="true"><ContextIcon size={18} /></span>
        <div><p className="text-[10px] text-muted">Gestión de incidencias / {context?.group}</p><p className="text-sm font-semibold text-ink">{context?.title}</p></div>
      </div>
      <div className="flex items-center gap-3 px-4">
        <span role="status" title={healthError} className={`chip ${health === 'connected' ? 'chip-success' : health === 'unavailable' ? 'chip-danger' : 'chip-neutral'}`}>
          <span aria-hidden="true" className={`h-2 w-2 rounded-full ${health === 'connected' ? 'bg-emerald-600' : health === 'unavailable' ? 'bg-red-600' : 'bg-slate-400'}`} />
          <span className="sr-only sm:not-sr-only">{health === 'connected' ? 'API conectada' : health === 'unavailable' ? 'API no disponible' : 'Comprobando API...'}</span>
        </span>
        <button className="button-secondary md:hidden" aria-label={menuOpen ? 'Cerrar navegación' : 'Abrir navegación'} aria-expanded={menuOpen} aria-controls="main-navigation" onClick={() => setMenuOpen(!menuOpen)}>
          {menuOpen ? <X size={18} /> : <Menu size={18} />}
        </button>
      </div>
    </header>
    <div className="flex min-h-[calc(100vh-4rem)] flex-col md:flex-row">
      <aside id="main-navigation" className={`${menuOpen ? 'block' : 'hidden'} app-sidebar w-full shrink-0 md:block md:w-56 xl:w-60`}>
        <nav aria-label="Navegación principal" className="p-3 md:sticky md:top-16 md:py-6">
          {['Operación', 'Análisis', 'Administración'].map((group) => <div key={group} className="nav-group">
            <p className="nav-group-label">{group}</p>
            {navigation.filter((item) => item.group === group).map(({ path, title, number, icon: Icon }) => <NavLink key={path} to={path} end={path === '/'} onClick={() => setMenuOpen(false)} className="nav-link">
              <span aria-hidden="true" className="nav-number">{number}</span><Icon size={15} strokeWidth={1.8} aria-hidden="true" />{title}
            </NavLink>)}
          </div>)}
        </nav>
      </aside>
      <main id="main-content" className="workspace">
        <div className="w-full"><Outlet /></div>
      </main>
    </div>
  </div>
}
