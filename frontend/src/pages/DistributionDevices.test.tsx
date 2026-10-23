import { MemoryRouter } from 'react-router'
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '../test/render'
import { PermissionProvider } from '../auth/permissions'
import { DistributionDevices } from './DistributionDevices'
import type { Node } from '../types/catalog'
import type { DistributionDevice } from '../types/distribution'
import { jsonResponse } from '../test/fixtures'

const mockNode1: Node = { id: 1, name: 'Nodo Central', active: true, created_at: '' }
const mockNode2: Node = { id: 2, name: 'Nodo Norte', active: true, created_at: '' }
const mockNodes = [mockNode1, mockNode2]

const mockDevice1: DistributionDevice = {
  id: 10,
  node_id: 1,
  name: 'Switch-Core-01',
  description: 'Switch principal de distribución',
  active: true,
  port_count: 24,
  circuit_count: 5,
  created_at: '',
}

const mockDevice2: DistributionDevice = {
  id: 11,
  node_id: 2,
  name: 'OLT-Huawei-Norte',
  description: null,
  active: false,
  port_count: 16,
  circuit_count: 0,
  created_at: '',
}

const mockDeviceFree: DistributionDevice = {
  id: 12,
  node_id: 1,
  name: 'Switch-Vacio-01',
  description: 'Equipo de reemplazo',
  active: true,
  port_count: 0,
  circuit_count: 0,
  created_at: '',
}

const allPermissions = [
  'distribution_devices.view',
  'distribution_devices.lookup',
  'distribution_devices.create',
  'distribution_devices.edit',
  'distribution_devices.move',
  'distribution_devices.set_active',
  'distribution_devices.delete',
  'circuits.view',
]

const operatorPermissions = [
  'distribution_devices.view',
  'distribution_devices.lookup',
  'distribution_devices.create',
  'distribution_devices.edit',
  'circuits.view',
]

