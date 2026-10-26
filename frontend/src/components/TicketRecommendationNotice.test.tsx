import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { TicketRecommendationNotice } from './TicketRecommendationNotice'
import { PermissionProvider } from '../auth/permissions'
import * as recommendationsApi from '../api/recommendations'
import type { TicketRecommendationsResponse } from '../types/recommendation'

vi.mock('../api/recommendations', () => ({
  getTicketRecommendations: vi.fn(),
  createTicketAck: vi.fn(),
  revokeTicketAck: vi.fn(),
}))

describe('TicketRecommendationNotice', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('no muestra nada si no hay recomendaciones activas ni ACK', async () => {
    const emptyResponse: TicketRecommendationsResponse = {
      ticket_id: 1,
      ticket_status: 'OPEN',
      stage_name: 'Etapa inicial',
      reference_position_id: 1,
      reference_position_name: 'Soporte N1',
      stage_started_at: '2026-10-25T10:00:00Z',
      elapsed_minutes: 10,
      has_active_ack: false,
      active_ack: null,
      recommendations: [],
      can_acknowledge: true,
    }
    vi.mocked(recommendationsApi.getTicketRecommendations).mockResolvedValue(emptyResponse)

    const { container } = render(
      <PermissionProvider permissions={['tickets.view', 'tickets.escalate']}>
        <TicketRecommendationNotice ticketId={1} />
      </PermissionProvider>
    )

    await waitFor(() => {
      expect(recommendationsApi.getTicketRecommendations).toHaveBeenCalledWith(1, false, expect.any(AbortSignal))
    })

    expect(container.firstChild).toBeNull()
  })

  it('muestra aviso de escalamiento recomendado y permite invocar el escalamiento', async () => {
    const onEscalate = vi.fn()
    const recResponse: TicketRecommendationsResponse = {
      ticket_id: 1,
      ticket_status: 'OPEN',
      stage_name: 'Etapa inicial',
      reference_position_id: 1,
      reference_position_name: 'Soporte N1',
      stage_started_at: '2026-10-25T10:00:00Z',
      elapsed_minutes: 35,
      has_active_ack: false,
      active_ack: null,
      recommendations: [
        {
          target_position_id: 2,
          target_position_name: 'Supervisor NOC',
          target_department_name: 'Operaciones',
          threshold_minutes: 30,
          elapsed_minutes: 35,
          overdue_minutes: 5,
        },
      ],
      can_acknowledge: true,
    }
    vi.mocked(recommendationsApi.getTicketRecommendations).mockResolvedValue(recResponse)

    render(
      <PermissionProvider permissions={['tickets.view', 'tickets.escalate']}>
        <TicketRecommendationNotice ticketId={1} onEscalate={onEscalate} />
      </PermissionProvider>
    )

    await screen.findByText('Escalamiento recomendado')
    expect(screen.getByText(/35 min transcurridos/)).toBeInTheDocument()
    expect(screen.getByText(/Supervisor NOC/)).toBeInTheDocument()

    const escalateBtn = screen.getByRole('button', { name: 'Escalar ticket' })
    fireEvent.click(escalateBtn)
    expect(onEscalate).toHaveBeenCalledTimes(1)
  })

  it('permite registrar un reconocimiento ACK', async () => {
    const recResponse: TicketRecommendationsResponse = {
      ticket_id: 1,
      ticket_status: 'OPEN',
      stage_name: 'Etapa inicial',
      reference_position_id: 1,
      reference_position_name: 'Soporte N1',
      stage_started_at: '2026-10-25T10:00:00Z',
      elapsed_minutes: 35,
      has_active_ack: false,
      active_ack: null,
      recommendations: [
        {
          target_position_id: 2,
          target_position_name: 'Supervisor NOC',
          target_department_name: 'Operaciones',
          threshold_minutes: 30,
          elapsed_minutes: 35,
          overdue_minutes: 5,
        },
      ],
      can_acknowledge: true,
    }
    vi.mocked(recommendationsApi.getTicketRecommendations).mockResolvedValue(recResponse)
    vi.mocked(recommendationsApi.createTicketAck).mockResolvedValue({
      id: 10,
      ticket_id: 1,
      acknowledged_by: { id: 1, name: 'Operador Alfa', active: true },
      acknowledged_by_position: { id: 1, name: 'Soporte N1', active: true },
      acknowledged_at: '2026-10-25T10:35:00Z',
      duration_type: '4H',
      expires_at: '2026-10-25T14:35:00Z',
      reason: 'Se está validando en campo con cuadrilla',
      active: true,
      revoked_by: null,
      revoked_at: null,
      revoked_reason: null,
    })

    // Mock HTMLDialogElement methods in jsdom
    HTMLDialogElement.prototype.showModal = function () {
      this.setAttribute('open', '')
    }
    HTMLDialogElement.prototype.close = function () {
      this.removeAttribute('open')
    }

    render(
      <PermissionProvider permissions={['tickets.view', 'tickets.escalate']}>
        <TicketRecommendationNotice ticketId={1} />
      </PermissionProvider>
    )

    await screen.findByText('Escalamiento recomendado')
    const ackBtn = screen.getByRole('button', { name: /Reconocer \(ACK\)/ })
    fireEvent.click(ackBtn)

    const reasonInput = screen.getByLabelText(/Motivo del reconocimiento/i)
    fireEvent.change(reasonInput, { target: { value: 'Se está validando en campo con cuadrilla' } })

    const confirmBtn = screen.getByRole('button', { name: 'Confirmar reconocimiento' })
    fireEvent.click(confirmBtn)

    await waitFor(() => {
      expect(recommendationsApi.createTicketAck).toHaveBeenCalledWith(
        1,
        {
          duration_type: '1H',
          reason: 'Se está validando en campo con cuadrilla',
        },
        false
      )
    })
  })

  it('muestra alarma silenciada cuando hay un ACK activo y permite revocarlo', async () => {
    const ackActiveResponse: TicketRecommendationsResponse = {
      ticket_id: 1,
      ticket_status: 'OPEN',
      stage_name: 'Etapa inicial',
      reference_position_id: 1,
      reference_position_name: 'Soporte N1',
      stage_started_at: '2026-10-25T10:00:00Z',
      elapsed_minutes: 40,
      has_active_ack: true,
      active_ack: {
        id: 10,
        ticket_id: 1,
        acknowledged_by: { id: 1, name: 'Operador Alfa', active: true },
        acknowledged_by_position: { id: 1, name: 'Soporte N1', active: true },
        acknowledged_at: '2026-10-25T10:35:00Z',
        duration_type: '4H',
        expires_at: '2026-10-25T14:35:00Z',
        reason: 'Se está validando en campo con cuadrilla',
        active: true,
        revoked_by: null,
        revoked_at: null,
        revoked_reason: null,
      },
      recommendations: [],
      can_acknowledge: true,
    }
    vi.mocked(recommendationsApi.getTicketRecommendations).mockResolvedValue(ackActiveResponse)
    vi.mocked(recommendationsApi.revokeTicketAck).mockResolvedValue({
      ...ackActiveResponse.active_ack!,
      active: false,
      revoked_at: '2026-10-25T10:45:00Z',
    })

    render(
      <PermissionProvider permissions={['tickets.view', 'tickets.escalate']}>
        <TicketRecommendationNotice ticketId={1} />
      </PermissionProvider>
    )

    await screen.findByText('Recomendaciones de escalamiento reconocidas')
    expect(screen.getByText(/ACK 4H/)).toBeInTheDocument()
    expect(screen.getByText(/Operador Alfa/)).toBeInTheDocument()
    expect(screen.getByText(/«Se está validando en campo con cuadrilla»/)).toBeInTheDocument()

    const revokeBtn = screen.getByRole('button', { name: 'Retirar reconocimiento' })
    fireEvent.click(revokeBtn)

    await waitFor(() => {
      expect(recommendationsApi.revokeTicketAck).toHaveBeenCalledWith(
        1,
        { reason: 'Retiro manual' },
        false
      )
    })
  })
})
