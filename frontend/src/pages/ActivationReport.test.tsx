import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { ActivationDetail } from './ActivationDetail'
import { jsonResponse } from '../test/fixtures'

const created_at = '2020-01-01T12:00:00Z'
const person = { id: 1, name: 'Operador', active: true, created_at }
const circuit = { id: 8, customer_id: 3, circuit_code: 'C-8', description: 'Enlace principal', active: true, created_at }
const activation = { id: 42, reference: 'ACT-000042', circuit_id: 8, circuit, responsible: person, responsible_id: 1, effective_at: created_at, created_at }
const notification = { activation_id: 42, mode: 'DISABLED', state: null, revision: 0, processor_paused: false, can_request: false }
function setup(mode?: 'pending' | 'error') {
  vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn(() => 'blob:activation'); static revokeObjectURL = vi.fn() })
  const downloads: string[] = []
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function(this: HTMLAnchorElement) { downloads.push(this.download) })
  const mock = vi.fn((path: string) => {
    if (path.startsWith('/api/activations/42/reports/pdf')) {
      if (mode === 'pending') return new Promise<Response>(() => {})
      return Promise.resolve(mode === 'error' ? jsonResponse({ detail: 'No se pudo generar el reporte de la activación.' }, 500) : new Response(new Blob(['%PDF'])))
    }
    if (path === '/api/activations/42') return Promise.resolve(jsonResponse(activation))
    if (path === '/api/activations/42/notification') return Promise.resolve(jsonResponse(notification))
    if (path.startsWith('/api/activations/42/interventions')) return Promise.resolve(jsonResponse(Array.from({ length: 50 }, (_, i) => ({ id: i, responsible: person, occurred_at: created_at, content: 'Trabajo visible' }))))
    if (path.startsWith('/api/customers/3')) return Promise.resolve(jsonResponse({ id: 3, name: 'Cliente', customer_code: 'C-3', active: true, created_at }))
    return Promise.resolve(jsonResponse([person]))
  })
  vi.stubGlobal('fetch', mock)
  render(<MemoryRouter initialEntries={['/activations/42']}><Routes><Route path="/activations/:id" element={<ActivationDetail />} /></Routes></MemoryRouter>)
  return { mock, downloads }
}

describe('PDF individual de activación', () => {
  it('descarga el ID consultado desde la cabecera, independientemente de la página de bitácora', async () => {
    const { mock, downloads } = setup()
    await screen.findByRole('heading', { name: 'ACT-000042' })
    const button = screen.getByRole('button', { name: 'Exportar PDF' })
    expect(screen.getByRole('heading', { name: 'ACT-000042' }).closest('.page-heading')).toContainElement(button)
    expect(button).toHaveClass('button-secondary')
    expect(screen.getByRole('button', { name: 'Nueva intervención' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
    await screen.findByText('Página 2')
    fireEvent.click(screen.getByRole('button', { name: 'Exportar PDF' }))
    await waitFor(() => expect(downloads).toEqual(['ticketyn-activacion-42.pdf']))
    const path = mock.mock.calls.find(([path]) => path.includes('/reports/pdf'))![0]
    expect(path).toBe('/api/activations/42/reports/pdf?timezone=America%2FGuatemala')
    expect(path).not.toContain('offset'); expect(path).not.toContain('limit')
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:activation')
  })
  it('muestra progreso y bloquea envíos duplicados sin alterar las otras acciones', async () => {
    const { mock } = setup('pending')
    const button = await screen.findByRole('button', { name: 'Exportar PDF' })
    fireEvent.click(button); fireEvent.click(button)
    expect(await screen.findByText('Generando archivo...')).toBeInTheDocument()
    expect(button).toBeDisabled()
    expect(mock.mock.calls.filter(([path]) => path.includes('/reports/pdf'))).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Nueva intervención' })).toBeEnabled()
  })
  it('muestra error sin perder la activación ni la bitácora', async () => {
    setup('error')
    fireEvent.click(await screen.findByRole('button', { name: 'Exportar PDF' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo generar el reporte de la activación.')
    expect(screen.getByRole('heading', { name: 'ACT-000042' })).toBeInTheDocument()
    expect(screen.getAllByText('Trabajo visible')).toHaveLength(50)
    expect(screen.getByRole('button', { name: 'Exportar PDF' })).toBeEnabled()
  })
})

it('muestra condiciones históricas sin completar desde el circuito actual', async () => {
  const mock=vi.fn((path:string)=>Promise.resolve(jsonResponse(path==='/api/activations/42/notification'?notification:path==='/api/activations/42'?{ ...activation, cpe_activation:'MikroTik original', service_type_name:'Internet original', initial_capacity:'1758.5', initial_capacity_unit:'Mbps', circuit:{...circuit, cpe_model:{name:'NO MOSTRAR CPE ACTUAL'}, service_type:{name:'NO MOSTRAR ACTUAL'}, initial_capacity:'9', initial_capacity_unit:'Gbps'} }:path.includes('/interventions')?[]:path.includes('/customers/3')?{id:3,name:'Cliente'}:[person])))
  vi.stubGlobal('fetch',mock)
  render(<MemoryRouter initialEntries={['/activations/42']}><Routes><Route path="/activations/:id" element={<ActivationDetail />} /></Routes></MemoryRouter>)
  expect(await screen.findByText('Internet original')).toBeInTheDocument()
  expect(screen.getByText('MikroTik original')).toBeInTheDocument()
  expect(screen.queryByText('NO MOSTRAR CPE ACTUAL')).not.toBeInTheDocument()
  expect(screen.getByText('1.759 Gbps')).toBeInTheDocument()
  expect(screen.queryByText('NO MOSTRAR ACTUAL')).not.toBeInTheDocument()
  expect(screen.queryByText('9 Gbps')).not.toBeInTheDocument()
})


it('muestra Sin registrar para el CPE histórico ausente', async () => {
  setup()
  const label = await screen.findByText('CPE de activación')
  expect(label.nextElementSibling).toHaveTextContent('Sin registrar')
})
