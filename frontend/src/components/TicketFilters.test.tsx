import { useState } from 'react'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TicketFilters } from './TicketFilters'
import { ticketQuery, localDateBoundary } from '../lib/ticketFilters'
import { jsonResponse } from '../test/fixtures'
function Harness({ initial = '' }: { initial?: string }) {
  const [params, setParams] = useState(new URLSearchParams(initial))
  return <><TicketFilters params={params} change={(values) => setParams((current) => {
    const next = new URLSearchParams(current)
    Object.entries(values).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key))
    return next
  })} clear={() => setParams(new URLSearchParams())} /><output data-testid="query">{JSON.stringify(ticketQuery(params).query)}</output></>
}
const period = (name: string) => within(screen.getByRole('group', { name: 'Período de tickets' })).getByRole('button', { name })
function setup(initial?: string) {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(2026, 0, 31, 12))
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse([]))))
  render(<Harness initial={initial} />)
}
afterEach(() => vi.useRealTimers())
describe('período de tickets', () => {
  it('Todos predeterminado y sin fechas conserva otros filtros', () => {
    setup('status=OPEN')
    expect(period('Todos')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('query')).toHaveTextContent('{"status":"OPEN"}')
    fireEvent.click(period('7D'))
    fireEvent.click(period('Todos'))
    expect(screen.getByLabelText('Desde')).toHaveValue('')
    expect(screen.getByLabelText('Hasta')).toHaveValue('')
    expect(screen.getByTestId('query')).toHaveTextContent('{"status":"OPEN"}')
  })
  it.each([['1D', '2026-01-31'], ['7D', '2026-01-25'], ['15D', '2026-01-17'], ['30D', '2026-01-02']])('%s utiliza el rango local inclusivo hasta hoy', (label, from) => {
    setup()
    fireEvent.click(period(label))
    expect(period(label)).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Desde')).toHaveValue(from)
    expect(screen.getByLabelText('Hasta')).toHaveValue('2026-01-31')
    expect(JSON.parse(screen.getByTestId('query').textContent!)).toEqual({ from: localDateBoundary(from), to: localDateBoundary('2026-01-31', true) })
  })
  it.each(['Desde', 'Hasta'])('editar %s selecciona Personalizado; limpiar vuelve a Todos', (label) => {
    setup()
    fireEvent.click(period('7D'))
    fireEvent.change(screen.getByLabelText(label), { target: { value: '2026-01-26' } })
    expect(period('Personalizado')).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar filtros' }))
    expect(period('Todos')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Desde')).toHaveValue('')
    expect(screen.getByLabelText('Hasta')).toHaveValue('')
  })
  it('fechas de URL son Personalizado y seleccionarlo conserva el rango', () => {
    setup('from=2026-01-10&to=2026-01-20')
    expect(period('Personalizado')).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(period('Personalizado'))
    expect(screen.getByLabelText('Desde')).toHaveValue('2026-01-10')
    expect(screen.getByLabelText('Hasta')).toHaveValue('2026-01-20')
  })
})