const auditorPermissions = [
  'distribution_devices.view',
  'distribution_devices.lookup',
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

function setupFetchMock(
  devices: DistributionDevice[] = [mockDevice1, mockDevice2, mockDeviceFree],
  nodes: Node[] = mockNodes,
  extraHandler?: (url: URL, init?: RequestInit) => Response | undefined,
) {
  const mock = vi.fn((input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = new URL(typeof input === 'string' ? input : input.toString(), 'http://localhost')
    if (extraHandler) {
      const res = extraHandler(url, init)
      if (res) return Promise.resolve(res)
    }

    if (url.pathname === '/api/nodes') {
      return Promise.resolve(jsonResponse(nodes))
    }

    if (url.pathname === '/api/distribution-devices' && (!init?.method || init.method === 'GET')) {
      let filtered = [...devices]
      const search = url.searchParams.get('search')
      if (search) {
        filtered = filtered.filter(
          (d) =>
            d.name.toLowerCase().includes(search.toLowerCase()) ||
            (d.description && d.description.toLowerCase().includes(search.toLowerCase())),
        )
      }
      const nodeId = url.searchParams.get('node_id')
      if (nodeId) {
        filtered = filtered.filter((d) => d.node_id === Number(nodeId))
      }
      const active = url.searchParams.get('active')
      if (active === 'true') filtered = filtered.filter((d) => d.active)
      if (active === 'false') filtered = filtered.filter((d) => !d.active)

      const offset = Number(url.searchParams.get('offset') ?? 0)
      const limit = Number(url.searchParams.get('limit') ?? 50)
      return Promise.resolve(jsonResponse(filtered.slice(offset, offset + limit)))
    }

    if (url.pathname === '/api/distribution-devices' && init?.method === 'POST') {
      const body = JSON.parse(String(init.body))
      if (body.name === 'Duplicado') {
        return Promise.resolve(
          jsonResponse(
            { detail: 'Ya existe un nombre equivalente dentro del mismo nodo o equipo.' },
            409,
          ),
        )
      }
      const created: DistributionDevice = {
        id: 99,
        node_id: body.node_id,
        name: body.name,
        description: body.description ?? null,
        active: true,
        port_count: 0,
        circuit_count: 0,
        created_at: new Date().toISOString(),
      }
      return Promise.resolve(jsonResponse(created, 201))
    }

    if (url.pathname.match(/\/api\/distribution-devices\/\d+$/) && init?.method === 'PATCH') {
      const body = JSON.parse(String(init.body))
      const id = Number(url.pathname.split('/').pop())
      const found = devices.find((d) => d.id === id) ?? mockDevice1
      return Promise.resolve(jsonResponse({ ...found, ...body }))
    }

    if (url.pathname.endsWith('/move') && init?.method === 'POST') {
      const body = JSON.parse(String(init.body))
      const id = Number(url.pathname.split('/')[3])
      const found = devices.find((d) => d.id === id) ?? mockDevice1
      if (found.circuit_count > 0) {
        return Promise.resolve(
          jsonResponse(
            { detail: 'El recurso tiene circuitos asociados, incluidos los inactivos.' },
            409,
          ),
        )
      }
      return Promise.resolve(jsonResponse({ ...found, node_id: body.node_id }))
    }

    if (url.pathname.endsWith('/status') && init?.method === 'PATCH') {
      const body = JSON.parse(String(init.body))
      const id = Number(url.pathname.split('/')[3])
      const found = devices.find((d) => d.id === id) ?? mockDevice1
      return Promise.resolve(jsonResponse({ ...found, active: body.active }))
    }

    if (url.pathname.match(/\/api\/distribution-devices\/\d+$/) && init?.method === 'DELETE') {
      return Promise.resolve(new Response(null, { status: 204 }))
    }

    return Promise.resolve(jsonResponse([]))
  })

  vi.stubGlobal('fetch', mock)
  return mock
}

function renderComponent(permissions = allPermissions) {
  return render(
    <MemoryRouter initialEntries={['/distribution-devices']}>
      <PermissionProvider permissions={permissions}>
        <DistributionDevices />
      </PermissionProvider>
    </MemoryRouter>,
  )
}

describe('DistributionDevices — Listado y gestión', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('renderiza el listado de equipos con nodo, puertos, circuitos y estado', async () => {
    setupFetchMock()
    renderComponent()

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Equipos de distribución' })).toBeInTheDocument()
    })

    expect(await screen.findByText('Switch-Core-01')).toBeInTheDocument()
    expect(screen.getByText('OLT-Huawei-Norte')).toBeInTheDocument()
    expect(screen.getByText('Switch-Vacio-01')).toBeInTheDocument()

    expect(screen.getAllByText('Nodo Central').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Nodo Norte').length).toBeGreaterThanOrEqual(1)

    // Check counts
    expect(screen.getByText('24')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()

    // Status badges
    expect(screen.getAllByText('Activo').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('Inactivo')).toBeInTheDocument()
  })

  it('filtra equipos por búsqueda de texto y actualiza la lista', async () => {
    setupFetchMock()
    renderComponent()

    await waitFor(() => {
      expect(screen.getByText('Switch-Core-01')).toBeInTheDocument()
    })

    const searchInput = screen.getByLabelText(/Buscar por nombre o descripción/i)
    fireEvent.change(searchInput, { target: { value: 'Huawei' } })

    await waitFor(() => {
      expect(screen.getByText('OLT-Huawei-Norte')).toBeInTheDocument()
      expect(screen.queryByText('Switch-Core-01')).not.toBeInTheDocument()
    })
  })

  it('filtra equipos por estado administrativo activo/inactivo', async () => {
    setupFetchMock()
    renderComponent()

    await waitFor(() => {
      expect(screen.getByText('Switch-Core-01')).toBeInTheDocument()
    })

    const statusSelect = screen.getByLabelText(/Estado administrativo/i)
    fireEvent.change(statusSelect, { target: { value: 'false' } })

    await waitFor(() => {
      expect(screen.getByText('OLT-Huawei-Norte')).toBeInTheDocument()
      expect(screen.queryByText('Switch-Core-01')).not.toBeInTheDocument()
    })
  })

  it('permite a un superadministrador ver acciones de crear, editar, trasladar, cambiar estado y eliminar', async () => {
    setupFetchMock()
    renderComponent(allPermissions)

    await waitFor(() => {
      expect(screen.getByText('Switch-Core-01')).toBeInTheDocument()
    })

    expect(screen.getByRole('button', { name: /Nuevo equipo/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Editar equipo Switch-Core-01' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Trasladar equipo Switch-Core-01' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Desactivar equipo Switch-Core-01' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Eliminar equipo Switch-Core-01' })).toBeInTheDocument()
  })

  it('limita a un operador a crear y editar sin mostrar traslado, estado ni eliminación', async () => {
    setupFetchMock()
    renderComponent(operatorPermissions)

    await waitFor(() => {
      expect(screen.getByText('Switch-Core-01')).toBeInTheDocument()
    })

    expect(screen.getByRole('button', { name: /Nuevo equipo/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Editar equipo Switch-Core-01' })).toBeInTheDocument()

    // Protected administrative actions must NOT be present
    expect(screen.queryByRole('button', { name: 'Trasladar equipo Switch-Core-01' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Desactivar equipo Switch-Core-01' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Eliminar equipo Switch-Core-01' })).not.toBeInTheDocument()
  })

  it('restringe a un auditor a solo lectura sin mostrar acciones de modificación', async () => {
    setupFetchMock()
    renderComponent(auditorPermissions)

    await waitFor(() => {
      expect(screen.getByText('Switch-Core-01')).toBeInTheDocument()
    })

    expect(screen.queryByRole('button', { name: /Nuevo equipo/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Editar equipo Switch-Core-01' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Trasladar equipo Switch-Core-01' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Desactivar equipo Switch-Core-01' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Eliminar equipo Switch-Core-01' })).not.toBeInTheDocument()

    // Consultation link remains available
    expect(screen.getByRole('link', { name: 'Ver detalle del equipo Switch-Core-01' })).toBeInTheDocument()
  })

  it('abre el modal de nuevo equipo y lo crea exitosamente', async () => {
    const fetchMock = setupFetchMock()
    renderComponent(allPermissions)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Nuevo equipo/i })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Nuevo equipo/i }))

    expect(screen.getByRole('heading', { name: 'Nuevo equipo de distribución' })).toBeInTheDocument()

    const nameInput = screen.getByLabelText(/^Nombre/i)
    fireEvent.change(nameInput, { target: { value: 'Switch-Nuevo-01' } })

    // Open node combobox and select Nodo Central
    const nodeCombo = screen.getByRole('combobox', { name: 'Nodo' })
    fireEvent.click(nodeCombo)
    fireEvent.click(screen.getByRole('option', { name: 'Nodo Central' }))

    const submitBtn = screen.getByRole('button', { name: 'Crear equipo' })
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(screen.getByText(/Se creó el equipo «Switch-Nuevo-01» con éxito/i)).toBeInTheDocument()
    })

    const postCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        url.toString().endsWith('/api/distribution-devices') && init?.method === 'POST',
    )
    expect(postCall).toBeDefined()
    expect(JSON.parse(String(postCall![1]?.body))).toEqual({
      node_id: 1,
      name: 'Switch-Nuevo-01',
      description: null,
    })
  })

  it('maneja errores 409 de nombre duplicado al crear un equipo', async () => {
    setupFetchMock()
    renderComponent(allPermissions)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Nuevo equipo/i })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /Nuevo equipo/i }))

    const nameInput = screen.getByLabelText(/^Nombre/i)
    fireEvent.change(nameInput, { target: { value: 'Duplicado' } })

    const nodeCombo = screen.getByRole('combobox', { name: 'Nodo' })
    fireEvent.click(nodeCombo)
    fireEvent.click(screen.getByRole('option', { name: 'Nodo Central' }))

    fireEvent.click(screen.getByRole('button', { name: 'Crear equipo' }))

    await waitFor(() => {
      expect(
        screen.getByText(/Ya existe un nombre equivalente dentro del mismo nodo o equipo/i),
      ).toBeInTheDocument()
    })
  })

  it('edita nombre y descripción de un equipo existente', async () => {
    const fetchMock = setupFetchMock()
    renderComponent(allPermissions)

    await waitFor(() => {
      expect(screen.getByText('Switch-Core-01')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Editar equipo Switch-Core-01' }))

    expect(screen.getByRole('heading', { name: 'Editar equipo de distribución' })).toBeInTheDocument()

    const nameInput = screen.getByLabelText(/^Nombre/i)
    fireEvent.change(nameInput, { target: { value: 'Switch-Core-01-Renombrado' } })

    fireEvent.click(screen.getByRole('button', { name: 'Actualizar equipo' }))

    await waitFor(() => {
      expect(
        screen.getByText(/Se actualizó el equipo «Switch-Core-01-Renombrado»/i),
      ).toBeInTheDocument()
    })

    const patchCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        url.toString().includes('/api/distribution-devices/10') && init?.method === 'PATCH',
    )
    expect(patchCall).toBeDefined()
    expect(JSON.parse(String(patchCall![1]?.body))).toEqual({
      name: 'Switch-Core-01-Renombrado',
      description: 'Switch principal de distribución',
    })
  })

  it('bloquea el traslado de un equipo que tiene circuitos asociados', async () => {
    setupFetchMock()
    renderComponent(allPermissions)

    await waitFor(() => {
      expect(screen.getByText('Switch-Core-01')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Trasladar equipo Switch-Core-01' }))

    expect(screen.getByRole('heading', { name: 'Trasladar equipo de nodo' })).toBeInTheDocument()

    // Must show blocking message because it has 5 circuits
    expect(
      screen.getByText(/Bloqueado: El equipo tiene 5 circuitos asociados/i),
    ).toBeInTheDocument()

    const submitBtn = screen.getByRole('button', { name: 'Confirmar traslado' })
    expect(submitBtn).toBeDisabled()
  })

  it('traslada de nodo un equipo que no tiene circuitos asociados', async () => {
    const fetchMock = setupFetchMock()
    renderComponent(allPermissions)

    await waitFor(() => {
      expect(screen.getByText('Switch-Vacio-01')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Trasladar equipo Switch-Vacio-01' }))

    expect(screen.getByRole('heading', { name: 'Trasladar equipo de nodo' })).toBeInTheDocument()
    expect(screen.queryByText(/Bloqueado:/i)).not.toBeInTheDocument()

    const nodeCombo = screen.getByRole('combobox', { name: 'Nodo destino' })
    fireEvent.click(nodeCombo)
    fireEvent.click(screen.getByRole('option', { name: 'Nodo Norte' }))

    const submitBtn = screen.getByRole('button', { name: 'Confirmar traslado' })
    expect(submitBtn).toBeEnabled()
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(screen.getByText(/Se trasladó el equipo «Switch-Vacio-01» al nuevo nodo/i)).toBeInTheDocument()
    })

    const moveCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        url.toString().endsWith('/api/distribution-devices/12/move') && init?.method === 'POST',
    )
    expect(moveCall).toBeDefined()
    expect(JSON.parse(String(moveCall![1]?.body))).toEqual({ node_id: 2 })
  })

  it('bloquea la desactivación de un equipo con circuitos asociados', async () => {
    setupFetchMock()
    renderComponent(allPermissions)

    await waitFor(() => {
      expect(screen.getByText('Switch-Core-01')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Desactivar equipo Switch-Core-01' }))

    expect(screen.getByRole('heading', { name: 'Desactivar equipo' })).toBeInTheDocument()
    expect(
      screen.getByText(/El equipo tiene 5 circuitos asociados.*No se puede desactivar/i),
    ).toBeInTheDocument()

    // Cannot confirm deactivation
    expect(screen.queryByRole('button', { name: 'Confirmar desactivar' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Entendido' })).toBeInTheDocument()
  })

  it('desactiva un equipo sin circuitos asociados tras confirmación', async () => {
    const fetchMock = setupFetchMock()
    renderComponent(allPermissions)

    await waitFor(() => {
      expect(screen.getByText('Switch-Vacio-01')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Desactivar equipo Switch-Vacio-01' }))

    expect(screen.getByRole('heading', { name: 'Desactivar equipo' })).toBeInTheDocument()
    const confirmBtn = screen.getByRole('button', { name: 'Confirmar desactivar' })
    fireEvent.click(confirmBtn)

    await waitFor(() => {
      expect(screen.getByText(/Se desactivó el equipo «Switch-Vacio-01»/i)).toBeInTheDocument()
    })

    const statusCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        url.toString().endsWith('/api/distribution-devices/12/status') && init?.method === 'PATCH',
    )
    expect(statusCall).toBeDefined()
    expect(JSON.parse(String(statusCall![1]?.body))).toEqual({ active: false })
  })

  it('bloquea la eliminación de un equipo con puertos registrados', async () => {
    setupFetchMock()
    renderComponent(allPermissions)

    await waitFor(() => {
      expect(screen.getByText('Switch-Core-01')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Eliminar equipo Switch-Core-01' }))

    expect(screen.getByRole('heading', { name: 'Eliminar equipo de distribución' })).toBeInTheDocument()
    expect(
      screen.getByText(/El equipo conserva 24 puertos registrados/i),
    ).toBeInTheDocument()

    expect(screen.queryByRole('button', { name: 'Eliminar equipo' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Entendido' })).toBeInTheDocument()
  })

  it('elimina un equipo sin puertos ni circuitos tras confirmación', async () => {
    const fetchMock = setupFetchMock()
    renderComponent(allPermissions)

    await waitFor(() => {
      expect(screen.getByText('Switch-Vacio-01')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Eliminar equipo Switch-Vacio-01' }))

    expect(screen.getByRole('heading', { name: 'Eliminar equipo de distribución' })).toBeInTheDocument()
    const deleteBtn = screen.getByRole('button', { name: 'Eliminar equipo' })
    fireEvent.click(deleteBtn)

    await waitFor(() => {
      expect(screen.getByText(/Se eliminó el equipo «Switch-Vacio-01» con éxito/i)).toBeInTheDocument()
    })

    const deleteCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        url.toString().endsWith('/api/distribution-devices/12') && init?.method === 'DELETE',
    )
    expect(deleteCall).toBeDefined()
  })
})


it.each([
  { count: 0, text: '0' },
  { count: 19, text: '19' },
  { count: undefined, text: '—' },
])('muestra puertos sin circuitos y distingue dato ausente ($count)', async ({ count, text }) => {
  setupFetchMock([{ ...mockDevice1, unassigned_port_count: count }])
  renderComponent()
  const row = (await screen.findByText(mockDevice1.name)).closest('tr')!
  expect(within(screen.getByRole('table')).getAllByRole('columnheader').map(cell => cell.textContent?.trim())).toEqual([
    'Equipo', 'Nodo', 'Descripción', 'Puertos', 'Puertos sin circuitos', 'Circuitos', 'Estado', 'Acciones',
  ])
  const cells = within(row).getAllByRole('cell')
  expect(cells[4]).toHaveTextContent(text)
  expect(cells[4]).toHaveClass('text-emerald-400')
  expect(cells[3]).toHaveTextContent('24')
  expect(cells[3]).toHaveClass('text-blue-400')
  expect(cells[5]).toHaveTextContent('5')
  expect(cells[5]).toHaveClass('text-purple-300')
  if (count === undefined) expect(within(row).getByLabelText('Dato no disponible')).toBeInTheDocument()
})
