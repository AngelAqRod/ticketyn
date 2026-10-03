import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FilterChips } from './FilterChips'

describe('resumen visual de filtros', () => {
  it('no añade un resumen cuando no hay filtros', () => {
    render(<FilterChips items={[]} />)
    expect(screen.queryByLabelText('Filtros activos')).not.toBeInTheDocument()
  })
  it('muestra valores descriptivos conservando el texto completo en title', () => {
    render(<FilterChips items={[{ label: 'Cliente', value: 'C-001 — Cliente histórico' }, { label: 'Estado', value: 'Abierto' }]} />)
    expect(screen.getByLabelText('Filtros activos')).toBeInTheDocument()
    expect(screen.getByText('Cliente: C-001 — Cliente histórico').parentElement).toHaveAttribute('title', 'Cliente: C-001 — Cliente histórico')
    expect(screen.getByText('Estado: Abierto')).toBeInTheDocument()
  })
  it('es informativo y no introduce acciones que modifiquen filtros', () => {
    render(<FilterChips items={[{ label: 'Desde', value: '2026-10-01' }]} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByText('Desde: 2026-10-01')).toBeInTheDocument()
  })
})
