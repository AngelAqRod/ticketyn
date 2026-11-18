import { afterEach, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { CircuitLocationData } from './CircuitLocationData'
afterEach(cleanup)
it('shows address, readable coordinates, a plain Maps link and multiline notes', () => {
  render(<CircuitLocationData site={{ address: '3a calle 5-10 zona 1', latitude: '14.634915', longitude: '-90.506882', additional_notes: 'Llave en recepción\nSegundo piso' }} />)
  expect(screen.getByText('3a calle 5-10 zona 1')).toBeVisible(); expect(screen.getByText('14.634915, -90.506882')).toBeVisible()
  const link = screen.getByRole('link', { name: 'Ver en Google Maps' })
  expect(link).toHaveAttribute('href', 'https://www.google.com/maps/search/?api=1&query=14.634915%2C-90.506882'); expect(link).toHaveAttribute('rel', 'noopener noreferrer'); expect(link).toHaveAttribute('target', '_blank')
  expect(screen.getByText(/Llave en recepción/)).toHaveClass('whitespace-pre-wrap')
})
it('reports missing data instead of inventing values and offers no link without coordinates', () => {
  render(<CircuitLocationData site={{ address: null, latitude: null, longitude: null, additional_notes: null }} />)
  expect(screen.getAllByText('No disponible')).toHaveLength(3); expect(screen.queryByRole('link')).not.toBeInTheDocument()
})
it('does not offer the action when only one coordinate is stored', () => {
  render(<CircuitLocationData site={{ address: null, latitude: '14.5', longitude: null, additional_notes: null }} />)
  expect(screen.queryByRole('link', { name: 'Ver en Google Maps' })).not.toBeInTheDocument()
})
it('can omit the notes when the caller shows them in their own box', () => {
  render(<CircuitLocationData showNotes={false} site={{ address: 'Zona 1', latitude: null, longitude: null, additional_notes: 'Oculta aquí' }} />)
  expect(screen.queryByText('Notas adicionales')).not.toBeInTheDocument(); expect(screen.queryByText('Oculta aquí')).not.toBeInTheDocument(); expect(screen.getByText('Zona 1')).toBeVisible()
})
