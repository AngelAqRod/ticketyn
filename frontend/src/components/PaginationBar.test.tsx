import { fireEvent, render, screen } from '../test/render'
import { describe, expect, it, vi } from 'vitest'
import { PaginationBar } from './PaginationBar'

describe('Paginación operativa compartida', () => {
  it('conserva información y callbacks, con página actual sin navegación arbitraria', () => {
    const previous = vi.fn(), next = vi.fn()
    render(<PaginationBar page={2} info={<span>Página 2 · Registros 51–100</span>} previousDisabled={false} nextDisabled={false} onPrevious={previous} onNext={next} />)
    expect(screen.getByText('Página 2 · Registros 51–100')).toBeInTheDocument()
    const current = screen.getByLabelText('Página 2')
    expect(current).toHaveAttribute('aria-current', 'page')
    expect(current.tagName).toBe('SPAN')
    expect(screen.getAllByRole('button')).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'Anterior' }))
    fireEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
    expect(previous).toHaveBeenCalledTimes(1)
    expect(next).toHaveBeenCalledTimes(1)
  })
  it('respeta primera/última página y bloqueos de carga sin llamar callbacks', () => {
    const callback = vi.fn()
    const { rerender } = render(<PaginationBar page={1} info="Página 1" previousDisabled nextDisabled onPrevious={callback} onNext={callback} />)
    for (const button of screen.getAllByRole('button')) { expect(button).toBeDisabled(); fireEvent.click(button) }
    expect(callback).not.toHaveBeenCalled()
    rerender(<PaginationBar page={3} info="Página 3" previousDisabled={false} nextDisabled onPrevious={callback} onNext={callback} />)
    expect(screen.getByLabelText('Página 3')).toHaveTextContent('3')
    expect(screen.getByRole('button', { name: 'Anterior' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Siguiente' })).toBeDisabled()
  })
  it('mantiene las etiquetas accesibles específicas de cada listado', () => {
    render(<PaginationBar page={1} info="Página 1" previousDisabled nextDisabled={false} onPrevious={() => {}} onNext={() => {}} previousLabel="Página anterior de tickets escalados" nextLabel="Página siguiente de tickets escalados" />)
    expect(screen.getByRole('button', { name: 'Página anterior de tickets escalados' })).toBeDisabled()
    screen.getByRole('button', { name: 'Página siguiente de tickets escalados' }).focus()
    expect(screen.getByRole('button', { name: 'Página siguiente de tickets escalados' })).toHaveFocus()
  })
})
