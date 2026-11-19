import { AuthGate } from './auth/AuthGate'
import { RequestState } from './components/RequestState'
import { lazy, Suspense } from 'react'
import { Link, Route, Routes } from 'react-router'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'

const AdminRequests = lazy(() => import('./pages/AdminRequests').then((module) => ({ default: module.AdminRequests })))
const AdminRequestForm = lazy(() => import('./pages/AdminRequestForm').then((module) => ({ default: module.AdminRequestForm })))
const AdminRequestDetail = lazy(() => import('./pages/AdminRequestDetail').then((module) => ({ default: module.AdminRequestDetail })))
const InstallationOrders = lazy(() => import('./pages/InstallationOrders').then((module) => ({ default: module.InstallationOrders })))
const InstallationOrderForm = lazy(() => import('./pages/InstallationOrderForm').then((module) => ({ default: module.InstallationOrderForm })))
const InstallationOrderDetail = lazy(() => import('./pages/InstallationOrderDetail').then((module) => ({ default: module.InstallationOrderDetail })))
const InstallationRequestDetail = lazy(() => import('./pages/InstallationRequestDetail').then((module) => ({ default: module.InstallationRequestDetail })))
const Profile = lazy(() => import('./pages/Profile').then((module) => ({ default: module.Profile })))
const SecurityRoles = lazy(() => import('./pages/SecurityRoles').then((module) => ({ default: module.SecurityRoles })))
const SecuritySessions = lazy(() => import('./pages/SecuritySessions').then((module) => ({ default: module.SecuritySessions })))
const SecurityAudit = lazy(() => import('./pages/SecurityAudit').then((module) => ({ default: module.SecurityAudit })))
const Changes = lazy(() => import('./pages/Changes').then((module) => ({ default: module.Changes })))
const ChangeForm = lazy(() => import('./pages/Changes').then((module) => ({ default: module.ChangeForm })))
const ChangeDetail = lazy(() => import('./pages/Changes').then((module) => ({ default: module.ChangeDetail })))
const InternalTickets = lazy(() => import('./pages/InternalTickets').then((module) => ({ default: module.InternalTickets })))
const InternalTicketDetail = lazy(() => import('./pages/InternalTickets').then((module) => ({ default: module.InternalTicketDetail })))
const InternalTicketEditor = lazy(() => import('./pages/InternalTickets').then((module) => ({ default: module.InternalTicketEditor })))
const Operations = lazy(() => import('./pages/Operations').then((module) => ({ default: module.Operations })))
const CircuitDetail = lazy(() => import('./pages/CircuitDetail').then((module) => ({ default: module.CircuitDetail })))
const DistributionDevices = lazy(() => import('./pages/DistributionDevices').then((module) => ({ default: module.DistributionDevices })))
const DistributionDeviceDetail = lazy(() => import('./pages/DistributionDeviceDetail').then((module) => ({ default: module.DistributionDeviceDetail })))
const ActivationDetail = lazy(() => import('./pages/ActivationDetail').then((module) => ({ default: module.ActivationDetail })))
const MyTickets = lazy(() => import('./pages/MyTickets').then((module) => ({ default: module.MyTickets })))
const Tickets = lazy(() => import('./pages/Tickets').then((module) => ({ default: module.Tickets })))
const TicketDetail = lazy(() => import('./pages/TicketDetail').then((module) => ({ default: module.TicketDetail })))
const NewTicket = lazy(() => import('./pages/NewTicket').then((module) => ({ default: module.NewTicket })))
const CatalogAdmin = lazy(() => import('./components/CatalogAdmin').then((module) => ({ default: module.CatalogAdmin })))
const Catalogs = lazy(() => import('./pages/Catalogs').then((module) => ({ default: module.Catalogs })))
const Settings = lazy(() => import('./pages/Settings').then((module) => ({ default: module.Settings })))
const MailNotifications = lazy(() => import('./pages/MailNotifications').then((module) => ({ default: module.MailNotifications })))


const FmsReports = lazy(() => import('./pages/FmsReports').then((module) => ({ default: module.FmsReports })))

const Reports = lazy(() => import('./pages/Reports').then((module) => ({ default: module.Reports })))

export default function App() {
  return <AuthGate><Routes><Route element={<Layout />}>
    <Route index element={<Dashboard />} />
    <Route path="dashboard" element={<Dashboard />} />
    <Route path="my-tickets" element={<MyTickets />} />
    <Route path="my-tickets/:tab" element={<MyTickets />} />
    <Route path="mis-tickets" element={<MyTickets />} />
    <Route path="mis-tickets/:tab" element={<MyTickets />} />
    <Route path="internal-tickets" element={<InternalTickets />} />
    <Route path="internal-tickets/new" element={<InternalTicketEditor />} />
    <Route path="internal-tickets/:id" element={<InternalTicketDetail />} />
    <Route path="internal-tickets/:id/edit" element={<InternalTicketEditor edit />} />
    <Route path="tickets" element={<Tickets />} />
    <Route path="tickets/new" element={<NewTicket />} />
    <Route path="tickets/:id" element={<TicketDetail />} />
    <Route path="tickets/:id/edit" element={<TicketDetail edit />} />
    <Route path="admin-requests" element={<AdminRequests />} />
    <Route path="admin-requests/new" element={<AdminRequestForm />} />
    <Route path="admin-requests/:id" element={<AdminRequestDetail />} />
    <Route path="admin-requests/:id/edit" element={<AdminRequestForm edit />} />
    <Route path="installation-orders" element={<InstallationOrders />} />
    <Route path="installation-orders/new" element={<InstallationOrderForm />} />
    <Route path="installation-orders/:id" element={<InstallationOrderDetail />} />
    <Route path="installation-orders/:id/edit" element={<InstallationOrderForm edit />} />
    <Route path="installation-requests/:id" element={<InstallationRequestDetail />} />
    <Route path="customers" element={<CatalogAdmin key="customers" kind="customers" />} />
    <Route path="circuits" element={<CatalogAdmin key="circuits" kind="circuits" />} />
    <Route path="circuits/:id" element={<CircuitDetail />} />
    <Route path="distribution-devices" element={<DistributionDevices />} />
    <Route path="distribution-devices/:id" element={<DistributionDeviceDetail />} />
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
    <Route path="profile" element={<Profile />} />
    <Route path="responsibles" element={<CatalogAdmin key="responsibles" kind="responsibles" administrativeAccess />} />
    <Route path="security-roles" element={<SecurityRoles />} />
    <Route path="security-sessions" element={<SecuritySessions />} />
    <Route path="security-audit" element={<SecurityAudit />} />
    <Route path="catalogs" element={<Catalogs />} />
    <Route path="settings" element={<Settings />} />
    <Route path="mail-templates" element={<MailNotifications key="templates" section="templates" />} />
    <Route path="mail-notifications" element={<MailNotifications key="configuration" />} />
    <Route path="*" element={<div className="panel p-10"><h1 className="text-xl font-semibold">Página no encontrada</h1><Link to="/" className="button-ghost mt-4">Volver al dashboard</Link></div>} />
  </Route></Routes></AuthGate>
}
