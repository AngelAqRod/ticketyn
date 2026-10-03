import { lazy, Suspense } from 'react'
import { Link, Route, Routes } from 'react-router'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { Tickets } from './pages/Tickets'
import { TicketDetail } from './pages/TicketDetail'
import { NewTicket } from './pages/NewTicket'
import { CatalogAdmin } from './components/CatalogAdmin'
import { Catalogs } from './pages/Catalogs'
import { Settings } from './pages/Settings'

const Reports = lazy(() => import('./pages/Reports').then((module) => ({ default: module.Reports })))

export default function App() {
  return <Routes><Route element={<Layout />}>
    <Route index element={<Dashboard />} />
    <Route path="tickets" element={<Tickets />} />
    <Route path="tickets/new" element={<NewTicket />} />
    <Route path="tickets/:id" element={<TicketDetail />} />
    <Route path="tickets/:id/edit" element={<TicketDetail edit />} />
    <Route path="customers" element={<CatalogAdmin key="customers" kind="customers" />} />
    <Route path="circuits" element={<CatalogAdmin key="circuits" kind="circuits" />} />
    <Route path="reports" element={<Suspense fallback={<p role="status">Cargando reportes...</p>}><Reports /></Suspense>} />
    <Route path="catalogs" element={<Catalogs />} />
    <Route path="settings" element={<Settings />} />
    <Route path="*" element={<div className="panel p-10"><h1 className="text-xl font-semibold">Página no encontrada</h1><Link to="/" className="mt-4 inline-block text-emerald-800 underline">Volver al dashboard</Link></div>} />
  </Route></Routes>
}
