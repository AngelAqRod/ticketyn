/** Presentation only: the selector value remains the circuit ID. */
export function circuitLabel(circuit: { circuit_code: string; description?: string | null }): string {
  const description = circuit.description?.trim()
  return description ? `${circuit.circuit_code} — ${description}` : circuit.circuit_code
}
