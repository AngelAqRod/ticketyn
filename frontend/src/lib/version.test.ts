import { describe, expect, it } from 'vitest'
import { describeVersion, parseVersion } from './version'

describe('identificación de la versión del frontend', () => {
  it.each(['1.2.3', '1.2.3-rc.1', '1.2.3.dev1', '1.2.3rc1', '1.2.3+build.2'])('admite %s sin transformar el valor', (value) => {
    expect(parseVersion(value)).toBe(value)
  })
  it.each([undefined, null, {}, [], 123, '', 'invalid', '<script>1.2.3</script>', '1.2.3\n', ' 1.2.3', '1.2.3 extra', `1.2.3+${'a'.repeat(64)}`])('rechaza datos no utilizables (%j)', (value) => {
    expect(parseVersion(value)).toBe(null)
  })
  it('muestra un único número cuando coincide con la API', () => {
    expect(describeVersion('1.2.3', '1.2.3')).toEqual({
      label: 'Ticketyn v1.2.3',
      title: 'Versión de este frontend: 1.2.3. Coincide con la versión informada por la API.',
    })
  })
  it('no sustituye la versión del bundle por una API desactualizada o de otra release', () => {
    expect(describeVersion('1.2.3', '9.8.7')).toEqual({
      label: 'Ticketyn v1.2.3',
      title: 'Versión de este frontend: 1.2.3. La API informa 9.8.7; no coincide con este frontend.',
    })
  })
  it('conserva la identificación del bundle sin inventar una versión de la API', () => {
    expect(describeVersion('1.2.3', null)).toEqual({
      label: 'Ticketyn v1.2.3',
      title: 'Versión de este frontend: 1.2.3. La versión de la API no está disponible.',
    })
  })
  it('no utiliza el backend como fallback para un bundle sin identificar', () => {
    expect(describeVersion(null, '9.8.7')).toEqual({
      label: 'versión no disponible', title: 'No se pudo identificar la versión de este frontend.',
    })
  })
})
