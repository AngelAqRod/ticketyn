import { describe, expect, it } from 'vitest'
import { formatGps, mapsUrl, parseGps } from './gps'

describe('Punto GPS', () => {
  it('parses a Google Maps paste, tolerating spaces around and between the values', () => {
    expect(parseGps('14.634915, -90.506882')).toEqual({ latitude: '14.634915', longitude: '-90.506882' })
    expect(parseGps('   14.634915,-90.506882  ')).toEqual({ latitude: '14.634915', longitude: '-90.506882' })
    expect(parseGps('14.634915 -90.506882')).toEqual({ latitude: '14.634915', longitude: '-90.506882' })
    expect(parseGps('(14.634915, -90.506882)')).toEqual({ latitude: '14.634915', longitude: '-90.506882' })
    expect(parseGps('+14, -90')).toEqual({ latitude: '14', longitude: '-90' })
  })
  it('treats an empty field as no point so it can be cleared', () => {
    expect(parseGps('')).toBeNull(); expect(parseGps('   ')).toBeNull()
  })
  it('rejects incomplete values and invalid formats with clear messages', () => {
    expect(() => parseGps('14.634915')).toThrow('latitud y longitud')
    expect(() => parseGps('14.634915,')).toThrow('latitud y longitud')
    expect(() => parseGps('norte, sur')).toThrow('Formato de Punto GPS no válido')
    expect(() => parseGps('14.6, -90.5, 10')).toThrow('Formato de Punto GPS no válido')
    expect(() => parseGps('14,634915, -90,506882')).toThrow('Formato de Punto GPS no válido')
  })
  it('validates both ranges including the limits', () => {
    expect(parseGps('90, 180')).toEqual({ latitude: '90', longitude: '180' }); expect(parseGps('-90, -180')).toEqual({ latitude: '-90', longitude: '-180' })
    expect(() => parseGps('90.1, 0')).toThrow('latitud debe estar entre -90 y 90')
    expect(() => parseGps('0, -180.1')).toThrow('longitud debe estar entre -180 y 180')
  })
  it('rebuilds the visual value and the map link only from a complete pair', () => {
    expect(formatGps('14.634915', '-90.506882')).toBe('14.634915, -90.506882')
    expect(formatGps('14.500000', '-90.000000')).toBe('14.5, -90')
    expect(formatGps(null, null)).toBe(''); expect(formatGps('14.5', null)).toBe('')
    expect(mapsUrl('14.634915', '-90.506882')).toBe('https://www.google.com/maps/search/?api=1&query=14.634915%2C-90.506882'); expect(mapsUrl(null, '1')).toBeNull()
  })
  it('never builds a link from empty, incomplete or invalid coordinates', () => {
    for (const [lat, lng] of [[null, null], ['14.5', null], [null, '-90.5'], ['', ''], ['abc', '1'], ['1', 'NaN'], ['91', '0'], ['0', '-181'], [undefined, undefined]] as const) expect(mapsUrl(lat, lng)).toBeNull()
    expect(mapsUrl('90', '180')).not.toBeNull(); expect(mapsUrl('-90.000000', '-180.000000')).toBe('https://www.google.com/maps/search/?api=1&query=-90%2C-180')
    expect(mapsUrl(14.5, -90.25)).toBe('https://www.google.com/maps/search/?api=1&query=14.5%2C-90.25')
  })
})
