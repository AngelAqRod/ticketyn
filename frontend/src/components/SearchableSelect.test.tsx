import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { SearchableSelect } from './SearchableSelect'

const options = [{ value: '1', label: 'SGgt — Cliente de prueba' }, { value: '2', label: 'OTHER — Segundo cliente' }, { value: '3', label: 'OLD — Histórico', disabled: true }]
function Example({ disabled = false, initial = '', empty = false }: { disabled?: boolean; initial?: string; empty?: boolean }) {
  const [value, setValue] = useState(initial)
  return <><label htmlFor="example">Cliente</label><SearchableSelect id="example" label="Cliente" value={value} onChange={setValue} options={empty ? [] : options} disabled={disabled} placeholder="Selecciona un cliente" emptyMessage="Catálogo vacío" noMatchMessage="No se encontraron clientes." /><output data-testid="selected">{value}</output></>
}

describe('SearchableSelect', () => {
  it('abre al hacer clic, filtra sin importar mayúsculas y selecciona con mouse', () => {
    render(<Example />)
    const input = screen.getByRole('combobox', { name: 'Cliente' })
    fireEvent.click(input)
    expect(input).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getAllByRole('option')).toHaveLength(3)
    fireEvent.change(input, { target: { value: 'PRUEBA' } })
    expect(screen.getAllByRole('option')).toHaveLength(1)
    fireEvent.click(screen.getByRole('option', { name: 'SGgt — Cliente de prueba' }))
    expect(input).toHaveValue('SGgt — Cliente de prueba')
    expect(screen.getByTestId('selected')).toHaveTextContent('1')
    expect(input).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
  it('ArrowDown/ArrowUp recorren opciones activas y Enter selecciona sin enviar', () => {
    render(<Example />)
    const input = screen.getByRole('combobox')
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    expect(input).toHaveAttribute('aria-activedescendant', 'example-option-0')
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    expect(input).toHaveAttribute('aria-activedescendant', 'example-option-1')
    fireEvent.keyDown(input, { key: 'ArrowUp' })
    expect(input).toHaveAttribute('aria-activedescendant', 'example-option-0')
    fireEvent.keyDown(input, { key: 'ArrowUp' })
    expect(input).toHaveAttribute('aria-activedescendant', 'example-option-1')
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(screen.getByTestId('selected')).toHaveTextContent('2')
    expect(input).toHaveAttribute('aria-expanded', 'false')
  })
  it('Escape cierra y restaura la etiqueta seleccionada sin cambiar el ID', () => {
    render(<Example initial="1" />)
    const input = screen.getByRole('combobox')
    fireEvent.click(input); fireEvent.change(input, { target: { value: 'OTHER' } })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(input).toHaveValue(options[0].label)
    expect(input).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByTestId('selected')).toHaveTextContent('1')
  })
  it('permite limpiar búsqueda y selección por separado', () => {
    render(<Example initial="1" />)
    const input = screen.getByRole('combobox')
    fireEvent.click(input); fireEvent.change(input, { target: { value: 'OTHER' } })
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar búsqueda' }))
    expect(screen.getAllByRole('option')).toHaveLength(3)
    expect(screen.getByTestId('selected')).toHaveTextContent('1')
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar Cliente' }))
    expect(input).toHaveValue(''); expect(screen.getByTestId('selected')).toBeEmptyDOMElement()
  })
  it('cierra por pérdida de foco y clic fuera', () => {
    render(<><Example /><button type="button">Fuera</button></>)
    const input = screen.getByRole('combobox')
    fireEvent.click(input)
    fireEvent.blur(input, { relatedTarget: screen.getByRole('button', { name: 'Fuera' }) })
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    fireEvent.click(input)
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Fuera' }))
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
  it('disabled impide abrir o modificar', () => {
    render(<Example disabled initial="1" />)
    expect(screen.getByRole('combobox')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Abrir Cliente' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Limpiar Cliente' })).toBeDisabled()
    fireEvent.click(screen.getByRole('combobox'))
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
  it('distingue catálogo vacío de búsqueda sin coincidencias y Enter no elige un ID', () => {
    const view = render(<Example />)
    const input = screen.getByRole('combobox')
    fireEvent.change(input, { target: { value: 'NO-MATCH' } })
    expect(screen.getByText('No se encontraron clientes.')).toBeInTheDocument()
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(screen.getByTestId('selected')).toBeEmptyDOMElement()
    view.unmount(); render(<Example empty />)
    fireEvent.click(screen.getByRole('combobox'))
    expect(screen.getByText('Catálogo vacío')).toBeInTheDocument()
    fireEvent.keyDown(screen.getByRole('combobox'), { key: 'ArrowDown' })
    expect(screen.getByRole('combobox')).not.toHaveAttribute('aria-activedescendant')
  })
  it('muestra un valor histórico inactivo pero no permite seleccionarlo de nuevo', () => {
    render(<Example initial="3" />)
    expect(screen.getByRole('combobox')).toHaveValue('OLD — Histórico')
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar Cliente' }))
    fireEvent.click(screen.getByRole('combobox'))
    const historical = screen.getByRole('option', { name: /OLD — Histórico/ })
    expect(historical).toHaveAttribute('aria-disabled', 'true')
    fireEvent.click(historical)
    expect(screen.getByTestId('selected')).toBeEmptyDOMElement()
  })
})

it('usa iconos decorativos conservando labels y tipo de las acciones', () => {
  render(<Example initial="1" />)
  for (const name of ['Limpiar Cliente', 'Abrir Cliente']) {
    const button = screen.getByRole('button', { name })
    expect(button).toHaveAttribute('type', 'button')
    expect(button.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    expect(button).toHaveClass('combobox-action')
  }
})
