import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { TicketRecommendationNotice } from './TicketRecommendationNotice'
import * as api from '../api/recommendations'
import type { TicketRecommendationsResponse } from '../types/recommendation'

vi.mock('../api/recommendations', () => ({ getTicketRecommendations: vi.fn(), createTicketAck: vi.fn(), revokeTicketAck: vi.fn() }))
const opened: TicketRecommendationsResponse = {
  ticket_id: 1, ticket_status: 'OPEN', stage_name: 'Etapa inicial', reference_position_id: 1, reference_position_name: 'N1',
  stage_started_at: '2020-01-01T00:00:00Z', elapsed_minutes: 40, has_active_ack: false, can_acknowledge: true,
  recommendations: [{ target_position_id: 2, target_position_name: 'N2', target_department_name: 'NOC', threshold_minutes: 30, elapsed_minutes: 40, overdue_minutes: 10 }],
}
const ack = { id: 1, ticket_id: 1, active: true, duration_type: '1H' as const, reason: 'Diagnóstico', acknowledged_at: '2020-01-01T00:00:00Z', expires_at: '2020-01-01T01:00:00Z', acknowledged_by: { id: 1, name: 'Operador', active: true } }
const flush = async () => { await act(async () => { await Promise.resolve() }) }
const advance = async (ms: number) => { await act(async () => { await vi.advanceTimersByTimeAsync(ms) }) }
function visibility(state: 'visible' | 'hidden') {
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: state })
  fireEvent(document, new Event('visibilitychange'))
}
beforeEach(() => {
  vi.useFakeTimers(); vi.clearAllMocks()
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
  vi.mocked(api.getTicketRecommendations).mockResolvedValue(opened)
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks() })

