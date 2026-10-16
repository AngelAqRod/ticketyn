import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SevenSegmentNumber } from './SevenSegmentNumber'
import { identityFor } from './moduleIdentity'

describe('Siete segmentos', () => {
  it.each([['0', 6], ['1', 2], ['2', 5], ['3', 5], ['4', 4], ['5', 5], ['6', 6], ['7', 3], ['8', 7], ['9', 6]])('representa %s con sus segmentos reales', (value, count) => {
    const { container } = render(<SevenSegmentNumber value={value} />)
    expect(screen.getByText(value)).toHaveClass('sr-only')
    expect(container.querySelectorAll('polygon')).toHaveLength(count as number)
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
  })
  it('conserva ceros iniciales y permite adaptar tamaño y color mediante CSS', () => {
    const { container } = render(<SevenSegmentNumber value="02" className="text-blue-200 text-xl" />)
    expect(screen.getByText('02')).toBeInTheDocument()
    expect([...container.querySelectorAll('g')].map(node => node.getAttribute('data-digit'))).toEqual(['0', '2'])
    expect(container.firstChild).toHaveClass('text-xl', 'text-blue-200')
  })
  it('mantiene la identidad del encabezado alineada con el orden de navegación', () => {
    expect(identityFor('/activations/1')?.number).toBe('07')
    expect(identityFor('/reports')?.number).toBe('10')
    expect(identityFor('/catalogs')?.number).toBe('14')
    expect(identityFor('/settings')?.number).toBe('15')
  })
})
