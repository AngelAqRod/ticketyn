import { render, screen } from '@testing-library/react'
import { Clock3, CircleCheck, Tickets } from 'lucide-react'
import { describe, expect, it } from 'vitest'
import { MetricStrip } from './MetricStrip'

describe('Indicadores compartidos', () => {
  it('conserva etiquetas, valores, orden e iconos originales con sus tonos', () => {
    const { container } = render(<MetricStrip variant="light" items={[
      { label: 'Tickets totales', value: 42, icon: <Tickets size={16} data-testid="total-icon" /> },
      { label: 'Tickets abiertos', value: 3, icon: <Clock3 size={16} data-testid="open-icon" />, iconTone: 'warning' },
      { label: 'Tickets cerrados', value: 39, icon: <CircleCheck size={16} data-testid="closed-icon" />, iconTone: 'success' },
    ]} />)
    expect([...container.querySelectorAll('dt')].map(el => el.textContent)).toEqual(['Tickets totales', 'Tickets abiertos', 'Tickets cerrados'])
    expect([...container.querySelectorAll('dd')].map(el => el.textContent)).toEqual(['42', '3', '39'])
    for (const name of ['total-icon', 'open-icon', 'closed-icon']) {
      expect(screen.getByTestId(name)).toHaveAttribute('width', '16')
      expect(screen.getByTestId(name)).toHaveAttribute('height', '16')
      expect(screen.getByTestId(name).parentElement).toHaveAttribute('aria-hidden', 'true')
    }
    expect(screen.getByTestId('open-icon').parentElement).toHaveAttribute('data-tone', 'warning')
    expect(screen.getByTestId('closed-icon').parentElement).toHaveAttribute('data-tone', 'success')
  })
  it('admite más de tres indicadores y formatos React sin reinterpretar datos', () => {
    const values = [0, '—', <span key="capacity">1.759 Gbps</span>, '46.15 %', '1 h 30 min', '12345678901234567890']
    const { container } = render(<MetricStrip items={values.map((value, index) => ({ label: `Indicador ${index}`, value }))} />)
    expect(container.querySelectorAll('dt')).toHaveLength(6)
    expect([...container.querySelectorAll('dd')].map(el => el.textContent)).toEqual(['0', '—', '1.759 Gbps', '46.15 %', '1 h 30 min', '12345678901234567890'])
  })
  it('mantiene independiente la variante pastel del color semántico original del icono', () => {
    render(<MetricStrip items={[{ label: 'Escalamientos activos', value: 2, color: 'amber', icon: <Clock3 size={20} data-testid="escalation-icon" /> }]} />)
    const icon = screen.getByTestId('escalation-icon')
    expect(icon.parentElement).not.toHaveAttribute('data-tone')
    expect(icon.closest('.metric-item')).toHaveAttribute('data-color', 'amber')
  })
})
