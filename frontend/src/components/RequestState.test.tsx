import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { RequestState } from './RequestState'
import { FeedbackMessage } from './FeedbackMessage'

describe('estados compartidos', () => {
  it('permite loading compacto configurable y prioriza la solicitud en curso', () => {
    render(<RequestState compact loading error="Anterior" loadingText="Cargando nodos..." />)
    expect(screen.getByRole('status')).toHaveTextContent('Cargando nodos...')
    expect(screen.getByRole('status')).not.toHaveClass('panel')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
  it('conserva IDs accesibles y ejecuta el reintento configurado sin enviar formularios', () => {
    const retry = vi.fn()
    render(<form><input aria-describedby="node-error" /><RequestState compact id="node-error" error="No disponible" errorTitle="" retryText="Reintentar nodos" onRetry={retry} /></form>)
    expect(screen.getByRole('alert')).toHaveAttribute('id', 'node-error')
    const button = screen.getByRole('button', { name: 'Reintentar nodos' })
    expect(button).toHaveAttribute('type', 'button')
    fireEvent.click(button)
    expect(retry).toHaveBeenCalledTimes(1)
  })
  it('anuncia el estado vacío sin inventar mensajes adicionales', () => {
    render(<RequestState empty emptyTitle="No hay clientes registrados." emptyDescription="" />)
    expect(screen.getByRole('status')).toHaveTextContent('No hay clientes registrados.')
    expect(screen.queryByText('No se encontraron registros en esta página.')).not.toBeInTheDocument()
  })
  it('no muestra un estado cuando la solicitud no lo requiere', () => {
    const { container } = render(<RequestState />)
    expect(container).toBeEmptyDOMElement()
  })
  it('feedback success/error conserva contenido, roles e identificación', () => {
    const { rerender } = render(<FeedbackMessage variant="success">Cambios guardados.</FeedbackMessage>)
    expect(screen.getByRole('status')).toHaveTextContent('Cambios guardados.')
    rerender(<FeedbackMessage variant="error" id="form-error">Error original.</FeedbackMessage>)
    expect(screen.getByRole('alert')).toHaveAttribute('id', 'form-error')
    expect(screen.getByRole('alert')).toHaveTextContent('Error original.')
  })
})
