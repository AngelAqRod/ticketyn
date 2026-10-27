import { act, render, screen } from '../test/render'
import { renderToString } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { OperationalClock } from './OperationalClock'

const original = process.env.TZ
afterEach(() => { vi.useRealTimers(); if (original === undefined) delete process.env.TZ; else process.env.TZ = original })

describe('reloj operativo', () => {
  it('antes de la primera actualización muestra --:--:--', () => {
    expect(renderToString(<OperationalClock />)).toContain('--:--:--')
  })
  it('se actualiza cada segundo y limpia el temporizador al desmontar', async () => {
    vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-27T02:39:01Z'))
    const { unmount } = render(<OperationalClock />)
    expect(screen.getByRole('timer', { name: 'Hora operativa, America/Guatemala' })).toHaveTextContent(/lun, 26 oct\s*20:39:01\s*· America\/Guatemala/)
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(screen.getByRole('timer')).toHaveTextContent('20:39:02')
    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
  it('no anuncia la hora: sin aria-live y con el texto oculto a lectores de pantalla', () => {
    const { container } = render(<OperationalClock />)
    expect(container.querySelector('[aria-live]')).toBeNull()
    expect(container.querySelector('[role="timer"] > [aria-hidden="true"]')).toBeInTheDocument()
  })
  it.each(['UTC', 'Etc/GMT+6', 'Asia/Tokyo'])('muestra la misma hora de Guatemala con TZ=%s', (zone) => {
    process.env.TZ = zone
    vi.useFakeTimers(); vi.setSystemTime(new Date('2026-03-01T05:59:59Z'))   // cerca del cambio de día en Guatemala
    render(<OperationalClock />)
    expect(screen.getByRole('timer')).toHaveTextContent(/28 feb\s*23:59:59/)
  })
})
