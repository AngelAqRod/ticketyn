import { fireEvent, render, screen } from '../test/render'
import { describe, expect, it, vi } from 'vitest'
import { CircuitSectorField } from './CircuitSectorField'
import type { Circuit, Sector } from '../types/catalog'
const sectors: Sector[] = [{ id: 1, name: 'Norte', active: true, created_at: '' }, { id: 2, name: 'Sur', active: true, created_at: '' }]
const circuit: Circuit = { id: 1, customer_id: 1, circuit_code: 'C', description: 'Enlace', active: true, created_at: '', sector_id: 1, sector: sectors[0] }

describe('Sector del circuito en formularios operativos', () => {
  it('muestra el Sector asignado como solo lectura', () => {
    const change = vi.fn()
    render(<CircuitSectorField id="sector" circuit={circuit} sectors={sectors} value="" onChange={change} />)
    expect(screen.getByLabelText(/^Sector/)).toHaveValue('Norte')
    expect(screen.getByLabelText(/^Sector/)).toHaveAttribute('readonly')
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(change).not.toHaveBeenCalled()
  })
  it('exige asignación cuando falta y muestra el nuevo Sector al cambiar de circuito', () => {
    const change = vi.fn()
    const view = render(<CircuitSectorField id="sector" circuit={{ ...circuit, sector_id: null, sector: null }} sectors={sectors} value="" onChange={change} />)
    expect(screen.getByRole('combobox')).toBeRequired()
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '2' } })
    expect(change).toHaveBeenCalledWith('2')
    view.rerender(<CircuitSectorField id="sector" circuit={circuit} sectors={sectors} value="2" onChange={change} />)
    expect(screen.getByLabelText(/^Sector/)).toHaveValue('Norte')
  })
})

it('el patrón compartido permite Nodo obligatorio o automático sin relación inventada con Sector', async () => {
  const { CircuitAssignmentField } = await import('./CircuitAssignmentField')
  const changed = vi.fn()
  const view = render(<CircuitAssignmentField field="node" id="node" circuit={{ ...circuit, node_id: null, node: null }} options={sectors} value="" onChange={changed} />)
  expect(screen.getByLabelText(/^Nodo/)).toBeRequired()
  fireEvent.change(screen.getByLabelText(/^Nodo/), { target: { value: '2' } })
  expect(changed).toHaveBeenCalledWith('2')
  view.rerender(<CircuitAssignmentField field="node" id="node" circuit={{ ...circuit, node_id: 2, node: sectors[1] }} options={sectors} value="1" onChange={changed} />)
  expect(screen.getByLabelText(/^Nodo/)).toHaveValue('Sur')
  expect(screen.getByLabelText(/^Nodo/)).toHaveAttribute('readonly')
})
