import { Link, Route, Routes } from 'react-router'
import { Layout } from './components/Layout'
import { Dashboard } from './pages/Dashboard'
import { Tickets } from './pages/Tickets'
import { Placeholder } from './pages/Placeholder'

export default function App() {
  return <Routes><Route element={<Layout />}>
    <Route index element={<Dashboard />} />
    <Route path="tickets" element={<Tickets />} />
    <Route path="customers" element={<Placeholder title="Clientes" description="Clientes y sus códigos de negocio." />} />
    <Route path="circuits" element={<Placeholder title="Circuitos" description="Circuitos y servicios contratados por tus clientes." />} />
    <Route path="catalogs" element={<Placeholder title="Catálogos" description="Sectores, departamentos y tipos de incidencia." />} />
    <Route path="settings" element={<Placeholder title="Configuración" description="Preferencias y numeración de tickets de esta instalación." />} />
    <Route path="*" element={<div className="panel p-10"><h1 className="text-xl font-semibold">Página no encontrada</h1><Link to="/" className="mt-4 inline-block text-emerald-800 underline">Volver al dashboard</Link></div>} />
  </Route></Routes>
}
