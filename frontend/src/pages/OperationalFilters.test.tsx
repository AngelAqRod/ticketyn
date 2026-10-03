import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation, useNavigate } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { Tickets } from './Tickets'
import { CatalogAdmin } from '../components/CatalogAdmin'
import { jsonResponse, ticket } from '../test/fixtures'
const customers = [1, 2].map((id) => ({ id, customer_code: `C-${id}`, name: `Cliente ${id}`, active: id === 1, created_at: ticket.created_at }))
const circuits = [1, 2].map((id) => ({ id, customer_id: id, circuit_code: `LINE-${id}`, description: `Enlace ${id}`, active: id === 1, created_at: ticket.created_at }))
function Location() { const location = useLocation(); const navigate = useNavigate(); return <><output data-testid="url">{location.search}</output><button onClick={() => navigate(-1)}>Atrás</button><button onClick={() => navigate(1)}>Adelante</button></> }
function setup(path = '/tickets', size = 1) {
  const mock = vi.fn((path: string) => {
    const address = new URL(path, 'http://local'), params = address.searchParams
    let data: unknown = []
    if (address.pathname === '/api/tickets') data = Array.from({ length: size }, (_, id) => ({ ...ticket, id: id + 1, reference: `REF-${id}` }))
    if (address.pathname === '/api/customers') data = customers
    if (address.pathname === '/api/circuits') data = circuits.filter((row) => (!params.has('customer_id') || String(row.customer_id) === params.get('customer_id')) && (!params.has('active') || String(row.active) === params.get('active')) && (!params.has('search') || `${row.circuit_code} ${row.description}`.toLowerCase().includes(params.get('search')!.toLowerCase())))
    if (['/api/sectors', '/api/departments', '/api/incident-types', '/api/nodes', '/api/responsibles'].includes(address.pathname)) data = [{ id: 1, name: 'Clasificación', active: true, created_at: ticket.created_at }]
    return Promise.resolve(jsonResponse(data))
  })
  vi.stubGlobal('fetch', mock)
  render(<MemoryRouter initialEntries={[path]}>{path.startsWith('/circuits') ? <CatalogAdmin kind="circuits" /> : <Tickets />}<Location /></MemoryRouter>)
  return mock
}
const params = () => new URLSearchParams(screen.getByTestId('url').textContent ?? '')
async function choose(label: string, name: string) {
  const input = screen.getByRole('combobox', { name: label })
  await waitFor(() => expect(input).not.toBeDisabled())
  fireEvent.click(input); fireEvent.click(await within(screen.getByRole('listbox')).findByRole('option', { name }))
}
describe('filtros operativos en URL', () => {
  it('restaura URL, pagina con filtros y permite atrás/adelante/limpiar', async () => {
    const mock = setup('/tickets?status=OPEN&customer_id=1&from=2026-10-02&to=2026-10-02&offset=50', 50)
    await screen.findByText('REF-0')
    expect(screen.getByLabelText('Estado')).toHaveValue('OPEN')
    expect(screen.getByLabelText('Desde')).toHaveValue('2026-10-02')
    expect(within(screen.getByRole('table')).getAllByText('Cliente uno')).toHaveLength(50)
    expect(within(screen.getByRole('table')).getAllByText('C-001.001')).toHaveLength(50)
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
    await waitFor(() => expect(params().get('offset')).toBe('100'))
    const paths = mock.mock.calls.map(([path]) => path).filter((path) => path.startsWith('/api/tickets?'))
    const request = new URL(paths.at(-1)!, 'http://local')
    expect(request.searchParams.get('customer_id')).toBe('1')
    expect(request.searchParams.get('from')).toBe(new Date(2026, 9, 2).toISOString())
    expect(request.searchParams.get('to')).toBe(new Date(2026, 9, 3).toISOString())
    fireEvent.change(screen.getByLabelText('Estado'), { target: { value: 'CLOSED' } })
    expect(params().has('offset')).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Atrás' }))
    await waitFor(() => expect(params().get('status')).toBe('OPEN'))
    fireEvent.click(screen.getByRole('button', { name: 'Adelante' }))
    await waitFor(() => expect(params().get('status')).toBe('CLOSED'))
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
    expect(screen.getByTestId('url').textContent).toBe('')
  })
  it('circuito global deriva cliente y cambiar cliente limpia circuito incompatible', async () => {
    const mock = setup()
    await choose('Circuito', 'LINE-2 — Enlace 2')
    expect(params().get('circuit_id')).toBe('2'); expect(params().get('customer_id')).toBe('2')
    await waitFor(() => expect(mock.mock.calls.some(([path]) => path.includes('/api/circuits?customer_id=2'))).toBe(true))
    await choose('Cliente', 'C-1 — Cliente 1')
    expect(params().get('customer_id')).toBe('1'); expect(params().has('circuit_id')).toBe(false)
    await choose('Circuito', 'LINE-1 — Enlace 1')
    expect(params().get('circuit_id')).toBe('1')
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar Cliente' }))
    expect(params().get('circuit_id')).toBe('1'); expect(params().has('customer_id')).toBe(false)
  })
  it('búsqueda y clasificación actualizan URL y petición, reiniciando offset', async () => {
    const mock = setup('/tickets?offset=50')
    await screen.findByText('REF-0')
    await waitFor(() => expect(screen.getByLabelText('Sector')).not.toBeDisabled())
    fireEvent.change(screen.getByLabelText('Buscar tickets'), { target: { value: 'Incidencia' } })
    for (const label of ['Sector', 'Departamento', 'Tipo de incidencia']) fireEvent.change(screen.getByLabelText(label), { target: { value: '1' } })
    expect(params().get('search')).toBe('Incidencia')
    expect(params().has('offset')).toBe(false)
    for (const key of ['sector_id', 'department_id', 'incident_type_id']) expect(params().get(key)).toBe('1')
    await waitFor(() => expect(mock.mock.calls.some(([path]) => path.includes('incident_type_id=1') && path.includes('sector_id=1') && path.includes('search=Incidencia'))).toBe(true))
  })
  it('rango invertido muestra error y evita petición de tickets', async () => {
    const mock = setup('/tickets?from=2026-10-03&to=2026-10-02')
    expect(await screen.findByText('Hasta debe ser igual o posterior a Desde.')).toBeInTheDocument()
    expect(mock.mock.calls.some(([path]) => path.startsWith('/api/tickets?'))).toBe(false)
  })
  it('Circuitos filtra desde URL, permite cambiar/limpiar y enlaza tickets', async () => {
    const mock = setup('/circuits?customer_id=2&active=false&search=line')
    await screen.findByText('LINE-2')
    expect(screen.getByLabelText('Estado de circuitos')).toHaveValue('false')
    expect(screen.getByLabelText('Buscar circuitos')).toHaveValue('line')
    expect(screen.getByRole('link', { name: 'Ver tickets de LINE-2' })).toHaveAttribute('href', '/tickets?circuit_id=2')
    await choose('Filtrar por cliente', 'C-1 — Cliente 1')
    fireEvent.change(screen.getByLabelText('Estado de circuitos'), { target: { value: 'true' } })
    fireEvent.change(screen.getByLabelText('Buscar circuitos'), { target: { value: 'Enlace 1' } })
    await screen.findByText('LINE-1')
    expect(mock.mock.calls.some(([path]) => path.includes('active=true') && path.includes('customer_id=1'))).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
    await screen.findByText('LINE-2'); expect(screen.getByTestId('url').textContent).toBe('')
  })
})


