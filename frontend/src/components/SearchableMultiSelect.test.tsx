import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { SearchableMultiSelect } from './SearchableMultiSelect'

const options = [
  { value: '1', label: 'Ana Torres' },
  { value: '2', label: 'Luis Pérez' },
  { value: '3', label: 'Persona histórica', disabled: true },
]
function Example({ initial = [], disabled = false }: { initial?: string[]; disabled?: boolean }) {
  const [value, setValue] = useState(initial)
  return <><label htmlFor="support">Personal de apoyo</label><SearchableMultiSelect id="support" label="Personal de apoyo" value={value} options={options} onChange={setValue} disabled={disabled} placeholder="Sin personal de apoyo" aria-describedby="support-help" /><p id="support-help">Opcional</p><output data-testid="selected">{JSON.stringify(value)}</output><button type="button">Fuera</button></>
}

describe('SearchableMultiSelect', () => {
  it('admite campo vacío con placeholder y sin obligación de seleccionar', () => {
    render(<Example />)
    const input = screen.getByRole('combobox', { name: 'Personal de apoyo' })
    expect(input).toHaveValue('')
    expect(input).toHaveAttribute('placeholder', 'Sin personal de apoyo')
    expect(input).toHaveAttribute('aria-required', 'false')
    expect(input).toHaveAttribute('aria-describedby', 'support-help')
    expect(screen.getByTestId('selected')).toHaveTextContent('[]')
    expect(screen.queryByRole('button', { name: /^Quitar/ })).not.toBeInTheDocument()
  })
  it('busca por nombre y agrega varias personas con clic normal, sin duplicados', () => {
    render(<Example />)
    const input = screen.getByRole('combobox')
    fireEvent.change(input, { target: { value: 'TORRES' } })
    expect(screen.getAllByRole('option')).toHaveLength(1)
    fireEvent.click(screen.getByRole('option', { name: 'Ana Torres' }))
    expect(screen.getByRole('button', { name: 'Quitar Ana Torres' })).toBeInTheDocument()
    fireEvent.click(input)
    expect(screen.queryByRole('option', { name: 'Ana Torres' })).not.toBeInTheDocument()
    fireEvent.change(input, { target: { value: 'Luis' } })
    fireEvent.click(screen.getByRole('option', { name: 'Luis Pérez' }))
    expect(screen.getByTestId('selected')).toHaveTextContent('["1","2"]')
    expect(screen.getAllByRole('button', { name: /^Quitar/ })).toHaveLength(2)
  })
  it('conserva asignaciones iniciales, permite quitar cada chip y deja cero participantes', () => {
    render(<Example initial={['1', '2']} />)
    fireEvent.click(screen.getByRole('button', { name: 'Quitar Ana Torres' }))
    expect(screen.getByTestId('selected')).toHaveTextContent('["2"]')
    expect(screen.getByRole('combobox')).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: 'Quitar Luis Pérez' }))
    expect(screen.getByTestId('selected')).toHaveTextContent('[]')
    expect(screen.getByRole('combobox')).toHaveAttribute('placeholder', 'Sin personal de apoyo')
  })
  it('reutiliza flechas, Enter y Escape y mantiene botones de eliminación accesibles', () => {
    render(<Example />)
    const input = screen.getByRole('combobox')
    input.focus()
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(screen.getByTestId('selected')).toHaveTextContent('["1"]')
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(screen.getByTestId('selected')).toHaveTextContent('["1","2"]')
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(input).toHaveAttribute('aria-expanded', 'false')
    const remove = screen.getByRole('button', { name: 'Quitar Ana Torres' })
    expect(remove).toHaveAttribute('type', 'button')
    remove.focus()
    expect(remove).toHaveFocus()
    fireEvent.click(remove)
    expect(input).toHaveFocus()
  })
  it('muestra personas históricas inactivas y permite retirarlas sin reasignarlas', () => {
    render(<Example initial={['3']} />)
    fireEvent.click(screen.getByRole('button', { name: 'Quitar Persona histórica' }))
    expect(screen.getByTestId('selected')).toHaveTextContent('[]')
    const inactive = screen.getByRole('option', { name: /^Persona histórica/ })
    expect(inactive).toHaveAttribute('aria-disabled', 'true')
    fireEvent.click(inactive)
    expect(screen.getByTestId('selected')).toHaveTextContent('[]')
  })
  it('limpia todos y bloquea modificaciones mientras está deshabilitado', () => {
    const view = render(<Example initial={['1', '2']} disabled />)
    expect(screen.getByRole('combobox')).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Quitar Ana Torres' }))
    expect(screen.getByTestId('selected')).toHaveTextContent('["1","2"]')
    expect(screen.getByRole('button', { name: 'Limpiar personal de apoyo' })).toBeDisabled()
    view.unmount()
    render(<Example initial={['1', '2']} />)
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar personal de apoyo' }))
    expect(screen.getByTestId('selected')).toHaveTextContent('[]')
  })
})
