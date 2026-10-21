import { readFileSync } from 'node:fs'
import { parseVersion } from '../src/lib/version.ts'

/** Read only the literal [project].version used by Ticketyn's release metadata. */
export function projectVersionFromToml(source: string): string {
  let project = false
  const values: string[] = []
  for (const line of source.split(/\r?\n/)) {
    const section = /^\s*\[([^\]]+)\]\s*(?:#.*)?$/.exec(line)
    if (section) { project = section[1] === 'project'; continue }
    if (!project || !/^\s*version\s*=/.test(line)) continue
    const match = /^\s*version\s*=\s*(?:"([^"\r\n]+)"|'([^'\r\n]+)')\s*(?:#.*)?$/.exec(line)
    const version = parseVersion(match?.[1] ?? match?.[2])
    if (!version) throw new Error('La versión [project].version de pyproject.toml no es válida.')
    values.push(version)
  }
  if (values.length !== 1) throw new Error('pyproject.toml debe declarar una única versión literal en [project].version.')
  return values[0]
}

export function readProjectVersion(file: URL): string {
  return projectVersionFromToml(readFileSync(file, 'utf8'))
}
