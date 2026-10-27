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
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar todo' }))
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

describe('barra de filtros de tickets', () => {
  const chip = (text: string) => screen.getByText(text).closest('.chip') as HTMLElement
  const panelButton = () => screen.getByRole('button', { name: /^Filtros/ })
  it('el panel avanzado se pliega sin perder valores y «Filtros (n)» cuenta solo los avanzados', () => {
    setup('status=OPEN&search=FOO&node_id=7&sector_id=2')
    expect(panelButton()).toHaveAccessibleName('Filtros (2)')
    expect(panelButton()).toHaveAttribute('aria-expanded', 'false')
    const panel = screen.getByLabelText('Filtros avanzados')
    expect(panel).toHaveAttribute('hidden')
    fireEvent.click(panelButton())
    expect(panelButton()).toHaveAttribute('aria-expanded', 'true')
    expect(panel).not.toHaveAttribute('hidden')
    fireEvent.change(screen.getByLabelText('Desde'), { target: { value: '2026-01-10' } })
    expect(panelButton()).toHaveAccessibleName('Filtros (3)')
    fireEvent.click(panelButton())
    expect(panel).toHaveAttribute('hidden')
    expect(screen.getByLabelText('Desde')).toHaveValue('2026-01-10')
    expect(screen.getByTestId('query')).toHaveTextContent('"status":"OPEN"')
    expect(screen.getByTestId('query')).toHaveTextContent('"node_id":7')
  })
  it('Escape cierra el panel y devuelve el foco al botón', () => {
    setup()
    fireEvent.click(panelButton())
    fireEvent.keyDown(screen.getByLabelText('Desde'), { key: 'Escape' })
    expect(panelButton()).toHaveAttribute('aria-expanded', 'false')
    expect(panelButton()).toHaveFocus()
  })
  it('los filtros avanzados activos siguen visibles como chips con el panel plegado y se quitan uno a uno', () => {
    setup('status=OPEN&search=FOO&sector_id=2&from=2026-01-10')
    expect(screen.getByLabelText('Filtros avanzados')).toHaveAttribute('hidden')
    expect(screen.getByText('Búsqueda: FOO')).toBeInTheDocument()
    expect(screen.getByText('Desde: 2026-01-10')).toBeInTheDocument()
    expect(screen.getByText('Sector: #2')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Quitar filtro Sector: #2' }))
    expect(screen.queryByText('Sector: #2')).not.toBeInTheDocument()
    expect(screen.getByTestId('query')).toHaveTextContent(/"search":"FOO"/)
    fireEvent.click(within(chip('Desde: 2026-01-10')).getByRole('button'))
    expect(screen.getByLabelText('Desde')).toHaveValue('')
    fireEvent.click(screen.getByRole('button', { name: 'Quitar filtro Estado: Abierto' }))
    expect(screen.getByTestId('query')).toHaveTextContent('{"search":"FOO"}')
  })
  it('Estado quitado desde su chip también apaga Sin responsable y Más de 24 h', () => {
    setup('status=OPEN&unassigned=true&age_bucket=gt_24h')
    fireEvent.click(screen.getByRole('button', { name: 'Quitar filtro Estado: Abierto' }))
    expect(screen.getByTestId('query')).toHaveTextContent('{}')
  })
  it('existe una única acción «Limpiar todo», solo con filtros activos', () => {
    setup()
    expect(screen.queryByRole('button', { name: /Limpiar/ })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Buscar tickets'), { target: { value: 'x' } })
    fireEvent.click(panelButton())
    expect(screen.getAllByRole('button', { name: /Limpiar/ })).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar todo' }))
    expect(screen.getByTestId('query')).toHaveTextContent('{}')
    expect(screen.queryByRole('button', { name: /Limpiar/ })).not.toBeInTheDocument()
  })
})
