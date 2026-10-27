import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { PageHeading, type PageHeadingProps } from './PageHeading'

afterEach(cleanup)

function renderHeading(props: Partial<PageHeadingProps> = {}, route = '/my-tickets') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <PageHeading title="Título" description="Descripción breve" {...props} />
    </MemoryRouter>,
  )
}

describe('PageHeading', () => {
  it('variante A: sin stats no renderiza región de indicadores ni tarjetas vacías', () => {
    renderHeading({ action: <button type="button">Actualizar</button> })
    expect(screen.getByRole('heading', { level: 1, name: 'Título' })).toBeInTheDocument()
    expect(screen.getByText('Descripción breve')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Actualizar' })).toBeInTheDocument()
    expect(screen.queryByRole('region')).not.toBeInTheDocument()
    expect(document.querySelector('.heading-stat')).toBeNull()
  })

  it('variante B: renderiza indicadores con etiqueta, valor y tono semántico', () => {
    renderHeading({
      statsLabel: 'Resumen de prueba',
      stats: [
        { label: 'Abiertos', value: 4, tone: 'open' },
        { label: 'Sin responsable', value: 1, tone: 'unassigned' },
        { label: 'Más de 24 h', value: 2, tone: 'age' },
        { label: 'Escalamientos', value: 3 },
      ],
    })
    const region = screen.getByRole('region', { name: 'Resumen de prueba' })
    const items = within(region).getAllByRole('listitem')
    expect(items).toHaveLength(4)
    expect(items[0]).toHaveClass('heading-stat--open')
    expect(items[1]).toHaveClass('heading-stat--unassigned')
    expect(items[2]).toHaveClass('heading-stat--age')
    expect(items[3]).toHaveClass('heading-stat--accent')
    expect(items[2]).toHaveTextContent('Más de 24 h2')
  })

  it('distingue cero, carga y dato no disponible sin convertir ausencia en cero', () => {
    renderHeading({
      stats: [
        { label: 'Cero', value: 0 },
        { label: 'Carga', value: null, loading: true },
        { label: 'Ausente', value: null },
      ],
    })
    const [zero, loading, missing] = screen.getAllByRole('listitem')
    expect(zero).toHaveTextContent('Cero0')
    expect(loading).toHaveTextContent('Cargando')
    expect(loading).not.toHaveTextContent('0')
    expect(missing).toHaveTextContent('No disponible')
    expect(missing).toHaveClass('heading-stat--unknown')
  })

  it.each([
    ['/my-tickets', 'blue'],
    ['/internal-tickets', 'purple'],
    ['/changes', 'cyan'],
    ['/activations', 'emerald'],
    ['/responsibles', 'slate'],
  ])('toma la identidad del módulo en %s (%s)', (route, theme) => {
    renderHeading({}, route)
    expect(document.querySelector('.page-heading')).toHaveClass(`page-heading--${theme}`)
  })

  it('mantiene el contador (telemetría) y el emblema fuera del árbol accesible', () => {
    renderHeading({ telemetry: <span>Registros: 5</span> })
    expect(screen.getByText('Registros: 5')).toBeInTheDocument()
    expect(document.querySelector('.heading-emblem')).toHaveAttribute('aria-hidden', 'true')
  })
})
