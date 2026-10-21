import { useState } from 'react'
import { fireEvent, render, screen, within } from '../test/render'
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
  it.each([['Hoy', '2026-01-31'], ['7D', '2026-01-25'], ['15D', '2026-01-17'], ['30D', '2026-01-02']])('%s utiliza el rango local inclusivo hasta hoy', (label, from) => {
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

it('Ayer usa un día completo y al editar pasa a Personalizado', () => {
  setup()
  fireEvent.click(period('Ayer'))
  expect(screen.getByLabelText('Desde')).toHaveValue('2026-01-30')
  expect(screen.getByLabelText('Hasta')).toHaveValue('2026-01-30')
  fireEvent.change(screen.getByLabelText('Hasta'), { target: { value: '2026-01-31' } })
  expect(period('Personalizado')).toHaveAttribute('aria-pressed', 'true')
})

describe('panel colapsable de filtros', () => {
  it('inicia expandido, muestra contador y permite contraer/expandir conservando chips y filtros', () => {
    sessionStorage.clear()
    setup('status=OPEN')
    const toggleButton = screen.getByRole('button', { name: /contraer filtros de tickets/i })
    expect(toggleButton).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByLabelText('1 filtro activo')).toBeInTheDocument()

    const content = document.getElementById('ticket-filters-content')
    expect(content).not.toHaveAttribute('hidden')
    expect(content).toHaveClass('block')
    expect(screen.getByLabelText('Estado')).toHaveValue('OPEN')

    fireEvent.click(toggleButton)
    expect(toggleButton).toHaveAttribute('aria-expanded', 'false')
    expect(toggleButton).toHaveAccessibleName('Expandir filtros de tickets')
    expect(content).toHaveAttribute('hidden')
    expect(content).toHaveClass('hidden')

    expect(screen.getByLabelText('1 filtro activo')).toBeInTheDocument()
    expect(screen.getByLabelText('Filtros activos')).toBeInTheDocument()
    expect(screen.getByText('Estado: Abierto')).toBeInTheDocument()
    expect(screen.getByTestId('query')).toHaveTextContent('{"status":"OPEN"}')

    fireEvent.click(toggleButton)
    expect(toggleButton).toHaveAttribute('aria-expanded', 'true')
    expect(content).not.toHaveAttribute('hidden')
    expect(content).toHaveClass('block')
    expect(screen.getByLabelText('Estado')).toHaveValue('OPEN')
  })

  it('restaura el estado contraído guardado en sessionStorage dentro de la sesión', () => {
    sessionStorage.setItem('ticketyn_ticket_filters_expanded', 'false')
    setup('search=FOO')
    const toggleButton = screen.getByRole('button', { name: /expandir filtros de tickets/i })
    expect(toggleButton).toHaveAttribute('aria-expanded', 'false')
    const content = document.getElementById('ticket-filters-content')
    expect(content).toHaveAttribute('hidden')
    expect(screen.getByText('Búsqueda: FOO')).toBeInTheDocument()
    sessionStorage.clear()
  })
})
