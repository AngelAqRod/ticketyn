/** Compare fixed precision capacities without IEEE-754 rounding. */
export function capacityInMicroMbps(value: string, unit: string): bigint {
  if (!/^(?:0|[1-9]\d{0,11})(?:\.\d{1,6})?$/.test(value)) throw new Error('Introduce una capacidad positiva con hasta seis decimales.')
  const [whole, fraction = ''] = value.split('.')
  const scaled = BigInt(whole) * 1000000n + BigInt(fraction.padEnd(6, '0'))
  if (scaled <= 0n || !['Mbps', 'Gbps'].includes(unit)) throw new Error('Las capacidades deben ser positivas y usar Mbps o Gbps.')
  return scaled * (unit === 'Gbps' ? 1000n : 1n)
}

/** Presentation only: choose the unit before rounding, then round decimal half up. */
export function formatCapacity(value?: string | null, unit?: string | null): string {
  if (value == null || !/^[0-9]+(?:\.[0-9]+)?$/.test(value) || (unit !== 'Mbps' && unit !== 'Gbps')) return 'Sin registrar'
  const [whole, fraction = ''] = value.split('.')
  const scale = 10n ** BigInt(fraction.length)
  const mbps = BigInt(whole + fraction) * (unit === 'Gbps' ? 1000n : 1n)
  const displayUnit = mbps >= 1000n * scale ? 'Gbps' : 'Mbps'
  const divisor = scale * (displayUnit === 'Gbps' ? 1000n : 1n)
  const thousandths = (mbps * 1000n * 2n + divisor) / (divisor * 2n)
  const decimals = (thousandths % 1000n).toString().padStart(3, '0').replace(/0+$/, '')
  return `${thousandths / 1000n}${decimals ? `.${decimals}` : ''} ${displayUnit}`
}
