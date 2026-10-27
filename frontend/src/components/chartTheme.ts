/** Shared Capsule NOC presentation tokens; never used for report calculations. */
export const chartPalette = ['#176BDF', '#9673D6', '#319C81', '#D69A46', '#568DB5', '#218FAD'] as const
export const chartTheme = {
  grid: '#1e293b', label: '#94a3b8', closed: '#34d399',
  changeStatuses: { scheduled: chartPalette[3], finished: '#91C9B5', executing: chartPalette[0] },
  horizontalRadius: [0, 4, 4, 0] as [number, number, number, number],
  verticalRadius: [4, 4, 0, 0] as [number, number, number, number],
}

/** Decorative categories follow their displayed order, independently of IDs or names.
 * Re-rendering the same order always produces the same sequence.
 * Semantic series colors are supplied separately by the chart.
 */
export function categoryColor(displayIndex: number) {
  return chartPalette[displayIndex % chartPalette.length]
}
