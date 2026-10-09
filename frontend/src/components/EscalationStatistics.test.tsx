import { useState } from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { EscalationStatistics } from './EscalationStatistics'
import { jsonResponse } from '../test/fixtures'
vi.mock('./ReportCharts', () => ({
  TrendChart: ({ title }: { title: string }) => <div role="img" aria-label={title} />,
  DistributionChart: ({ title }: { title: string }) => <div role="img" aria-label={title} />,
  RankingChart: ({ title }: { title: string }) => <div role="img" aria-label={title} />,
}))
function setup(fail = false) {
  const mock = vi.fn((path: string) => {
    if (path.includes('/responsibles?')) return Promise.resolve(jsonResponse([{ id: 2, name: 'Especialista', active: false, created_at: '2026-10-09T00:00:00Z' }]))
    if (path.includes('/tickets?')) return Promise.resolve(jsonResponse(fail ? { detail: 'Estadísticas no disponibles.' } : [{ id: 1, reference: 'T-1', title: 'Incidente', status: 'OPEN' }], fail ? 503 : 200))
    return Promise.resolve(jsonResponse(fail ? { detail: 'Estadísticas no disponibles.' } : { total_tickets: 4, escalated_tickets: 1, events: 3, active: 2, finished: 1, average_duration_seconds: 3600, escalated_percentage: 25, granularity: 'day', trend: [], recipients: [{ id: 2, label: 'Especialista', count: 3 }] }, fail ? 503 : 200))
  })
  vi.stubGlobal('fetch', mock)
  function Controlled() {
    const [recipient, setRecipient] = useState('')
    return <EscalationStatistics query={{ timezone: 'UTC', node_id: 5, ...(recipient ? { recipient_id: Number(recipient) } : {}) }} people={[{ id: 2, name: 'Especialista', active: false, created_at: '2026-10-09T00:00:00Z' }]} summary={fail ? null : { total_tickets: 4, escalated_tickets: 1, events: 3, active: 2, finished: 1, average_duration_seconds: 3600, escalated_percentage: 25, granularity: 'day', trend: [], recipients: [{ id: 2, label: 'Especialista', count: 3, customer_id: null, customer_code: null, customer_name: null }] }} onRecipientChange={setRecipient} />
  }
  render(<MemoryRouter><Controlled /></MemoryRouter>)
  return mock
}
describe('Estadísticas de escalamientos', () => {
  it('distingue tickets de eventos y no presenta gráficos por motivo', async () => {
    const mock = setup()
    expect(await screen.findByText('25.0 %')).toBeInTheDocument()
    expect(screen.getByText('Tickets únicos escalados').nextElementSibling).toHaveTextContent('1')
    expect(screen.getByText('Eventos de escalamiento').nextElementSibling).toHaveTextContent('3')
    expect(screen.getByRole('link', { name: 'T-1' })).toHaveAttribute('href', '/tickets/1')
    expect(screen.getAllByRole('img')).toHaveLength(3)
    const query = new URL(mock.mock.calls.find(([url]) => url.includes('/tickets?'))![0], 'http://local').searchParams
    expect(query.get('node_id')).toBe('5'); expect(query.has('from')).toBe(false)
  })
  it('selección de persona y ranking filtran destinatario, no responsable principal', async () => {
    const mock = setup(); await screen.findByText('25.0 %')
    fireEvent.click(screen.getByRole('combobox', { name: 'Escalamientos recibidos por' }))
    fireEvent.click(await screen.findByRole('option', { name: 'Especialista' }))
    await waitFor(() => expect(mock.mock.calls.some(([path]) => path.includes('recipient_id=2'))).toBe(true))
    expect(mock.mock.calls.every(([path]) => !path.includes('responsible_id='))).toBe(true)
    await screen.findByText('25.0 %')
    fireEvent.click(screen.getByRole('button', { name: 'Ver ranking completo (1)' }))
    fireEvent.click(within(screen.getByRole('table', { name: 'Escalamientos recibidos por persona' })).getByRole('button', { name: 'Especialista' }))
    expect(screen.getByRole('combobox', { name: 'Escalamientos recibidos por' })).toHaveValue('Especialista')
  })
  it('no contiene selector independiente ni solicita métricas redundantes', async () => {
    const mock = setup(); await screen.findByRole('link', { name: 'T-1' })
    expect(screen.queryByRole('group', { name: 'Período de escalamientos' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Desde')).not.toBeInTheDocument()
    expect(mock.mock.calls.every(([url]) => url.includes('/escalations/tickets?'))).toBe(true)
  })
  it('errores son recuperables y no muestran métricas inventadas', async () => {
    setup(true)
    expect(await screen.findByRole('alert')).toHaveTextContent('Estadísticas no disponibles.')
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
    expect(screen.queryByText('25.0 %')).not.toBeInTheDocument()
  })
})
