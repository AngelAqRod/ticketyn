/** Module identity only: SVG segments, with equivalent text for assistive technology. */
const digits: Record<string, string> = {
  '0': 'abcdef', '1': 'bc', '2': 'abdeg', '3': 'abcdg', '4': 'bcfg',
  '5': 'acdfg', '6': 'acdefg', '7': 'abc', '8': 'abcdefg', '9': 'abcdfg',
}
const segments: Record<string, string> = {
  a: '3,1 11,1 13,3 11,5 3,5 1,3',
  b: '11,5 13,3 13,11 11,13 9,11 9,7',
  c: '11,13 13,15 13,23 11,21 9,19 9,15',
  d: '3,21 11,21 13,23 11,25 3,25 1,23',
  e: '1,15 3,13 5,15 5,19 3,21 1,23',
  f: '1,3 3,5 5,7 5,11 3,13 1,11',
  g: '3,11 11,11 13,13 11,15 3,15 1,13',
}

export function SevenSegmentNumber({ value, className = '' }: { value: string | number; className?: string }) {
  const text = String(value)
  if (!/^\d+$/.test(text)) return <span className={className}>{text}</span>
  return <span className={`seven-segment-number ${className}`}>
    <span className="sr-only">{text}</span>
    <svg aria-hidden="true" focusable="false" viewBox={`0 0 ${text.length * 16} 26`} style={{ width: `${text.length * 16 / 26}em` }}>
      {[...text].map((digit, index) => <g key={index} transform={`translate(${index * 16} 0)`} data-digit={digit}>
        {[...digits[digit]].map(segment => <polygon key={segment} points={segments[segment]} />)}
      </g>)}
    </svg>
  </span>
}
