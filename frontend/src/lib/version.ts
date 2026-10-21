/** Accept release identifiers, including Python/semver prereleases, as plain text. */
export function parseVersion(value: unknown): string | null {
  return typeof value === 'string' && value === value.trim() && value.length <= 64 && /^\d+\.\d+\.\d+[a-zA-Z0-9.+-]*$/.test(value)
    ? value : null
}

/** A backend response must never relabel the JavaScript bundle being executed. */
export function describeVersion(bundleValue: unknown, apiValue: unknown) {
  const bundle = parseVersion(bundleValue)
  const api = parseVersion(apiValue)
  if (!bundle) return { label: 'versión no disponible', title: 'No se pudo identificar la versión de este frontend.' }
  const source = `Versión de este frontend: ${bundle}.`
  const status = !api ? 'La versión de la API no está disponible.'
    : api === bundle ? 'Coincide con la versión informada por la API.'
    : `La API informa ${api}; no coincide con este frontend.`
  return { label: `Ticketyn v${bundle}`, title: `${source} ${status}` }
}
