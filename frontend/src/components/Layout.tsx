import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router'
import { LayoutDashboard, Ticket, Users, Network, Layers3, Settings, Menu, X } from 'lucide-react'
import { getHealth } from '../api'

const navigation = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/tickets', label: 'Tickets', icon: Ticket },
  { path: '/customers', label: 'Clientes', icon: Users },
  { path: '/circuits', label: 'Circuitos', icon: Network },
  { path: '/catalogs', label: 'Catálogos', icon: Layers3 },
  { path: '/settings', label: 'Configuración', icon: Settings },
]

export function Layout() {
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
    <header className="flex h-18 items-center justify-between border-b border-slate-200 bg-white px-5 lg:px-8">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-800 text-white"><Ticket size={21} aria-hidden="true" /></div>
        <span className="text-xl font-semibold tracking-tight text-slate-900">Ticketyn<span className="text-emerald-700">.</span></span>
        <span className="ml-5 hidden border-l border-slate-200 pl-5 text-sm text-slate-500 sm:block">Gestión de incidencias</span>
      </div>
      <div className="flex items-center gap-5">
        <span role="status" title={healthError} className="flex items-center gap-2 text-xs text-slate-600">
          <span aria-hidden="true" className={`h-2 w-2 rounded-full ${health === 'connected' ? 'bg-emerald-600' : health === 'unavailable' ? 'bg-red-600' : 'bg-slate-400'}`} />
          <span className="sr-only sm:not-sr-only">{health === 'connected' ? 'API conectada' : health === 'unavailable' ? 'API no disponible' : 'Comprobando API...'}</span>
        </span>
        <button className="button-secondary md:hidden" aria-label={menuOpen ? 'Cerrar navegación' : 'Abrir navegación'} aria-expanded={menuOpen} aria-controls="main-navigation" onClick={() => setMenuOpen(!menuOpen)}>
          {menuOpen ? <X size={18} /> : <Menu size={18} />}
        </button>
      </div>
    </header>
    <div className="flex min-h-[calc(100vh-4.5rem)] flex-col md:flex-row">
      <aside id="main-navigation" className={`${menuOpen ? 'block' : 'hidden'} w-full shrink-0 border-b border-slate-200 bg-white md:block md:w-56 md:border-r md:border-b-0 lg:w-60`}>
        <nav aria-label="Navegación principal" className="p-4 md:py-7">
          <p className="mb-3 px-3 text-[10px] font-semibold tracking-widest text-slate-400 uppercase">Espacio de trabajo</p>
          <div className="space-y-1">
            {navigation.map(({ path, label, icon: Icon }) => <NavLink key={path} to={path} end={path === '/'} onClick={() => setMenuOpen(false)} className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-3 text-sm ${isActive ? 'bg-emerald-50 font-semibold text-emerald-800' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'} ${path === '/settings' ? 'mt-8 border-t border-slate-100' : ''}`}>
              <Icon size={18} strokeWidth={1.7} aria-hidden="true" />{label}
            </NavLink>)}
          </div>
        </nav>
      </aside>
      <main id="main-content" className="min-w-0 flex-1 px-5 py-8 lg:px-10 lg:py-10">
        <div className="mx-auto max-w-7xl"><Outlet /></div>
      </main>
    </div>
  </div>
}
