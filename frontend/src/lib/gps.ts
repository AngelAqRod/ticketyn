/** Punto GPS: one visible field ("14.634915, -90.506882"), two numeric columns in the database. */
export const GPS_EXAMPLE = '14.634915, -90.506882'
const NUMBER = String.raw`[+-]?\d+(?:\.\d+)?`
const PAIR = new RegExp(String.raw`^\(?\s*(${NUMBER})\s*(?:,|;|\s)\s*(${NUMBER})\s*\)?$`)
export type GpsPoint = { latitude: string; longitude: string }

/** Returns null for an empty field and throws a user-facing message for anything incomplete or out of range. */
export function parseGps(text: string): GpsPoint | null {
  const value = text.trim()
  if (!value) return null
  const match = PAIR.exec(value)
  if (!match) {
    throw new Error(new RegExp(`^\\(?\\s*${NUMBER}\\s*[,;]?\\s*\\)?$`).test(value)
      ? `El Punto GPS debe incluir latitud y longitud, por ejemplo ${GPS_EXAMPLE}.`
      : `Formato de Punto GPS no válido. Usa «latitud, longitud», por ejemplo ${GPS_EXAMPLE}.`)
  }
  const [latitude, longitude] = [match[1].replace(/^\+/, ''), match[2].replace(/^\+/, '')]
  if (Math.abs(Number(latitude)) > 90) throw new Error('La latitud debe estar entre -90 y 90.')
  if (Math.abs(Number(longitude)) > 180) throw new Error('La longitud debe estar entre -180 y 180.')
  return { latitude, longitude }
}

const clean = (value: string | number) => String(Number(value))

/** Visual value rebuilt from the stored pair; empty unless both coordinates exist. */
export function formatGps(latitude?: string | number | null, longitude?: string | number | null): string {
  return latitude == null || longitude == null ? '' : `${clean(latitude)}, ${clean(longitude)}`
}

/** Single source of the Google Maps link (circuit detail and installation orders). Null unless both coordinates are valid. */
export function mapsUrl(latitude?: string | number | null, longitude?: string | number | null): string | null {
  if (latitude == null || longitude == null || latitude === '' || longitude === '') return null
  const [lat, lng] = [Number(latitude), Number(longitude)]
  if (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) return null
  // Documented URL scheme: no API key, no JavaScript API. URLSearchParams encodes the comma as %2C.
  return `https://www.google.com/maps/search/?${new URLSearchParams({ api: '1', query: `${lat},${lng}` })}`
}
