import { useState } from 'react'
import { fireEvent, render, screen } from '../test/render'
import { describe, expect, it, vi } from 'vitest'
import { FilterBar, FilterPanelGroup, type FilterBarTheme } from './FilterBar'

function Harness({ theme, onClear = () => {} }: { theme?: FilterBarTheme; onClear?: () => void }) {
  const [text, setText] = useState('hola')
  const [removed, setRemoved] = useState(false)
  return <FilterBar label="Filtros de prueba" theme={theme} panelCount={1} onClear={onClear}
    search={<input aria-label="Buscar" value={text} onChange={(event) => setText(event.target.value)} />}
    quick={<button type="button">Rápido</button>}
    panel={<FilterPanelGroup title="Grupo"><input aria-label="Avanzado" defaultValue="valor" /></FilterPanelGroup>}
    chips={removed ? [] : [{ label: 'Cliente', value: '200', onRemove: () => setRemoved(true) }, { label: 'Fijo', value: 'sí' }]} />
}

describe('FilterBar', () => {
  it('renderiza búsqueda, rápidos, contador y chips', () => {
    render(<Harness />)
    expect(screen.getByRole('region', { name: 'Filtros de prueba' })).toBeInTheDocument()
    expect(screen.getByLabelText('Buscar')).toHaveValue('hola')
    expect(screen.getByRole('button', { name: 'Rápido' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Filtros (1)' })).toBeInTheDocument()
    expect(screen.getByText('Cliente: 200')).toBeInTheDocument()
  })
  it('abre y cierra el panel por teclado conservando los valores', () => {
    render(<Harness />)
    const button = screen.getByRole('button', { name: 'Filtros (1)' })
    const field = screen.getByLabelText('Avanzado', { selector: 'input' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByLabelText('Filtros avanzados')).toHaveAttribute('hidden')
    fireEvent.change(field, { target: { value: 'otro' } })
    button.focus(); fireEvent.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(button).toHaveAttribute('aria-controls', screen.getByRole('group', { name: 'Filtros avanzados' }).id)
    fireEvent.click(button)
    expect(screen.getByLabelText('Avanzado', { selector: 'input' })).toHaveValue('otro')
  })
  it('el chip se quita con un botón real y etiquetado; los chips sin onRemove no lo muestran', () => {
    render(<Harness />)
    expect(screen.getAllByRole('button', { name: /^Quitar filtro/ })).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Quitar filtro Cliente: 200' }))
    expect(screen.queryByText('Cliente: 200')).not.toBeInTheDocument()
  })
  it('«Limpiar todo» solo aparece con chips y llama a onClear', () => {
    const onClear = vi.fn()
    render(<Harness onClear={onClear} />)
    fireEvent.click(screen.getByRole('button', { name: 'Limpiar todo' }))
    expect(onClear).toHaveBeenCalledOnce()
    fireEvent.click(screen.getByRole('button', { name: 'Quitar filtro Cliente: 200' }))
    expect(screen.queryByRole('button', { name: 'Limpiar todo' })).not.toBeInTheDocument()
  })
  it.each(['blue', 'purple', 'cyan', 'emerald'] as const)('aplica la variante de color %s', (theme) => {
    render(<Harness theme={theme} />)
    expect(screen.getByRole('region', { name: 'Filtros de prueba' })).toHaveClass(`filter-bar--${theme}`)
  })
})
