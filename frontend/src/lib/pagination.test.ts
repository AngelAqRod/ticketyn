import { describe, expect, it } from 'vitest'
import { pageInfo, pageText, rangeText } from './pagination'

describe('pageInfo', () => {
  it('primera página', () => expect(pageText(pageInfo(0, 50, 183))).toBe('Página 1 de 4 · Registros 1–50 de 183'))
  it('última página parcial', () => {
    const info = pageInfo(150, 33, 183)
    expect(rangeText(info)).toBe('Mostrando 151–183 de 183')
    expect(info.lastOffset).toBe(150)
  })
  it('sin resultados', () => { expect(rangeText(pageInfo(0, 0, 0))).toBe('Mostrando 0 de 0'); expect(pageText(pageInfo(0, 0, 0))).toBe('Mostrando 0 de 0') })
  it('página exacta y fuera de rango', () => {
    expect(pageInfo(100, 50, 150).pages).toBe(3)
    expect(pageInfo(300, 0, 150).lastOffset).toBe(100)
  })
})