describe('filtros Nodo y Responsable', () => {
  it('restaura ambos filtros, pagina, reinicia offset y limpia URL', async () => {
    const mock = setup('/tickets?node_id=1&responsible_id=1&status=OPEN&offset=50', 50)
    await screen.findByText('REF-0')
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Nodo' })).toHaveValue('Clasificación'))
    expect(screen.getByRole('combobox', { name: 'Responsable' })).toHaveValue('Clasificación')
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
    await waitFor(() => expect(mock.mock.calls.some(([path]) => path.includes('offset=100') && path.includes('node_id=1') && path.includes('responsible_id=1'))).toBe(true))
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar Responsable' }))
    expect(params().has('responsible_id')).toBe(false)
    expect(params().get('node_id')).toBe('1'); expect(params().has('offset')).toBe(false)
    await choose('Responsable', 'Clasificación')
    expect(params().get('responsible_id')).toBe('1')
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
    expect(params().has('node_id')).toBe(false); expect(params().has('responsible_id')).toBe(false)
  })
  it('Circuitos conserva Nodo junto a cliente/estado y limpia filtros', async () => {
    const mock = setup('/circuits?node_id=1&customer_id=1&active=true')
    await screen.findByText('LINE-1')
    expect(screen.getByRole('combobox', { name: 'Filtrar por nodo' })).toHaveValue('Clasificación')
    expect(mock.mock.calls.some(([path]) => path.startsWith('/api/circuits?') && path.includes('node_id=1') && path.includes('customer_id=1') && path.includes('active=true'))).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar Nodo' }))
    expect(params().has('node_id')).toBe(false); expect(params().get('customer_id')).toBe('1')
    await choose('Filtrar por nodo', 'Clasificación')
    expect(params().get('node_id')).toBe('1')
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
    expect(screen.getByTestId('url').textContent).toBe('')
  })
})
