import { UserControls } from './UserControls'
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router'
import { LayoutDashboard, Ticket, Users, Network, Layers3, ChartNoAxesCombined, Settings, Menu, X, Zap, Gauge, Power, Workflow, Mail, ShieldCheck } from 'lucide-react'
import { getHealth, getSystemVersion } from '../api'
import { usePermissions, routeAllowed } from '../auth/permissions'
import { SevenSegmentNumber } from './SevenSegmentNumber'
import { identityFor, moduleIdentity, moduleGroups, orderedModuleIdentity } from './moduleIdentity'
import { describeVersion, parseVersion } from '../lib/version'

const icons = [LayoutDashboard, Ticket, Ticket, Workflow, Users, Network, ChartNoAxesCombined, Layers3, Settings, Zap, Gauge, Power, ChartNoAxesCombined, ChartNoAxesCombined, ChartNoAxesCombined, Mail, Mail, Users, Settings, Users, ShieldCheck]
const navigation = orderedModuleIdentity.map(item => ({
  ...item, icon: icons[moduleIdentity.findIndex(original => original.path === item.path)],
}))


export function Layout() {
  const access = usePermissions()
  const visibleNavigation = navigation.filter(item => routeAllowed(item.path, access))
  const pathname = useLocation().pathname
  const context = identityFor(pathname) ?? (pathname === '/profile' ? { path: '/profile', title: 'Mi perfil', group: 'Personal', number: '' } : undefined)
  const ContextIcon = navigation.find((item) => item.path === context?.path)?.icon ?? Ticket
  const [menuOpen, setMenuOpen] = useState(false)
  const [health, setHealth] = useState<'loading' | 'connected' | 'unavailable'>('loading')
  const [apiVersion, setApiVersion] = useState<string | null>(null)
  const version = describeVersion(__TICKETYN_FRONTEND_VERSION__, apiVersion)
  const [healthError, setHealthError] = useState<string | undefined>()
  useEffect(() => {
    const controller = new AbortController()
    getSystemVersion(controller.signal)
      .then((data) => { if (!controller.signal.aborted) setApiVersion(parseVersion(data?.version)) })
      .catch(() => { if (!controller.signal.aborted) setApiVersion(null) })
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
        <div className="brand-capsule">
          <div className="brand-mark">
            <img src="/branding/isotipo_oscuro.svg" alt="" aria-hidden="true" className="w-6 h-6 object-contain" />
          </div>
          <span className="text-base font-bold tracking-tight text-white font-display">Ticketyn</span>
        </div>
      </div>
      <div className="header-context" aria-label="Contexto del módulo">
        <span className="header-context-group">{context?.group ?? 'Operación'}</span>
        <span className="header-context-sep" aria-hidden="true">/</span>
        {context?.number && <span className="header-context-number" aria-hidden="true"><SevenSegmentNumber value={context.number} /></span>}
        <span className="header-context-title flex items-center gap-1.5">
          <ContextIcon size={14} aria-hidden="true" className="text-sky-400 shrink-0" />
          <span>{context?.title}</span>
        </span>
      </div>
      <div className="flex min-w-0 items-center gap-2 px-2 sm:px-4">
        <div className="header-status-group">
          <span className="header-version-badge" aria-label="Versión de Ticketyn" title={version.title}>{version.label}</span>
          <span role="status" title={healthError} className={`header-api-badge ${health === 'connected' ? 'header-api-connected' : health === 'unavailable' ? 'header-api-unavailable' : 'header-api-loading'}`}>
            <span aria-hidden="true" className={`h-2 w-2 rounded-full shrink-0 ${health === 'connected' ? 'bg-emerald-400 shadow-[0_0_6px_#10b981]' : health === 'unavailable' ? 'bg-red-500 shadow-[0_0_6px_#ef4444]' : 'bg-slate-400'}`} />
            <span className="sr-only sm:not-sr-only font-mono text-xs font-medium tracking-wide">{health === 'connected' ? 'API conectada' : health === 'unavailable' ? 'API no disponible' : 'Comprobando API...'}</span>
          </span>
          <UserControls />
        </div>
        <button className="header-mobile-toggle button-secondary shrink-0 md:hidden" aria-label={menuOpen ? 'Cerrar navegación' : 'Abrir navegación'} aria-expanded={menuOpen} aria-controls="main-navigation" onClick={() => setMenuOpen(!menuOpen)}>
          {menuOpen ? <X size={18} /> : <Menu size={18} />}
        </button>
      </div>
    </header>
    <div className="flex min-h-[calc(100vh-3.5rem)] flex-col md:flex-row">
      <aside id="main-navigation" className={`${menuOpen ? 'block' : 'hidden'} app-sidebar w-full shrink-0 md:block md:w-56 xl:w-60`}>
        <nav aria-label="Navegación principal" tabIndex={0} className="sidebar-navigation-scroll p-3 md:py-6">
          {moduleGroups.filter(group => visibleNavigation.some(item => item.group === group)).map((group) => <div key={group} className="nav-group">
            <p className="nav-group-label">{group}</p>
            {visibleNavigation.filter((item) => item.group === group).map(({ path, title, number, icon: Icon }) => <NavLink key={path} to={path} end={path === '/'} onClick={() => setMenuOpen(false)} className="nav-link">
              <span aria-hidden="true" className="nav-number hidden"><SevenSegmentNumber value={number} /></span><Icon size={16} strokeWidth={1.8} aria-hidden="true" className="shrink-0" /><span className="nav-title">{title}</span>
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
