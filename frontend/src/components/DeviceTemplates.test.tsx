import { MemoryRouter } from 'react-router'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '../test/render'
import { useState } from 'react'
import { PermissionProvider } from '../auth/permissions'
import { DeviceTemplateAdmin } from './DeviceTemplateAdmin'
import { DeviceTemplateChoice, manualTemplate, templateReady, type TemplateChoice } from './DeviceTemplateChoice'
import { DeviceFormModal } from './DistributionModals'
import { QuickDistributionCreate } from './QuickDistributionCreate'
import * as templates from '../api/deviceTemplates'
import * as ports from '../api/portNomenclatures'
import * as distribution from '../api/distribution'
import * as quick from '../api'
import type { DeviceTemplate } from '../api/deviceTemplates'

vi.mock('../api/deviceTemplates', async original => ({ ...await original<typeof import('../api/deviceTemplates')>(),
  listDeviceTemplates: vi.fn(), getDeviceTemplate: vi.fn(), previewDeviceTemplate: vi.fn(), saveDeviceTemplate: vi.fn() }))
vi.mock('../api/portNomenclatures', async original => ({ ...await original<typeof import('../api/portNomenclatures')>(), listPortNomenclatures: vi.fn() }))
vi.mock('../api/distribution', async original => ({ ...await original<typeof import('../api/distribution')>(),
  createDistributionDevice: vi.fn(), listDistributionDevices: vi.fn() }))

vi.mock('../api', async original => ({ ...await original<typeof import('../api')>(), createDistributionDevice: vi.fn(), listDistributionDevices: vi.fn() }))

const template: DeviceTemplate = { id: 1, name: 'Modelo NOC', manufacturer: null, description: null, active: true, created_at: '',
  groups: [{ nomenclature_id: 1, numbering_format: 'N', positions: [], start: 0, end: 2, nomenclature_name: 'Óptica', prefix: 'SFP+', names: ['SFP+0', 'SFP+1', 'SFP+2'], warning: null }],
  total_ports: 3, usable: true, preview_token: 'a'.repeat(64) }
const permissions = ['view', 'create', 'edit'].map(action => 'catalogs.distribution_device_templates.' + action)
const node = { id: 1, name: 'Nodo A', active: true, created_at: '' }
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open') }
})
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(templates.listDeviceTemplates).mockResolvedValue([template])
  vi.mocked(templates.getDeviceTemplate).mockResolvedValue(template)
  vi.mocked(templates.previewDeviceTemplate).mockResolvedValue(template)
  vi.mocked(templates.saveDeviceTemplate).mockResolvedValue(template)
  vi.mocked(ports.listPortNomenclatures).mockResolvedValue([{ id: 1, name: 'Óptica', prefix: 'SFP+', formats: ['N', 'X/Y/Z'], active: true, created_at: '' }])
  vi.mocked(quick.listDistributionDevices).mockResolvedValue([])
  vi.mocked(distribution.createDistributionDevice).mockResolvedValue({ id: 2, node_id: 1, name: 'Equipo nuevo', active: true, created_at: '', description: null, port_count: 3, circuit_count: 0 })
  vi.mocked(quick.createDistributionDevice).mockImplementation(distribution.createDistributionDevice)
})
async function chooseTemplate() {
  fireEvent.click(screen.getByLabelText('Crear desde plantilla'))
  await waitFor(() => expect(templates.listDeviceTemplates).toHaveBeenCalled())
  fireEvent.click(screen.getByRole('combobox', { name: 'Plantilla' }))
  fireEvent.click(await screen.findByRole('option', { name: 'Modelo NOC · 3 puertos' }))
  await screen.findByText('1 grupos · 3 puertos')
}
function Choice() {
  const [value, setValue] = useState<TemplateChoice>(manualTemplate)
  return <><DeviceTemplateChoice value={value} onChange={setValue} /><button disabled={!templateReady(value)}>Confirmar</button></>
}

