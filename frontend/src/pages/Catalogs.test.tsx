import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Catalogs } from './Catalogs'

vi.mock('../components/CatalogAdmin', () => ({ CatalogAdmin: ({ kind }: { kind: string }) => <div data-testid="catalog-content">{kind}</div> }))

describe('selector de Catálogos', () => {
  it('conserva el orden canónico y cambia únicamente el catálogo seleccionado', () => {
    render(<Catalogs />)
    const nav = screen.getByRole('navigation', { name: 'Catálogos' })
    const buttons = within(nav).getAllByRole('button')
    expect(buttons.map(button => button.textContent)).toEqual(['Sectores', 'Departamentos', 'Tipos de incidencia', 'Nodos', 'Responsables', 'Puestos', 'Motivos de escalamiento', 'Tipos de servicio', 'Motivos de baja', 'Modelos de CPE'])
    expect(buttons[0]).toHaveAttribute('aria-pressed', 'true')
    buttons.forEach((button, index) => {
      fireEvent.click(button)
      expect(button).toHaveAttribute('aria-pressed', 'true')
      expect(buttons.filter(item => item.getAttribute('aria-pressed') === 'true')).toHaveLength(1)
      expect(screen.getByTestId('catalog-content')).toHaveTextContent(['sectors', 'departments', 'incident-types', 'nodes', 'responsibles', 'positions', 'escalation-reasons', 'service-types', 'deactivation-reasons', 'cpe-models'][index])
    })
  })
})
