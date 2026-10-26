import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useNavigate, useParams } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { PermissionProvider } from '../auth/permissions'
import { CircuitLink } from './CircuitLink'
import { TicketTable } from './TicketTable'
import { ticket } from '../test/fixtures'

function Target() { const navigate = useNavigate(); return <><h1>Circuito {useParams().id}</h1><button onClick={() => navigate(-1)}>Regresar</button></> }
function setup(ui: React.ReactNode, permissions = ['circuits.view', 'tickets.view']) {
  return render(<PermissionProvider permissions={permissions}><MemoryRouter initialEntries={['/tickets/1']}>
    <Routes><Route path="/tickets/1" element={ui} /><Route path="/circuits/:id" element={<Target />} /><Route path="/tickets/:id" element={<h1>Otro ticket</h1>} /></Routes>
  </MemoryRouter></PermissionProvider>)
}
describe('CircuitLink', () => {
  it('utiliza ID real, navegación interna y regreso al ticket sin propagar el clic', () => {
    const rowClick = vi.fn(), fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher)
    setup(<div onClick={rowClick}><CircuitLink id={37}>200.01 — Servicio</CircuitLink></div>)
    const link = screen.getByRole('link', { name: '200.01 — Servicio' })
    expect(link).toHaveAttribute('href', '/circuits/37'); expect(link).not.toHaveAttribute('target')
    fireEvent.click(link)
    expect(screen.getByRole('heading', { name: 'Circuito 37' })).toBeVisible()
    expect(rowClick).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Regresar' }))
    expect(screen.getByRole('link', { name: '200.01 — Servicio' })).toBeVisible()
    expect(fetcher).not.toHaveBeenCalled()
  })
  it.each([undefined, null, 0, -1, 1.5, NaN])('conserva texto sin ruta cuando ID no está resuelto: %s', id => {
    setup(<CircuitLink id={id}>Circuito histórico</CircuitLink>)
    expect(screen.getByText('Circuito histórico')).toBeVisible()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
  it('respeta circuits.view, sin ampliar permisos de consulta contextual', () => {
    setup(<CircuitLink id={37}>200.01</CircuitLink>, ['tickets.view', 'circuits.lookup'])
    expect(screen.getByText('200.01')).toBeVisible(); expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})
describe('Circuitos en TicketTable compartida', () => {
  it('conserva columna y diferencia rutas de ticket y circuito, sin peticiones por fila', () => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher)
    const historical = { ...ticket, circuit_id: 37, circuit: { id: 37, circuit_code: '200.01', description: 'Servicio histórico', active: false } }
    setup(<TicketTable tickets={[historical]} />)
    const table = screen.getByRole('table', { name: 'Listado de tickets' })
    expect(within(table).getAllByRole('columnheader')).toHaveLength(12)
    expect(within(table).getByRole('link', { name: ticket.reference })).toHaveAttribute('href', '/tickets/1')
    const circuit = within(table).getByRole('link', { name: '200.01' })
    expect(circuit).toHaveAttribute('href', '/circuits/37')
    expect(circuit.closest('td')).toHaveAttribute('title', 'Servicio histórico')
    fireEvent.click(circuit)
    expect(screen.getByRole('heading', { name: 'Circuito 37' })).toBeVisible()
    expect(fetcher).not.toHaveBeenCalled()
  })
  it('mantiene circuito como texto sin permiso de lectura', () => {
    setup(<TicketTable tickets={[ticket]} />, ['tickets.view'])
    expect(screen.getByText(ticket.circuit!.circuit_code)).toBeVisible()
    expect(screen.queryByRole('link', { name: ticket.circuit!.circuit_code })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: ticket.reference })).toBeVisible()
  })
  it('no construye una ruta con un FK sin resumen resuelto o con IDs incompatibles', () => {
    setup(<TicketTable tickets={[{ ...ticket, circuit: undefined }, { ...ticket, id: 2, circuit: { ...ticket.circuit!, id: 99 } }]} />)
    expect(screen.queryByRole('link', { name: ticket.circuit!.circuit_code })).not.toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Circuito' })).toBeVisible()
  })
})
