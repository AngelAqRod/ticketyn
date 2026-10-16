import { Changes, ChangeForm, ChangeDetail } from './pages/Changes'
import { InternalTickets, InternalTicketDetail, InternalTicketEditor } from './pages/InternalTickets'
import { Operations } from './pages/Operations'
import { CircuitDetail } from './pages/CircuitDetail'
import { ActivationDetail } from './pages/ActivationDetail'
import { RequestState } from './components/RequestState'
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

const FmsReports = lazy(() => import('./pages/FmsReports').then((module) => ({ default: module.FmsReports })))

const Reports = lazy(() => import('./pages/Reports').then((module) => ({ default: module.Reports })))

export default function App() {
  return <Routes><Route element={<Layout />}>
    <Route index element={<Dashboard />} />
    <Route path="internal-tickets" element={<InternalTickets />} />
    <Route path="internal-tickets/new" element={<InternalTicketEditor />} />
    <Route path="internal-tickets/:id" element={<InternalTicketDetail />} />
    <Route path="internal-tickets/:id/edit" element={<InternalTicketEditor edit />} />
    <Route path="tickets" element={<Tickets />} />
    <Route path="tickets/new" element={<NewTicket />} />
    <Route path="tickets/:id" element={<TicketDetail />} />
    <Route path="tickets/:id/edit" element={<TicketDetail edit />} />
    <Route path="customers" element={<CatalogAdmin key="customers" kind="customers" />} />
    <Route path="circuits" element={<CatalogAdmin key="circuits" kind="circuits" />} />
    <Route path="circuits/:id" element={<CircuitDetail />} />
    <Route path="activations" element={<Operations key="activations" kind="activations" />} />
    <Route path="activations/:id" element={<ActivationDetail />} />
    <Route path="capacity-changes" element={<Operations key="capacity-changes" kind="capacity-changes" />} />
    <Route path="circuit-lifecycle" element={<Operations key="circuit-lifecycle" kind="circuit-lifecycle" />} />
    <Route path="changes" element={<Changes/>}/>
    <Route path="changes/new" element={<ChangeForm/>}/>
    <Route path="changes/:id" element={<ChangeDetail/>}/>
    <Route path="changes/:id/edit" element={<ChangeForm/>}/>
    <Route path="reports" element={<Suspense fallback={<RequestState loading compact loadingText="Cargando reportes..." />}><Reports /></Suspense>} />
    {([['activation-reports', 'activations'], ['capacity-reports', 'capacity-changes'], ['lifecycle-reports', 'circuit-lifecycle']] as const).map(([path, kind]) => <Route key={path} path={path} element={<Suspense fallback={<RequestState loading compact loadingText="Cargando reportes..." />}><FmsReports key={kind} kind={kind} /></Suspense>} />)}
    <Route path="catalogs" element={<Catalogs />} />
    <Route path="settings" element={<Settings />} />
    <Route path="*" element={<div className="panel p-10"><h1 className="text-xl font-semibold">Página no encontrada</h1><Link to="/" className="button-ghost mt-4">Volver al dashboard</Link></div>} />
  </Route></Routes>
}
