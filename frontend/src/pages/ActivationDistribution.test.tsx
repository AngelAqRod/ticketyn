import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { ActivationDetail } from './ActivationDetail'
import { OperationsTable } from '../components/OperationsTable'
import { OperationModal } from '../components/OperationModal'
import { activationDistributionLabel } from '../types/fms'
import type { Operation } from '../types/fms'
import type { Circuit } from '../types/catalog'

const jsonResponse = (data: unknown, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  headers: new Headers({ 'content-type': 'application/json' }),
  json: () => Promise.resolve(data),
  text: () => Promise.resolve(JSON.stringify(data)),
})

describe('FMS Activations - Distribución (Ticketyn v0.8.0)', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    HTMLDialogElement.prototype.showModal = vi.fn()
    HTMLDialogElement.prototype.close = vi.fn()
  })

  it('helper activationDistributionLabel resuelve correctamente los tres estados', () => {
    const withDist = {
      distribution_recorded: true,
      distribution_device_name: 'SW-DIST-01',
      distribution_port_name: 'gi1/0/24',
    } as Operation
    expect(activationDistributionLabel(withDist, 'distribution_device_name')).toBe('SW-DIST-01')
    expect(activationDistributionLabel(withDist, 'distribution_port_name')).toBe('gi1/0/24')

    const unassigned = {
      distribution_recorded: true,
      distribution_device_name: null,
      distribution_port_name: null,
    } as Operation
    expect(activationDistributionLabel(unassigned, 'distribution_device_name')).toBe('No asignado')
    expect(activationDistributionLabel(unassigned, 'distribution_port_name')).toBe('No asignado')

    const historical = {
      distribution_recorded: false,
      distribution_device_name: null,
      distribution_port_name: null,
    } as Operation
    expect(activationDistributionLabel(historical, 'distribution_device_name')).toBe('No registrado')
    expect(activationDistributionLabel(historical, 'distribution_port_name')).toBe('No registrado')
  })

  it('ActivationDetail presenta Equipo de distribución y Puerto con asignación', async () => {
    const act: Operation = {
      id: 10,
      circuit_id: 1,
      circuit: {
        id: 1,
        customer_id: 1,
        circuit_code: 'CIR-001',
        description: 'Enlace principal',
        active: true,
        created_at: '2026-01-01T00:00:00Z',
      },
      responsible_id: 1,
      responsible: { id: 1, name: 'Operador NOC', active: true },
      effective_at: '2026-01-01T12:00:00Z',
      created_at: '2026-01-01T12:00:00Z',
      reference: 'ACT-000010',
      distribution_recorded: true,
      distribution_device_name: 'OLT-HUAWEI-01',
      distribution_port_name: 'gpon-0/1/2',
    }

    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/api/activations/10/interventions')) return Promise.resolve(jsonResponse([]))
      if (url.includes('/api/activations/10/notification')) return Promise.resolve(jsonResponse({ activation_id: 10, mode: 'DISABLED' }))
      if (url.includes('/api/activations/10')) return Promise.resolve(jsonResponse(act))
      if (url.includes('/api/customers/1')) return Promise.resolve(jsonResponse({ id: 1, name: 'Cliente Corporativo', customer_code: 'CLI-01' }))
      if (url.includes('/api/responsibles')) return Promise.resolve(jsonResponse([]))
      return Promise.resolve(jsonResponse({}))
    }))

    render(
      <MemoryRouter initialEntries={['/activations/10']}>
        <Routes>
          <Route path="/activations/:id" element={<ActivationDetail />} />
        </Routes>
      </MemoryRouter>
    )

    expect(await screen.findByText('ACT-000010')).toBeInTheDocument()
    expect(screen.getByText('OLT-HUAWEI-01')).toBeInTheDocument()
    expect(screen.getByText('gpon-0/1/2')).toBeInTheDocument()
  })

  it('ActivationDetail presenta «No asignado» cuando el circuito no tenía equipo ni puerto', async () => {
    const act: Operation = {
      id: 11,
      circuit_id: 1,
      circuit: {
        id: 1,
        customer_id: 1,
        circuit_code: 'CIR-001',
        description: 'Enlace sin distribución',
        active: true,
        created_at: '2026-01-01T00:00:00Z',
      },
      responsible_id: 1,
      responsible: { id: 1, name: 'Operador NOC', active: true },
      effective_at: '2026-01-01T12:00:00Z',
      created_at: '2026-01-01T12:00:00Z',
      reference: 'ACT-000011',
      distribution_recorded: true,
      distribution_device_name: null,
      distribution_port_name: null,
    }

    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/api/activations/11/interventions')) return Promise.resolve(jsonResponse([]))
      if (url.includes('/api/activations/11/notification')) return Promise.resolve(jsonResponse({ activation_id: 11, mode: 'DISABLED' }))
      if (url.includes('/api/activations/11')) return Promise.resolve(jsonResponse(act))
      if (url.includes('/api/customers/1')) return Promise.resolve(jsonResponse({ id: 1, name: 'Cliente Corporativo', customer_code: 'CLI-01' }))
      if (url.includes('/api/responsibles')) return Promise.resolve(jsonResponse([]))
      return Promise.resolve(jsonResponse({}))
    }))

    render(
      <MemoryRouter initialEntries={['/activations/11']}>
        <Routes>
          <Route path="/activations/:id" element={<ActivationDetail />} />
        </Routes>
      </MemoryRouter>
    )

    expect(await screen.findByText('ACT-000011')).toBeInTheDocument()
    const unassigned = screen.getAllByText('No asignado')
    expect(unassigned.length).toBeGreaterThanOrEqual(2)
  })

  it('ActivationDetail presenta «No registrado» para activaciones anteriores a la funcionalidad', async () => {
    const act: Operation = {
      id: 12,
      circuit_id: 1,
      circuit: {
        id: 1,
        customer_id: 1,
        circuit_code: 'CIR-001',
        description: 'Enlace histórico',
        active: true,
        created_at: '2020-01-01T00:00:00Z',
      },
      responsible_id: 1,
      responsible: { id: 1, name: 'Operador NOC', active: true },
      effective_at: '2020-01-01T12:00:00Z',
      created_at: '2020-01-01T12:00:00Z',
      reference: 'ACT-000012',
      distribution_recorded: false,
      distribution_device_name: null,
      distribution_port_name: null,
    }

    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/api/activations/12/interventions')) return Promise.resolve(jsonResponse([]))
      if (url.includes('/api/activations/12/notification')) return Promise.resolve(jsonResponse({ activation_id: 12, mode: 'DISABLED' }))
      if (url.includes('/api/activations/12')) return Promise.resolve(jsonResponse(act))
      if (url.includes('/api/customers/1')) return Promise.resolve(jsonResponse({ id: 1, name: 'Cliente Corporativo', customer_code: 'CLI-01' }))
      if (url.includes('/api/responsibles')) return Promise.resolve(jsonResponse([]))
      return Promise.resolve(jsonResponse({}))
    }))

    render(
      <MemoryRouter initialEntries={['/activations/12']}>
        <Routes>
          <Route path="/activations/:id" element={<ActivationDetail />} />
        </Routes>
      </MemoryRouter>
    )

    expect(await screen.findByText('ACT-000012')).toBeInTheDocument()
    const notRegistered = screen.getAllByText('No registrado')
    expect(notRegistered.length).toBeGreaterThanOrEqual(2)
  })

  it('OperationsTable incluye encabezados y valores de distribución para activaciones', () => {
    const items: Operation[] = [
      {
        id: 1,
        circuit_id: 1,
        circuit: { id: 1, customer_id: 1, circuit_code: 'CIR-100', description: 'Desc', active: true, created_at: '' },
        responsible_id: 1,
        responsible: { id: 1, name: 'Operador', active: true },
        effective_at: '2026-01-01T00:00:00Z',
        created_at: '2026-01-01T00:00:00Z',
        reference: 'ACT-100',
        distribution_recorded: true,
        distribution_device_name: 'SWITCH-01',
        distribution_port_name: 'p1',
      },
      {
        id: 2,
        circuit_id: 1,
        circuit: { id: 1, customer_id: 1, circuit_code: 'CIR-101', description: 'Desc', active: true, created_at: '' },
        responsible_id: 1,
        responsible: { id: 1, name: 'Operador', active: true },
        effective_at: '2026-01-01T00:00:00Z',
        created_at: '2026-01-01T00:00:00Z',
        reference: 'ACT-101',
        distribution_recorded: true,
        distribution_device_name: null,
        distribution_port_name: null,
      },
    ]

    render(
      <MemoryRouter>
        <OperationsTable kind="activations" items={items} />
      </MemoryRouter>
    )

    expect(screen.getByRole('columnheader', { name: 'Equipo de distribución' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Puerto' })).toBeInTheDocument()
    expect(screen.getByText('SWITCH-01')).toBeInTheDocument()
    expect(screen.getByText('p1')).toBeInTheDocument()
    expect(screen.getAllByText('No asignado').length).toBe(2)
  })

  it('OperationModal en activaciones muestra la distribución del circuito seleccionado', () => {
    const circuit: Circuit = {
      id: 5,
      customer_id: 2,
      circuit_code: 'CIR-DIST',
      description: 'Circuito con equipo',
      active: true,
      created_at: '',
      distribution_device: { id: 1, name: 'OLT-SUR-01', active: true },
      distribution_port: { id: 10, name: 'pon-1', active: true },
    }

    render(
      <MemoryRouter>
        <OperationModal kind="activations" circuit={circuit} onCancel={vi.fn()} onSaved={vi.fn()} />
      </MemoryRouter>
    )

    const distSection = screen.getByLabelText('Distribución actual del circuito')
    expect(within(distSection).getByText('OLT-SUR-01')).toBeInTheDocument()
    expect(within(distSection).getByText('pon-1')).toBeInTheDocument()
  })
})
