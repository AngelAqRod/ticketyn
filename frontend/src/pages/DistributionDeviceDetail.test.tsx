import { MemoryRouter, Route, Routes } from 'react-router'
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '../test/render'
import { PermissionProvider } from '../auth/permissions'
import { DistributionDeviceDetail } from './DistributionDeviceDetail'
import type { Node } from '../types/catalog'
import type {
  DistributionCircuit,
  DistributionDevice,
  DistributionPort,
} from '../types/distribution'
import { portGenerationResponse } from '../test/portGeneration'
import { jsonResponse } from '../test/fixtures'

const mockNode: Node = { id: 1, name: 'Nodo Central', active: true, created_at: '' }

const mockDevice: DistributionDevice = {
  id: 10,
  node_id: 1,
  name: 'Switch-Core-01',
  description: 'Switch troncal de fibra',
  active: true,
  port_count: 3,
  circuit_count: 4,
  created_at: '2026-01-01T10:00:00Z',
}

const mockPortWithCircuits: DistributionPort = {
  id: 20,
  distribution_device_id: 10,
  name: 'sfp+1',
  description: 'Enlace troncal 10G',
  active: true,
  circuit_count: 2,
  created_at: '2026-01-01T10:00:00Z',
}

const mockPortMultiCircuits: DistributionPort = {
  id: 21,
  distribution_device_id: 10,
  name: 'ge-0/0/1',
  description: 'Puerto multi-servicio',
  active: true,
  circuit_count: 1,
  created_at: '2026-01-01T10:00:00Z',
}

const mockPortWithoutCircuits: DistributionPort = {
  id: 22,
  distribution_device_id: 10,
  name: 'ge-0/0/2',
  description: null,
  active: true,
  circuit_count: 0,
  created_at: '2026-01-01T10:00:00Z',
}

const mockPorts = [mockPortWithCircuits, mockPortMultiCircuits, mockPortWithoutCircuits]

const mockCircuit1: DistributionCircuit = {
  id: 101,
  circuit_code: 'CKT-CORP-001',
  description: 'Enlace Corporativo Principal',
  active: true,
  customer_id: 1,
  customer_code: 'CLI-001',
  customer_name: 'Banco Financiero',
  service_type_id: 1,
  service_type_name: 'Fibra Dedicada',
  distribution_port_id: 20,
  distribution_port_name: 'sfp+1',
}

const mockCircuit2: DistributionCircuit = {
  id: 102,
  circuit_code: 'CKT-CORP-002',
  description: 'Enlace Redundante',
  active: true,
  customer_id: 1,
  customer_code: 'CLI-001',
  customer_name: 'Banco Financiero',
  service_type_id: 1,
  service_type_name: 'Fibra Dedicada',
  distribution_port_id: 20,
  distribution_port_name: 'sfp+1',
}

const mockCircuitWithoutPort: DistributionCircuit = {
  id: 103,
  circuit_code: 'CKT-PEND-003',
  description: 'Enlace asignado a equipo sin puerto',
  active: false,
  customer_id: 2,
  customer_code: 'CLI-002',
  customer_name: 'Seguros del Sur',
  service_type_id: 2,
  service_type_name: 'Internet Empresas',
  distribution_port_id: null,
  distribution_port_name: null,
}

const mockCircuits = [mockCircuit1, mockCircuit2, mockCircuitWithoutPort]

const allPermissions = [
  'distribution_devices.view',
  'distribution_devices.lookup',
  'distribution_devices.create',
  'distribution_devices.edit',
  'distribution_devices.move',
  'distribution_devices.set_active',
  'distribution_devices.delete',
  'distribution_ports.view',
  'distribution_ports.lookup',
  'distribution_ports.create',
  'distribution_ports.edit',
  'distribution_ports.move',
  'distribution_ports.set_active',
  'distribution_ports.delete',
  'circuits.view',
]

const originalShow = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal')
const originalClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close')

beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
    configurable: true,
    value(this: HTMLDialogElement) {
      this.setAttribute('open', '')
    },
  })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', {
    configurable: true,
    value(this: HTMLDialogElement) {
      this.removeAttribute('open')
    },
  })
})

afterAll(() => {
  if (originalShow) Object.defineProperty(HTMLDialogElement.prototype, 'showModal', originalShow)
  if (originalClose) Object.defineProperty(HTMLDialogElement.prototype, 'close', originalClose)
})

