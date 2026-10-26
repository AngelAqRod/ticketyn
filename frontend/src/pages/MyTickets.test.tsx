import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { MyTickets } from './MyTickets'
import * as api from '../api/myTickets'
import type { MyTicketsListResponse, MyTicketsSummaryResponse } from '../types/myTickets'

vi.mock('../api/myTickets', () => ({
  getMyTickets: vi.fn(),
  getMyTicketsSummary: vi.fn(),
}))

const mockSummary: MyTicketsSummaryResponse = {
  assigned_count: 5,
  participated_count: 12,
  escalations_count: 3,
  to_verify_count: 2,
}

const mockAssignedList: MyTicketsListResponse = {
  items: [
    {
      id: 101,
      ticket_type: 'CUSTOMER',
      reference: 'TK-2026-00101',
      title: 'Corte de fibra troncal',
      description: 'Cliente sin servicio',
      status: 'OPEN',
      created_at: '2026-10-25T10:00:00Z',
      start_at: '2026-10-25T10:00:00Z',
      end_at: null,
      responsible_id: 1,
      responsible_name: 'Alice Operadora',
      customer_name: 'Banco Central',
      customer_code: 'CLI-001',
      circuit_code: 'CKT-909',
      has_recommendation: true,
      recommendations_count: 1,
      provider_name: null,
      sector_name: 'Norte',
      node_name: 'Nodo Principal',
      department_name: 'NOC',
      incident_type_name: 'Fibra',
      escalation_id: null,
      escalation_status: null,
      escalation_reason: null,
      escalation_started_at: null,
      escalation_finished_at: null,
      escalation_description: null,
      escalation_requester_name: null,
      escalation_recipient_name: null,
      escalation_position_name: null,
      recommendation_stage: null,
      recommendation_elapsed_minutes: null,
      recommendation_threshold_minutes: null,
      recommendation_overdue_minutes: null,
      recommendation_target_position_name: null,
      recommendation_reference_position_name: null,
    },
  ],
  total: 1,
  limit: 20,
  offset: 0,
}

const mockEscalationsList: MyTicketsListResponse = {
  items: [
    {
      id: 202,
      ticket_type: 'INTERNAL',
      reference: 'TI-2026-00202',
      title: 'Falla BGP Core',
      description: 'Revisión técnica de enrutamiento',
      status: 'OPEN',
      created_at: '2026-10-25T11:00:00Z',
      start_at: '2026-10-25T11:00:00Z',
      end_at: null,
      responsible_id: 2,
      responsible_name: 'Bob Inicial',
      customer_name: null,
      customer_code: null,
      circuit_code: null,
      has_recommendation: false,
      recommendations_count: 0,
      provider_name: 'CarrierX',
      sector_name: 'Datacenter',
      node_name: null,
      department_name: 'NOC',
      incident_type_name: 'Core',
      escalation_id: 50,
      escalation_status: 'ACTIVE',
      escalation_reason: 'N2 requerido',
      escalation_started_at: '2026-10-25T11:30:00Z',
      escalation_finished_at: null,
      escalation_description: 'Escalando a Ingeniería',
      escalation_requester_name: 'Carlos Solicitante',
      escalation_recipient_name: 'Ingeniero Destino',
      escalation_position_name: 'Ingeniería',
      recommendation_stage: null,
      recommendation_elapsed_minutes: null,
      recommendation_threshold_minutes: null,
      recommendation_overdue_minutes: null,
      recommendation_target_position_name: null,
      recommendation_reference_position_name: null,
    },
  ],
  total: 1,
  limit: 20,
  offset: 0,
}