describe('plantillas compartidas', () => {
  it('mantiene manual sin consultas; requiere comprobación al seleccionar plantilla', async () => {
    render(<Choice />)
    expect(screen.getByRole('button', { name: 'Confirmar' })).toBeEnabled()
    expect(templates.listDeviceTemplates).not.toHaveBeenCalled()
    await chooseTemplate()
    expect(screen.getByRole('button', { name: 'Confirmar' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Agregar grupo' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('Grupo 1:', { exact: false }))
    expect(screen.getByText('SFP+0, SFP+1, SFP+2')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Crear manualmente'))
    expect(screen.queryByRole('combobox', { name: 'Plantilla' })).not.toBeInTheDocument()
  })
  it('bloquea aplicación con nomenclatura inactiva', async () => {
    vi.mocked(templates.getDeviceTemplate).mockResolvedValue({ ...template, usable: false })
    render(<Choice />)
    await chooseTemplate()
    expect(screen.getByRole('button', { name: 'Confirmar' })).toBeDisabled()
    expect(screen.getByText(/Regulariza sus nomenclaturas/)).toBeInTheDocument()
  })
  it('muestra errores de red y permite volver a comprobar', async () => {
    vi.mocked(templates.getDeviceTemplate).mockRejectedValueOnce(new Error('Red interrumpida'))
    render(<Choice />)
    fireEvent.click(screen.getByLabelText('Crear desde plantilla'))
    fireEvent.click(await screen.findByRole('combobox', { name: 'Plantilla' }))
    fireEvent.click(await screen.findByRole('option', { name: 'Modelo NOC · 3 puertos' }))
    await screen.findByText('Red interrumpida')
    expect(screen.getByRole('button', { name: 'Confirmar' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Volver a comprobar' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Confirmar' })).toBeEnabled())
  })
  it('crea equipo desde plantilla conservando nombre, descripción y nodo', async () => {
    const onSaved = vi.fn()
    render(<DeviceFormModal isOpen nodes={[node]} onSaved={onSaved} onClose={vi.fn()} />)
    fireEvent.change(screen.getByRole('textbox', { name: /^Nombre$/ }), { target: { value: 'Equipo nuevo' } })
    fireEvent.change(screen.getByLabelText('Descripción (opcional)'), { target: { value: 'Rack operativo' } })
    fireEvent.click(screen.getByRole('combobox', { name: /Nodo/ }))
    fireEvent.click(await screen.findByRole('option', { name: 'Nodo A' }))
    await chooseTemplate()
    const save = screen.getByRole('button', { name: /Crear equipo/ })
    fireEvent.click(save); fireEvent.click(save)
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
    expect(distribution.createDistributionDevice).toHaveBeenCalledExactlyOnceWith({ node_id: 1, name: 'Equipo nuevo', description: 'Rack operativo', template_id: 1, template_token: 'a'.repeat(64) })
  })
  it('reutiliza la modalidad en creación rápida sin guardar el circuito', async () => {
    const onCreated = vi.fn()
    render(<PermissionProvider permissions={['distribution_devices.create', 'distribution_devices.view']}><QuickDistributionCreate kind="device" parentId={1} parentName="Nodo A" onCreated={onCreated} onCancel={vi.fn()} /></PermissionProvider>)
    await waitFor(() => expect(screen.getByRole('textbox', { name: /^Nombre$/ })).toBeEnabled())
    fireEvent.change(screen.getByRole('textbox', { name: /^Nombre$/ }), { target: { value: 'Equipo rápido' } })
    await chooseTemplate()
    fireEvent.click(screen.getByRole('button', { name: 'Crear' }))
    await waitFor(() => expect(onCreated).toHaveBeenCalledOnce())
    expect(quick.createDistributionDevice).toHaveBeenCalledWith(expect.objectContaining({ node_id: 1, name: 'Equipo rápido', template_id: 1 }), expect.any(AbortSignal))
  })
})

describe('administración de plantillas', () => {
  it('permite editar grupos y guarda únicamente tras la comprobación backend', async () => {
    render(<PermissionProvider permissions={permissions}><MemoryRouter><DeviceTemplateAdmin /></MemoryRouter></PermissionProvider>)
    await screen.findByText('Modelo NOC')
    fireEvent.click(screen.getByRole('button', { name: 'Editar Modelo NOC' }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Nombre / modelo' }), { target: { value: 'Modelo ampliado' } })
    fireEvent.click(screen.getByRole('button', { name: 'Agregar grupo' }))
    expect(screen.getAllByText(/Grupo [12]$/, { selector: 'legend' })).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'Quitar grupo 2' }))
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Número final' }), { target: { value: '11' } })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Guardar plantilla' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Guardar plantilla' }))
    await waitFor(() => expect(templates.saveDeviceTemplate).toHaveBeenCalledWith(expect.objectContaining({ name: 'Modelo ampliado', groups: [expect.objectContaining({ end: 11 })], preview_token: template.preview_token }), 1))
    await screen.findByText(/Los equipos existentes permanecen intactos/)
  })
  it('muestra conflicto de grupos y bloquea guardar', async () => {
    vi.mocked(templates.previewDeviceTemplate).mockRejectedValue(new Error('Nombre duplicado SFP+1: grupos 1 y 2'))
    render(<PermissionProvider permissions={permissions}><MemoryRouter><DeviceTemplateAdmin /></MemoryRouter></PermissionProvider>)
    fireEvent.click(await screen.findByRole('button', { name: 'Editar Modelo NOC' }))
    await screen.findByText('Nombre duplicado SFP+1: grupos 1 y 2')
    expect(screen.getByRole('button', { name: 'Guardar plantilla' })).toBeDisabled()
  })
  it('respeta lectura sin acciones administrativas y muestra grupos', async () => {
    render(<PermissionProvider permissions={[permissions[0]]}><MemoryRouter><DeviceTemplateAdmin /></MemoryRouter></PermissionProvider>)
    await screen.findByText('Modelo NOC')
    expect(screen.queryByRole('button', { name: 'Nueva plantilla' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Editar Modelo NOC' })).not.toBeInTheDocument()
    expect(within(screen.getByRole('table')).getByText('Consultar')).toBeInTheDocument()
  })
})

it('descarta una respuesta tardía al volver a creación manual', async () => {
  let resolve!: (item: DeviceTemplate) => void
  vi.mocked(templates.getDeviceTemplate).mockReturnValueOnce(new Promise(done => { resolve = done }))
  render(<Choice />)
  fireEvent.click(screen.getByLabelText('Crear desde plantilla'))
  fireEvent.click(await screen.findByRole('combobox', { name: 'Plantilla' }))
  fireEvent.click(await screen.findByRole('option', { name: 'Modelo NOC · 3 puertos' }))
  await waitFor(() => expect(templates.getDeviceTemplate).toHaveBeenCalled())
  fireEvent.click(screen.getByLabelText('Crear manualmente'))
  const { act } = await import('../test/render')
  await act(async () => resolve(template))
  expect(screen.getByLabelText('Crear manualmente')).toBeChecked()
  expect(screen.queryByText('1 grupos · 3 puertos')).not.toBeInTheDocument()
})

it('impide guardar cuando los grupos superan 256 puertos en total', async () => {
  render(<PermissionProvider permissions={permissions}><MemoryRouter><DeviceTemplateAdmin /></MemoryRouter></PermissionProvider>)
  fireEvent.click(await screen.findByRole('button', { name: 'Editar Modelo NOC' }))
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Número final' }), { target: { value: '256' } })
  expect(screen.getByRole('button', { name: 'Guardar plantilla' })).toBeDisabled()
  await new Promise(resolve => setTimeout(resolve, 300))
  expect(templates.previewDeviceTemplate).not.toHaveBeenCalled()
})