function setupDetailFetchMock(
  dev: DistributionDevice = mockDevice,
  portsList: DistributionPort[] = mockPorts,
  circuitsList: DistributionCircuit[] = mockCircuits,
) {
  const mock = vi.fn((input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost')
    const generation = portGenerationResponse(url, init, portsList)
    if (generation) return generation

    if (url.pathname === '/api/nodes') {
      return Promise.resolve(jsonResponse([mockNode]))
    }

    if (url.pathname === `/api/distribution-devices/${dev.id}` && (!init?.method || init.method === 'GET')) {
      return Promise.resolve(jsonResponse(dev))
    }

    if (url.pathname === '/api/distribution-devices' && (!init?.method || init.method === 'GET')) {
      return Promise.resolve(jsonResponse([dev]))
    }

    if (url.pathname === '/api/distribution-ports' && (!init?.method || init.method === 'GET')) {
      return Promise.resolve(jsonResponse(portsList))
    }

    if (
      url.pathname === `/api/distribution-devices/${dev.id}/circuits` &&
      (!init?.method || init.method === 'GET')
    ) {
      let filtered = [...circuitsList]
      const portId = url.searchParams.get('port_id')
      if (portId) {
        filtered = filtered.filter((c) => c.distribution_port_id === Number(portId))
      }
      const withoutPort = url.searchParams.get('without_port') === 'true'
      if (withoutPort) {
        filtered = filtered.filter((c) => c.distribution_port_id === null)
      }
      return Promise.resolve(jsonResponse(filtered))
    }

    // Port edit
    if (url.pathname.match(/\/api\/distribution-ports\/\d+$/) && init?.method === 'PATCH') {
      const body = JSON.parse(String(init.body))
      const portId = Number(url.pathname.split('/').pop())
      const found = portsList.find((p) => p.id === portId) ?? mockPortWithCircuits
      return Promise.resolve(jsonResponse({ ...found, ...body }))
    }

    // Port move
    if (url.pathname.match(/\/api\/distribution-ports\/\d+\/move$/) && init?.method === 'POST') {
      const portId = Number(url.pathname.split('/')[3])
      const found = portsList.find((p) => p.id === portId) ?? mockPortWithCircuits
      if (found.circuit_count > 0) {
        return Promise.resolve(
          jsonResponse(
            { detail: 'El recurso tiene circuitos asociados, incluidos los inactivos.' },
            409,
          ),
        )
      }
      const body = JSON.parse(String(init.body))
      return Promise.resolve(jsonResponse({ ...found, distribution_device_id: body.distribution_device_id }))
    }

    // Port status
    if (url.pathname.match(/\/api\/distribution-ports\/\d+\/status$/) && init?.method === 'PATCH') {
      const portId = Number(url.pathname.split('/')[3])
      const found = portsList.find((p) => p.id === portId) ?? mockPortWithCircuits
      const body = JSON.parse(String(init.body))
      return Promise.resolve(jsonResponse({ ...found, active: body.active }))
    }

    // Port delete
    if (url.pathname.match(/\/api\/distribution-ports\/\d+$/) && init?.method === 'DELETE') {
      return Promise.resolve(new Response(null, { status: 204 }))
    }

    return Promise.resolve(jsonResponse([]))
  })

  vi.stubGlobal('fetch', mock)
  return mock
}

function renderDetail(permissions = allPermissions, entry = '/distribution-devices/10') {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <PermissionProvider permissions={permissions}>
        <Routes>
          <Route path="distribution-devices/:id" element={<DistributionDeviceDetail />} />
        </Routes>
      </PermissionProvider>
    </MemoryRouter>,
  )
}