const mockToVerifyList: MyTicketsListResponse = {
  items: [
    {
      id: 303,
      ticket_type: 'CUSTOMER',
      reference: 'TK-2026-00303',
      title: 'Alerta sin atención en tiempo',
      description: 'Superado umbral de 20 min',
      status: 'OPEN',
      created_at: '2026-10-25T12:00:00Z',
      start_at: '2026-10-25T12:00:00Z',
      end_at: null,
      responsible_id: 3,
      responsible_name: 'Operador N1',
      customer_name: 'Finanzas Sur',
      customer_code: 'CLI-002',
      circuit_code: 'CKT-100',
      has_recommendation: true,
      recommendations_count: 1,
      provider_name: null,
      sector_name: 'Sur',
      node_name: 'Nodo Sur',
      department_name: 'NOC',
      incident_type_name: 'Enlace',
      escalation_id: null,
      escalation_status: null,
      escalation_reason: null,
      escalation_started_at: null,
      escalation_finished_at: null,
      escalation_description: null,
      escalation_requester_name: null,
      escalation_recipient_name: null,
      escalation_position_name: null,
      recommendation_stage: 'Etapa inicial',
      recommendation_elapsed_minutes: 35,
      recommendation_threshold_minutes: 20,
      recommendation_overdue_minutes: 15,
      recommendation_target_position_name: 'Supervisor',
      recommendation_reference_position_name: 'Soporte',
    },
  ],
  total: 1,
  limit: 20,
  offset: 0,
}

const flush = async () => {
  await act(async () => {
    await Promise.resolve()
  })
}

const advance = async (ms: number) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

