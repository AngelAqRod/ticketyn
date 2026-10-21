// @vitest-environment node
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { describe, expect, it } from 'vitest'
import { projectVersionFromToml, readProjectVersion } from './projectVersion'

describe('versión del proyecto para Vite', () => {
  it('utiliza únicamente [project].version, no otras versiones del TOML', () => {
    expect(projectVersionFromToml('[build-system]\nversion = "8.0.0"\n[project]\nversion = "1.2.3" # release\n[tool.example]\nversion = "9.0.0"\n')).toBe('1.2.3')
  })

  it('admite comillas simples, CRLF y versiones de desarrollo declaradas', () => {
    expect(projectVersionFromToml("[project]\r\nversion = '1.2.3.dev1'\r\n")).toBe('1.2.3.dev1')
  })

  it.each([
    '[tool.example]\nversion = "1.2.3"',
    '[project]\nname = "ticketyn"',
    '[project]\nversion = "invalid"',
    '[project]\nversion = ""',
    '[project]\nversion = 123',
    '[project]\nversion = "1.2.3"\nversion = "4.5.6"',
  ])('detiene la compilación sin una versión literal válida y única (%s)', (source) => {
    expect(() => projectVersionFromToml(source)).toThrow(/versión/)
  })

  it('lee el archivo explícito sin depender del directorio de trabajo', () => {
    const folder = mkdtempSync(join(tmpdir(), 'ticketyn-version-'))
    try {
      const file = join(folder, 'pyproject.toml')
      writeFileSync(file, '[project]\nversion = "9.8.7"\n')
      expect(readProjectVersion(pathToFileURL(file))).toBe('9.8.7')
      expect(() => readProjectVersion(pathToFileURL(join(folder, 'missing.toml')))).toThrow()
    } finally {
      rmSync(folder, { recursive: true, force: true })
    }
  })
})