describe('DistributionDeviceDetail — Ficha técnica y gestión de puertos', () => {
  it('conserva el orden natural de la API en la tabla Puertos del equipo con 24 puertos históricos', async () => {
    const ports = Array.from({ length: 24 }, (_, index) => ({
      ...mockPortWithoutCircuits, id: 100 + index, name: `SFP${index + 1}`, nomenclature_id: null,
    }))
    setupDetailFetchMock({ ...mockDevice, port_count: 24, circuit_count: 0 }, ports, [])
    renderDetail()
    const section = within(await screen.findByRole('region', { name: 'Puertos del equipo' }))
    const names = section.getAllByRole('row').slice(1).map(row => within(row).getAllByRole('cell')[0].textContent)
    expect(names).toEqual(Array.from({ length: 24 }, (_, index) => `SFP${index + 1}`))
  })
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renderiza encabezado, nodo, estado y enlace de retorno', async () => {
    setupDetailFetchMock()
    renderDetail()

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Switch-Core-01' })).toBeInTheDocument()
    })

    expect(screen.getByText(/Nodo: Nodo Central/i)).toBeInTheDocument()
    expect(screen.getByText('Volver a equipos de distribución')).toBeInTheDocument()
    expect(screen.getAllByText('Activo').length).toBeGreaterThanOrEqual(1)
  })

  it('muestra los cuatro indicadores del resumen operativo con conteos precisos', async () => {
    setupDetailFetchMock()
    renderDetail()

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Switch-Core-01' })).toBeInTheDocument()
    })

    const summarySection = within(screen.getByLabelText('Resumen operativo del equipo'))
    expect(summarySection.getByText('Total de puertos')).toBeInTheDocument()
    expect(summarySection.getByText('3')).toBeInTheDocument()
    expect(summarySection.getByText('Con circuitos')).toBeInTheDocument()
    expect(summarySection.getByText('2')).toBeInTheDocument()
    expect(summarySection.getByText('Sin circuitos')).toBeInTheDocument()
    expect(summarySection.getByText('1')).toBeInTheDocument()
    expect(summarySection.getByText('Total de circuitos')).toBeInTheDocument()
    expect(summarySection.getByText('4')).toBeInTheDocument()

    // Verification that disclaimer exists (logical Ticketyn records, not physical interface state)
    expect(screen.getByText(/Los conteos representan registros lógicos configurados en Ticketyn/i)).toBeInTheDocument()
  })

  it('muestra todos los puertos registrados, etiquetando con «Sin circuitos asociados» los que tienen 0 circuitos', async () => {
    setupDetailFetchMock()
    renderDetail()

    await waitFor(() => {
      expect(screen.getAllByText('sfp+1')[0]).toBeInTheDocument()
    })

    const portsSection = within(screen.getByLabelText('Puertos del equipo'))
    expect(portsSection.getByText('ge-0/0/1')).toBeInTheDocument()
    expect(portsSection.getByText('ge-0/0/2')).toBeInTheDocument()

    // Port with 0 circuits must display exact text: "Sin circuitos asociados"
    expect(portsSection.getByText('Sin circuitos asociados')).toBeInTheDocument()

    // Must NEVER show forbidden misleading strings like "Puerto libre" or "disponible físicamente"
    expect(screen.queryByText(/Puerto libre/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/disponible físicamente/i)).not.toBeInTheDocument()
  })

  it('muestra circuitos asociados, enlaces a fichas de circuito y cliente', async () => {
    setupDetailFetchMock()
    renderDetail()

    await waitFor(() => {
      expect(screen.getByText('CKT-CORP-001')).toBeInTheDocument()
    })

    expect(screen.getByText('CKT-CORP-002')).toBeInTheDocument()
    expect(screen.getByText('CKT-PEND-003')).toBeInTheDocument()

    expect(screen.getAllByText(/Banco Financiero/i).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/Seguros del Sur/i)).toBeInTheDocument()

    // Verify circuit code links to circuit detail
    const circuitLink = screen.getByRole('link', { name: 'CKT-CORP-001' })
    expect(circuitLink).toHaveAttribute('href', '/circuits/101')
  })

  it('identifica claramente los «Circuitos sin puerto asignado»', async () => {
    setupDetailFetchMock()
    renderDetail()

    await waitFor(() => {
      expect(screen.getByText('CKT-PEND-003')).toBeInTheDocument()
    })

    // Group button or table cell with exact text
    expect(screen.getAllByText('Circuitos sin puerto asignado').length).toBeGreaterThanOrEqual(1)
  })

  it('filtra los circuitos asociados al pulsar sobre un puerto específico', async () => {
    setupDetailFetchMock()
    renderDetail()

    await waitFor(() => {
      expect(screen.getAllByText('sfp+1')[0]).toBeInTheDocument()
    })

    // Click on port filter button in table: "2 circuitos"
    const portFilterBtn = screen.getByRole('button', { name: '2 circuitos' })
    fireEvent.click(portFilterBtn)

    await waitFor(() => {
      expect(screen.getByText(/Filtrando por puerto:/i)).toBeInTheDocument()
    })
  })

  it('crea un nuevo puerto asociado automáticamente al equipo actual sin volver a solicitarlo', async () => {
    const fetchMock = setupDetailFetchMock()
    renderDetail(allPermissions)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Nuevo puerto/i })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Nuevo puerto/i }))

    expect(screen.getByRole('heading', { name: 'Nuevo puerto de distribución' })).toBeInTheDocument()

    // Verify inherited device name is displayed
    expect(within(screen.getByRole('dialog')).getByText('Switch-Core-01')).toBeInTheDocument()

    const nomenclature = await screen.findByRole('combobox', { name: 'Nomenclatura' })
    await waitFor(() => expect(nomenclature).toBeEnabled()); fireEvent.click(nomenclature); fireEvent.click(screen.getByRole('option', { name: 'Fibra (sfp+)' }))
    fireEvent.change(screen.getByLabelText(/^Número del puerto/), { target: { value: '2' } })
    const submitBtn = screen.getByRole('button', { name: 'Crear puertos' })
    await waitFor(() => expect(submitBtn).toBeEnabled()); fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(screen.getByText(/Se creó el puerto «sfp\+2» con éxito/i)).toBeInTheDocument()
    })

    const postCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        url.toString().endsWith('/api/distribution-ports') && init?.method === 'POST',
    )
    expect(postCall).toBeDefined()
    expect(JSON.parse(String(postCall![1]?.body))).toMatchObject({ distribution_device_id: 10, nomenclature_id: 90, start: 2, preview_token: 'checked' })
  })

  it('bloquea el traslado de un puerto que tiene circuitos asociados', async () => {
    setupDetailFetchMock()
    renderDetail(allPermissions)

    await waitFor(() => {
      expect(screen.getAllByText('sfp+1')[0]).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Trasladar puerto sfp+1' }))

    expect(screen.getByRole('heading', { name: 'Trasladar puerto a otro equipo' })).toBeInTheDocument()

    // Must show blocking message because it has 2 circuits
    expect(screen.getByText(/Bloqueado: El puerto tiene 2 circuitos asociados/i)).toBeInTheDocument()

    const submitBtn = screen.getByRole('button', { name: 'Confirmar traslado' })
    expect(submitBtn).toBeDisabled()
  })

  it('bloquea la desactivación y eliminación de un puerto con circuitos', async () => {
    setupDetailFetchMock()
    renderDetail(allPermissions)

    await waitFor(() => {
      expect(screen.getAllByText('sfp+1')[0]).toBeInTheDocument()
    })

    // Attempt deactivate port with 2 circuits
    fireEvent.click(screen.getByRole('button', { name: 'Desactivar puerto sfp+1' }))
    expect(screen.getByText(/El puerto tiene 2 circuitos asociados.*No se puede desactivar/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Confirmar desactivar' })).not.toBeInTheDocument()

    // Close modal
    fireEvent.click(screen.getByRole('button', { name: 'Entendido' }))

    // Attempt delete port with 2 circuits
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar puerto sfp+1' }))
    expect(screen.getByText(/El puerto tiene 2 circuitos asociados/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Eliminar puerto' })).not.toBeInTheDocument()
  })

  it('permite desactivar y eliminar un puerto sin circuitos asociados', async () => {
    const fetchMock = setupDetailFetchMock()
    renderDetail(allPermissions)

    await waitFor(() => {
      expect(screen.getByText('ge-0/0/2')).toBeInTheDocument()
    })

    // ge-0/0/2 has 0 circuits
    fireEvent.click(screen.getByRole('button', { name: 'Desactivar puerto ge-0/0/2' }))
    expect(screen.getByRole('button', { name: 'Confirmar desactivar' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar desactivar' }))

    await waitFor(() => {
      expect(screen.getByText(/Se desactivó el puerto «ge-0\/0\/2»/i)).toBeInTheDocument()
    })

    // Now delete
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar puerto ge-0/0/2' }))
    const deleteBtn = screen.getByRole('button', { name: 'Eliminar puerto' })
    fireEvent.click(deleteBtn)

    await waitFor(() => {
      expect(screen.getByText(/Se eliminó el puerto «ge-0\/0\/2» con éxito/i)).toBeInTheDocument()
    })
  })

  it('muestra mensaje claro cuando el usuario carece de permiso circuits.view', async () => {
    const permissionsWithoutCircuitsView = allPermissions.filter((p) => p !== 'circuits.view')
    setupDetailFetchMock()
    renderDetail(permissionsWithoutCircuitsView)

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Switch-Core-01' })).toBeInTheDocument()
    })

    expect(screen.getByText('Sin permiso para consultar circuitos asociados.')).toBeInTheDocument()
    expect(screen.queryByText('CKT-CORP-001')).not.toBeInTheDocument()
  })
})


it('utiliza el contador completo del equipo aunque la página de puertos sea parcial', async () => {
  setupDetailFetchMock({ ...mockDevice, port_count: 203, unassigned_port_count: 201 }, [mockPortWithCircuits])
  renderDetail()
  await screen.findByRole('heading', { name: mockDevice.name })
  const summary = screen.getByLabelText('Resumen operativo del equipo')
  expect(within(summary).getByText('Sin circuitos').parentElement).toHaveTextContent('201')
  expect(within(summary).getByText('Total de puertos').parentElement).toHaveTextContent('203')
  expect(within(summary).getByText('Con circuitos').parentElement).toHaveTextContent('2')
})
