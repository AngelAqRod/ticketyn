import { afterEach, describe, expect, it, vi } from 'vitest'
import { defaultHiddenColumns, loadHiddenColumns, parseHiddenColumns, saveHiddenColumns } from './ticketColumns'

describe('preferencia de columnas', () => {
  afterEach(() => vi.unstubAllGlobals())
  it.each([[null], ['no-json'], ['{"a":1}'], ['["desconocida"]'], ['["node",3]']])('valor inválido %s → predeterminado', (raw) => expect(parseHiddenColumns(raw)).toEqual(defaultHiddenColumns))
  it('acepta columnas conocidas y elimina duplicados', () => expect(parseHiddenColumns('["end","end","type"]')).toEqual(['end', 'type']))
  it('acepta lista vacía (mostrar todo)', () => expect(parseHiddenColumns('[]')).toEqual([]))
  it('funciona con el almacenamiento deshabilitado', () => {
    vi.stubGlobal('localStorage', { getItem: () => { throw new Error('bloqueado') }, setItem: () => { throw new Error('bloqueado') } })
    expect(loadHiddenColumns()).toEqual(defaultHiddenColumns)
    expect(() => saveHiddenColumns(['node'])).not.toThrow()
  })
})
