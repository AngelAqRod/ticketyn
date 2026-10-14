import { describe, expect, it } from 'vitest'
import { circuitLabel } from './circuitLabel'

describe('Etiquetas compartidas del selector Circuito', () => {
  it('muestra código y descripción', () => {
    expect(circuitLabel({ circuit_code: '200.01', description: 'CIRCUITO CLIENTE 200' })).toBe('200.01 — CIRCUITO CLIENTE 200')
  })
  it.each([null, undefined, '', '   '])('omite el separador si falta la descripción: %s', description => {
    expect(circuitLabel({ circuit_code: '200.01', description })).toBe('200.01')
  })
  it('quita únicamente espacios externos para la presentación', () => {
    const circuit = { circuit_code: '200.01', description: '  Enlace principal  ' }
    expect(circuitLabel(circuit)).toBe('200.01 — Enlace principal')
    expect(circuit.description).toBe('  Enlace principal  ')
  })
})
