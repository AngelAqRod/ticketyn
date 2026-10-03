import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { RankingSection } from './RankingSection'
import type { ReportRanking } from '../types/report'

vi.mock('./ReportCharts', () => ({ RankingChart: ({ rows }: { rows: ReportRanking[] }) => <div role="img" aria-label="Top 10">{rows.slice(0, 10).map((row) => <span key={row.id}>{row.label}</span>)}</div> }))
const rows: ReportRanking[] = Array.from({ length: 12 }, (_, index) => ({ id: index + 1, label: `Sector ${index + 1}`, count: 12 - index, customer_id: null, customer_code: null, customer_name: null }))
function setup(items = rows) {
  render(<MemoryRouter><RankingSection title="Sectores con más incidencias" rows={items} destination={(row) => `/reports?sector_id=${row.id}`} /></MemoryRouter>)
}
describe('ranking expandible', () => {
  it('muestra Top 10 sin renderizar la tabla completa inicialmente', () => {
    setup()
    expect(screen.getByRole('img', { name: 'Top 10' })).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByText('Sector 11')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ver ranking completo (12)' })).toHaveAttribute('aria-expanded', 'false')
  })
  it('expande todos los registros, conserva drill-down y permite colapsar', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: 'Ver ranking completo (12)' }))
    expect(screen.getByRole('table', { name: 'Sectores con más incidencias' })).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(13)
    expect(screen.getByRole('link', { name: 'Sector 12' })).toHaveAttribute('href', '/reports?sector_id=12')
    const toggle = screen.getByRole('button', { name: 'Ocultar ranking completo (12)' })
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(document.getElementById(toggle.getAttribute('aria-controls')!)).toBeVisible()
    fireEvent.click(toggle)
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
  it('muestra vacío sin controles de expansión innecesarios', () => {
    setup([])
    expect(screen.getByText('Sin incidencias.')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
  it('conserva el ranking completo también con un solo registro', () => {
    setup(rows.slice(0, 1))
    fireEvent.click(screen.getByRole('button', { name: 'Ver ranking completo (1)' }))
    expect(screen.getByRole('link', { name: 'Sector 1' })).toBeInTheDocument()
  })
})