describe.each([false, true])('actualización de recomendaciones (interno=%s)', internal => {
  it('consulta el ticket visible al inicio y cada 60 segundos', async () => {
    render(<TicketRecommendationNotice ticketId={1} internal={internal} ticketStatus="OPEN" />)
    await flush()
    expect(api.getTicketRecommendations).toHaveBeenCalledExactlyOnceWith(1, internal, expect.any(AbortSignal))
    await advance(59_999); expect(api.getTicketRecommendations).toHaveBeenCalledTimes(1)
    await advance(1); expect(api.getTicketRecommendations).toHaveBeenCalledTimes(2)
    await advance(60_000); expect(api.getTicketRecommendations).toHaveBeenCalledTimes(3)
    expect(screen.getByText('Escalamiento recomendado')).toBeInTheDocument()
  })
  it('no consulta tickets cerrados y reinicia al reabrir', async () => {
    const view = render(<TicketRecommendationNotice ticketId={1} internal={internal} ticketStatus="CLOSED" />)
    await advance(180_000)
    expect(api.getTicketRecommendations).not.toHaveBeenCalled()
    view.rerender(<TicketRecommendationNotice ticketId={1} internal={internal} ticketStatus="OPEN" />)
    await flush(); expect(api.getTicketRecommendations).toHaveBeenCalledTimes(1)
    view.rerender(<TicketRecommendationNotice ticketId={1} internal={internal} ticketStatus="CLOSED" />)
    await advance(180_000); expect(api.getTicketRecommendations).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('Escalamiento recomendado')).not.toBeInTheDocument()
    visibility('hidden'); visibility('visible'); await flush()
    expect(api.getTicketRecommendations).toHaveBeenCalledTimes(1)
  })
  it('limpia el temporizador anterior al cambiar de ticket o desmontar', async () => {
    const view = render(<TicketRecommendationNotice ticketId={1} internal={internal} />)
    await flush()
    vi.mocked(api.getTicketRecommendations).mockResolvedValue({ ...opened, ticket_id: 2 })
    view.rerender(<TicketRecommendationNotice ticketId={2} internal={internal} />)
    await flush(); await advance(60_000)
    expect(vi.mocked(api.getTicketRecommendations).mock.calls.map(call => call[0])).toEqual([1, 2, 2])
    view.unmount(); expect(vi.getTimerCount()).toBe(0)
    await advance(180_000); expect(api.getTicketRecommendations).toHaveBeenCalledTimes(3)
  })
  it('suspende en pestaña inactiva y actualiza al recuperar visibilidad', async () => {
    visibility('hidden')
    render(<TicketRecommendationNotice ticketId={1} internal={internal} />)
    await advance(180_000); expect(api.getTicketRecommendations).not.toHaveBeenCalled()
    visibility('visible'); await flush(); expect(api.getTicketRecommendations).toHaveBeenCalledTimes(1)
    visibility('hidden'); await advance(180_000); expect(api.getTicketRecommendations).toHaveBeenCalledTimes(1)
    visibility('visible'); await flush(); expect(api.getTicketRecommendations).toHaveBeenCalledTimes(2)
    await advance(60_000); expect(api.getTicketRecommendations).toHaveBeenCalledTimes(3)
  })
  it('detiene la vigilancia y sincroniza la pantalla tras un cierre remoto', async () => {
    const onTicketStatusChange = vi.fn()
    render(<TicketRecommendationNotice ticketId={1} internal={internal} onTicketStatusChange={onTicketStatusChange} />)
    await flush()
    vi.mocked(api.getTicketRecommendations).mockResolvedValue({ ...opened, ticket_status: 'CLOSED', recommendations: [] })
    await advance(60_000)
    expect(onTicketStatusChange).toHaveBeenCalledExactlyOnceWith('CLOSED')
    await advance(300_000); visibility('hidden'); visibility('visible'); await flush()
    expect(api.getTicketRecommendations).toHaveBeenCalledTimes(2)
    expect(screen.queryByText('Escalamiento recomendado')).not.toBeInTheDocument()
  })
  it('mantiene una única petición y agrupa invalidaciones mientras está pendiente', async () => {
    let resolve!: (value: TicketRecommendationsResponse) => void
    vi.mocked(api.getTicketRecommendations).mockReturnValueOnce(new Promise(done => { resolve = done }))
    const view = render(<TicketRecommendationNotice ticketId={1} internal={internal} refreshKey={0} />)
    await advance(180_000); expect(api.getTicketRecommendations).toHaveBeenCalledTimes(1)
    view.rerender(<TicketRecommendationNotice ticketId={1} internal={internal} refreshKey={1} />)
    view.rerender(<TicketRecommendationNotice ticketId={1} internal={internal} refreshKey={2} />)
    visibility('visible'); await flush()
    expect(api.getTicketRecommendations).toHaveBeenCalledTimes(1)
    await act(async () => resolve(opened))
    expect(api.getTicketRecommendations).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(1)
    await advance(60_000); expect(api.getTicketRecommendations).toHaveBeenCalledTimes(3)
  })
  it('no permite que una respuesta anterior reactive un ticket cerrado', async () => {
    let resolve!: (value: TicketRecommendationsResponse) => void
    vi.mocked(api.getTicketRecommendations).mockReturnValueOnce(new Promise(done => { resolve = done }))
    const view = render(<TicketRecommendationNotice ticketId={1} internal={internal} />)
    const signal = vi.mocked(api.getTicketRecommendations).mock.calls[0][2]!
    view.rerender(<TicketRecommendationNotice ticketId={1} internal={internal} ticketStatus="CLOSED" />)
    expect(signal.aborted).toBe(true)
    await act(async () => resolve(opened)); await advance(180_000)
    expect(api.getTicketRecommendations).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('Escalamiento recomendado')).not.toBeInTheDocument()
  })
  it('evalúa ACK al vencer sin añadir temporizadores por destino', async () => {
    vi.mocked(api.getTicketRecommendations).mockResolvedValueOnce({ ...opened, has_active_ack: true, active_ack: ack, recommendations: [] })
    render(<TicketRecommendationNotice ticketId={1} internal={internal} />)
    await flush(); expect(screen.getByText(/Recomendaciones de escalamiento reconocidas/)).toBeInTheDocument()
    expect(vi.getTimerCount()).toBe(1)
    await advance(60_000)
    expect(screen.getByText('Escalamiento recomendado')).toBeInTheDocument()
    expect(vi.getTimerCount()).toBe(1)
  })
  it('actualiza inmediatamente después de registrar y retirar ACK', async () => {
    vi.mocked(api.createTicketAck).mockResolvedValue(ack)
    vi.mocked(api.revokeTicketAck).mockResolvedValue({ ...ack, active: false })
    render(<TicketRecommendationNotice ticketId={1} internal={internal} />)
    await flush()
    fireEvent.click(screen.getByRole('button', { name: 'Reconocer (ACK)' }))
    fireEvent.change(screen.getByLabelText(/Motivo del reconocimiento/), { target: { value: 'Diagnóstico' } })
    vi.mocked(api.getTicketRecommendations).mockResolvedValueOnce({ ...opened, has_active_ack: true, active_ack: ack, recommendations: [] })
    fireEvent.submit(screen.getByRole('button', { name: 'Confirmar reconocimiento' }).closest('form')!)
    await flush()
    expect(api.getTicketRecommendations).toHaveBeenCalledTimes(2)
    fireEvent.click(screen.getByRole('button', { name: 'Retirar reconocimiento' })); await flush()
    expect(api.getTicketRecommendations).toHaveBeenCalledTimes(3)
    expect(vi.getTimerCount()).toBe(1)
  })
})
