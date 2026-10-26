import '../styles/operatorProfile.css'

// Fourteen independent bars: six outer, split centre, four diagonals, two centre verticals.
export const lcdSegments = {
  a: '5,2 25,2 28,5 25,8 5,8 2,5',
  b: '26,9 29,6 29,24 26,27 23,24 23,12',
  c: '26,31 29,34 29,52 26,55 23,52 23,34',
  d: '5,54 25,54 28,57 25,60 5,60 2,57',
  e: '4,31 7,34 7,52 4,55 1,52 1,34',
  f: '4,9 7,12 7,24 4,27 1,24 1,12',
  g1: '6,27 12,27 15,30 12,33 6,33 3,30',
  g2: '18,27 24,27 27,30 24,33 18,33 15,30',
  h: '8,10 11,11 14,23 12,26 9,22',
  i: '13,10 16,7 19,10 19,23 16,26 13,23',
  j: '21,10 23,12 20,23 18,26 16,23',
  k: '16,37 18,34 21,38 24,49 21,51',
  l: '13,37 16,34 19,37 19,50 16,53 13,50',
  m: '12,34 15,37 11,49 8,51 7,48',
} as const

type Segment = keyof typeof lcdSegments
export const lcdCharacters: Record<string, readonly Segment[]> = {
  A: ['a','b','c','e','f','g1','g2'], B: ['a','b','c','d','g2','i','l'],
  C: ['a','d','e','f'], D: ['a','b','c','d','i','l'], E: ['a','d','e','f','g1','g2'], F: ['a','e','f','g1','g2'],
  G: ['a','c','d','e','f','g2'], H: ['b','c','e','f','g1','g2'], I: ['a','d','i','l'],
  J: ['b','c','d','e'], K: ['e','f','g1','j','k'], L: ['d','e','f'],
  M: ['b','c','e','f','h','j'], N: ['b','c','e','f','h','k'], O: ['a','b','c','d','e','f'],
  P: ['a','b','e','f','g1','g2'], Q: ['a','b','c','d','e','f','k'], R: ['a','b','e','f','g1','g2','k'],
  S: ['a','c','d','f','g1','g2'], T: ['a','i','l'], U: ['b','c','d','e','f'],
  V: ['e','f','j','m'], W: ['b','c','e','f','k','m'], X: ['h','j','k','m'], Y: ['h','j','l'], Z: ['a','d','j','m'],
  '0': ['a','b','c','d','e','f','j','m'], '1': ['b','c'], '2': ['a','b','d','e','g1','g2'],
  '3': ['a','b','c','d','g1','g2'], '4': ['b','c','f','g1','g2'], '5': ['a','c','d','f','g1','g2'],
  '6': ['a','c','d','e','f','g1','g2'], '7': ['a','b','c'], '8': ['a','b','c','d','e','f','g1','g2'],
  '9': ['a','b','c','d','f','g1','g2'], '?': ['a','b','g2','l'],
}

const normalize = (value: string) => value.normalize('NFKD').replace(/\p{M}/gu, '').toUpperCase().replace(/[^A-Z0-9 ]/g, ' ').trim()
export function operatorInitials(name = '', username = ''): string {
  const parts = normalize(name).split(/\s+/).filter(Boolean)
  if (parts.length > 1) return parts[0][0] + parts.at(-1)![0]
  const fallback = normalize(username).replaceAll(' ', '')
  if (fallback.length >= 2) return fallback.slice(0, 2)
  const single = parts[0] ?? fallback
  return (single || '??').padEnd(2, '?').slice(0, 2)
}

export function LcdOperatorAvatar({ name = '', username = '', size = 'large' }: {
  name?: string; username?: string; size?: 'large' | 'compact'
}) {
  const initials = operatorInitials(name, username)
  return <span className={`lcd-operator-avatar lcd-operator-avatar--${size}`} role="img" aria-label={`Identidad de ${name || username || 'usuario'}: ${initials}`}>
    <svg aria-hidden="true" focusable="false" viewBox="0 0 80 72">
      {[...initials].map((character, index) => <g key={index} transform={`translate(${index * 36 + 7} 5)`} data-character={character}>
        {Object.entries(lcdSegments).map(([segment, points]) => <polygon key={segment} points={points} data-segment={segment}
          className={lcdCharacters[character].includes(segment as Segment) ? 'lcd-segment-on' : 'lcd-segment-off'} />)}
      </g>)}
    </svg>
  </span>
}