function renderComponent(initialRoute = '/my-tickets') {
  return render(
    <MemoryRouter initialEntries={[initialRoute]}>
      <Routes>
        <Route path="/my-tickets" element={<MyTickets />} />
        <Route path="/my-tickets/:tab" element={<MyTickets />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('Módulo «Mis tickets»', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    })
    vi.mocked(api.getMyTicketsSummary).mockResolvedValue(mockSummary)
    vi.mocked(api.getMyTickets).mockResolvedValue(mockAssignedList)
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('renderiza encabezado, tarjetas de resumen y listado de asignados', async () => {
    renderComponent()
    await flush()

    // Encabezado
    expect(screen.getByRole('heading', { name: 'Mis tickets' })).toBeInTheDocument()
    expect(screen.getByText('PERSONAL')).toBeInTheDocument()

    // Summary indicators
    const summarySection = screen.getByRole('region', { name: 'Resumen de mis tickets' })
    expect(within(summarySection).getByText('Asignados a mí')).toBeInTheDocument()
    expect(within(summarySection).getByText('He participado')).toBeInTheDocument()
    expect(within(summarySection).getByText('Mis escalamientos')).toBeInTheDocument()
    expect(within(summarySection).getByText('Por verificar')).toBeInTheDocument()
    expect(within(summarySection).getByText('5')).toBeInTheDocument()
    expect(within(summarySection).getByText('12')).toBeInTheDocument()
    expect(within(summarySection).getByText('3')).toBeInTheDocument()
    expect(within(summarySection).getByText('2')).toBeInTheDocument()

    // Ticket en asignados con recomendación activa
    expect(screen.getByText('TK-2026-00101')).toBeInTheDocument()
    expect(screen.getByText('Corte de fibra troncal')).toBeInTheDocument()
    expect(screen.getByText('Recom. activa')).toBeInTheDocument()
  })

  it('permite cambiar entre vistas de pestañas y carga la información correspondiente', async () => {
    vi.mocked(api.getMyTickets).mockImplementation(async (params) => {
      if (params?.view === 'escalations') return mockEscalationsList
      if (params?.view === 'to_verify') return mockToVerifyList
      return mockAssignedList
    })

    renderComponent()
    await flush()

    // Cambiar a "Mis escalamientos"
    const tabs = screen.getByRole('tablist', { name: 'Vistas de mis tickets' })
    const escTab = within(tabs).getByRole('tab', { name: 'Mis escalamientos' })
    fireEvent.click(escTab)
    await flush()

    expect(api.getMyTickets).toHaveBeenCalledWith(
      expect.objectContaining({ view: 'escalations' }),
      expect.any(AbortSignal)
    )
    expect(screen.getByText('Escalamientos asignados a mí')).toBeInTheDocument()
    expect(screen.getByText('TI-2026-00202')).toBeInTheDocument()
    expect(screen.getByText('Falla BGP Core')).toBeInTheDocument()
    expect(screen.getByText('Carlos Solicitante')).toBeInTheDocument()
    expect(screen.getByText('Ingeniería')).toBeInTheDocument()
    expect(screen.getByText('Bob Inicial')).toBeInTheDocument()

    // Cambiar a "Por verificar"
    const tvTab = within(tabs).getByRole('tab', { name: /Por verificar/ })
    fireEvent.click(tvTab)
    await flush()

    expect(api.getMyTickets).toHaveBeenCalledWith(
      expect.objectContaining({ view: 'to_verify' }),
      expect.any(AbortSignal)
    )
    expect(screen.getByText('TK-2026-00303')).toBeInTheDocument()
    expect(screen.getByText('Supervisor')).toBeInTheDocument()
    expect(screen.getByText('+15 min')).toBeInTheDocument()
    expect(screen.getByText('Escalamiento requerido')).toBeInTheDocument()
  })

  it('realiza polling cada 60 segundos en «Por verificar» mientras está visible', async () => {
    vi.mocked(api.getMyTickets).mockResolvedValue(mockToVerifyList)
    renderComponent('/my-tickets?view=to_verify')
    await flush()

    expect(api.getMyTickets).toHaveBeenCalledTimes(1)

    // Avanza 59.9s -> no debe llamar aún
    await advance(59_999)
    expect(api.getMyTickets).toHaveBeenCalledTimes(1)

    // Cumple 60s -> llamada de refresco
    await advance(1)
    await flush()
    expect(api.getMyTickets).toHaveBeenCalledTimes(2)

    // Otros 60s -> tercera llamada
    await advance(60_000)
    await flush()
    expect(api.getMyTickets).toHaveBeenCalledTimes(3)
  })

  it('pausa el polling cuando la ventana está oculta (document.visibilityState = hidden)', async () => {
    vi.mocked(api.getMyTickets).mockResolvedValue(mockToVerifyList)
    renderComponent('/my-tickets?view=to_verify')
    await flush()

    expect(api.getMyTickets).toHaveBeenCalledTimes(1)

    // Ocultar pestaña
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    })
    fireEvent(document, new Event('visibilitychange'))
    await flush()

    // Avanzar tiempo mientras está oculta -> no debe llamar a la API
    await advance(180_000)
    expect(api.getMyTickets).toHaveBeenCalledTimes(1)

    // Volver a hacer visible
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    })
    fireEvent(document, new Event('visibilitychange'))
    await flush()

    // Debe reanudar y consultar inmediatamente
    expect(api.getMyTickets).toHaveBeenCalledTimes(2)
  })

  it('muestra el estado vacío adecuado cuando no hay tickets', async () => {
    vi.mocked(api.getMyTickets).mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 })
    const { unmount } = renderComponent('/my-tickets?view=assigned')
    await flush()
    expect(screen.getByText('No tienes tickets asignados actualmente.')).toBeInTheDocument()
    unmount()

    // Comprobar estado vacío en escalamientos
    renderComponent('/my-tickets?view=escalations')
    await flush()
    expect(screen.getByText('No tienes escalamientos asignados actualmente.')).toBeInTheDocument()
    expect(
      screen.getByText('Los escalamientos donde figures como responsable asignado aparecerán aquí.')
    ).toBeInTheDocument()
  })

  it('conserva la vista indicada por la URL en recarga y admite parámetros view, tab o ruta', async () => {
    vi.mocked(api.getMyTickets).mockResolvedValue(mockAssignedList)

    // 1. ?view=escalations
    const r1 = renderComponent('/my-tickets?view=escalations')
    await flush()
    expect(api.getMyTickets).toHaveBeenLastCalledWith(
      expect.objectContaining({ view: 'escalations' }),
      expect.any(Object)
    )
    r1.unmount()

    // 2. ?tab=participated
    const r2 = renderComponent('/my-tickets?tab=participated')
    await flush()
    expect(api.getMyTickets).toHaveBeenLastCalledWith(
      expect.objectContaining({ view: 'participated' }),
      expect.any(Object)
    )
    r2.unmount()

    // 3. ?tab=verify (normaliza a to_verify)
    const r3 = renderComponent('/my-tickets?tab=verify')
    await flush()
    expect(api.getMyTickets).toHaveBeenLastCalledWith(
      expect.objectContaining({ view: 'to_verify' }),
      expect.any(Object)
    )
    r3.unmount()

    // 4. /my-tickets/escalations (ruta con path param)
    const r4 = renderComponent('/my-tickets/escalations')
    await flush()
    expect(api.getMyTickets).toHaveBeenLastCalledWith(
      expect.objectContaining({ view: 'escalations' }),
      expect.any(Object)
    )
    r4.unmount()
  })
})
