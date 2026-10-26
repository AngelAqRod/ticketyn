import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { LcdOperatorAvatar, lcdCharacters, lcdSegments, operatorInitials } from './LcdOperatorAvatar'
import { UserControls } from './UserControls'
import { AuthContext, type Identity } from '../auth/context'

it.each([
  ['Ana López', 'ana', 'AL'], ['María José Núñez', 'maria', 'MN'], ['Ángel Écija', 'angel', 'AE'],
  ['Operador', 'noc-2', 'NO'], ['', 'n1', 'N1'], ['', '', '??'], ['Ñora Úbeda', '', 'NU'], ['José', '', 'JO'],
])('normaliza iniciales: %s / %s', (name, username, expected) => {
  expect(operatorInitials(name, username)).toBe(expected)
})

describe('display auténtico de 14 segmentos', () => {
  it('dibuja exactamente 14 polígonos independientes por carácter, sin fuentes ni texto SVG', () => {
    const { container } = render(<LcdOperatorAvatar name="Ana López" />)
    expect(Object.keys(lcdSegments)).toHaveLength(14)
    expect(container.querySelectorAll('g')).toHaveLength(2)
    expect(container.querySelectorAll('polygon')).toHaveLength(28)
    expect(container.querySelector('text')).toBeNull()
    expect(screen.getByRole('img', { name: 'Identidad de Ana López: AL' })).toBeInTheDocument()
    const a = container.querySelector('[data-character="A"]')!
    expect(Array.from(a.querySelectorAll('.lcd-segment-on')).map(segment => segment.getAttribute('data-segment'))).toEqual(lcdCharacters.A)
    expect(a.querySelectorAll('.lcd-segment-off')).toHaveLength(14 - lcdCharacters.A.length)
  })
  it('tiene mapas válidos para todo el alfabeto y distingue letras que siete segmentos no representan', () => {
    for (const character of 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789?') {
      expect(lcdCharacters[character].length).toBeGreaterThan(0)
      expect(new Set(lcdCharacters[character]).size).toBe(lcdCharacters[character].length)
      expect(lcdCharacters[character].every(segment => segment in lcdSegments)).toBe(true)
    }
    expect(lcdCharacters.I).not.toEqual(lcdCharacters['1'])
    expect(lcdCharacters.M).toContain('h')
    expect(lcdCharacters.X).toEqual(['h', 'j', 'k', 'm'])
  })
  it('soporta tamaños compactos y actualiza las iniciales sin solicitudes', () => {
    const { rerender } = render(<LcdOperatorAvatar name="Ana López" size="compact" />)
    expect(screen.getByRole('img')).toHaveClass('lcd-operator-avatar--compact')
    rerender(<LcdOperatorAvatar name="Mario Núñez" size="large" />)
    expect(screen.getByRole('img', { name: 'Identidad de Mario Núñez: MN' })).toHaveClass('lcd-operator-avatar--large')
  })
})

it('integra el LCD compacto con el usuario autenticado y conserva los controles', () => {
  const identity: Identity = { responsible_id: 1, name: 'Ana López', username: 'ana', role: 'OPERATOR', password_change_required: false,
    operational_access: true, permissions: [], expires_in: 1800, warning_seconds: 120, role_revision: 1 }
  const value = { identity, busy: false, logout: vi.fn(async () => {}), accept: vi.fn(), refresh: vi.fn(async () => {}) }
  const { rerender } = render(<MemoryRouter><AuthContext.Provider value={value}><UserControls /></AuthContext.Provider></MemoryRouter>)
  expect(screen.getByRole('img', { name: 'Identidad de Ana López: AL' })).toHaveClass('lcd-operator-avatar--compact')
  expect(screen.getByRole('link', { name: 'Mi perfil' })).toHaveAttribute('href', '/profile')
  expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeEnabled()
  rerender(<MemoryRouter><AuthContext.Provider value={{ ...value, identity: { ...identity, name: 'Carlos Díaz' } }}><UserControls /></AuthContext.Provider></MemoryRouter>)
  expect(screen.getByRole('img', { name: 'Identidad de Carlos Díaz: CD' })).toBeInTheDocument()
})

it('mantiene accesibles los controles de usuario en móvil y cierra con Escape', async () => {
  const { fireEvent } = await import('@testing-library/react')
  const original = window.matchMedia
  window.matchMedia = vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })
  const identity: Identity = { responsible_id: 1, name: 'Ana López', username: 'ana', role: 'OPERATOR', password_change_required: false,
    operational_access: true, permissions: [], expires_in: 1800, warning_seconds: 120, role_revision: 1 }
  try {
    render(<MemoryRouter><AuthContext.Provider value={{ identity, busy: false, logout: vi.fn(async () => {}), accept: vi.fn(), refresh: vi.fn(async () => {}) }}><UserControls /></AuthContext.Provider></MemoryRouter>)
    expect(window.matchMedia).toHaveBeenCalledWith('(max-width: 1023px)')
    const trigger = screen.getByRole('button', { name: 'Menú de Ana López' })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    fireEvent.click(trigger)
    expect(screen.getByRole('link', { name: 'Mi perfil' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Cerrar sesión' })).toBeVisible()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(trigger).toHaveFocus()
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('link', { name: 'Mi perfil' })).not.toBeInTheDocument()
  } finally { window.matchMedia = original }
})
