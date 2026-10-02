import { Link, Route, Routes } from 'react-router'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { Tickets } from './pages/Tickets'
import { TicketDetail } from './pages/TicketDetail'
import { NewTicket } from './pages/NewTicket'
import { CatalogAdmin } from './components/CatalogAdmin'
import { Catalogs } from './pages/Catalogs'
import { Placeholder } from './pages/Placeholder'

export default function App() {
  return <Routes><Route element={<Layout />}>
    <Route index element={<Dashboard />} />
    <Route path="tickets" element={<Tickets />} />
    <Route path="tickets/new" element={<NewTicket />} />
    <Route path="tickets/:id" element={<TicketDetail />} />
    <Route path="tickets/:id/edit" element={<TicketDetail edit />} />
    <Route path="customers" element={<CatalogAdmin key="customers" kind="customers" />} />
    <Route path="circuits" element={<CatalogAdmin key="circuits" kind="circuits" />} />
    <Route path="catalogs" element={<Catalogs />} />
    <Route path="settings" element={<Placeholder title="Configuración" description="Preferencias y numeración de tickets de esta instalación." />} />
    <Route path="*" element={<div className="panel p-10"><h1 className="text-xl font-semibold">Página no encontrada</h1><Link to="/" className="mt-4 inline-block text-emerald-800 underline">Volver al dashboard</Link></div>} />
  </Route></Routes>
}
