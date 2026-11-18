import { render as renderRaw } from '@testing-library/react'
import { fireEvent, render as renderReact, screen, within } from '../test/render'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PermissionContext } from '../auth/permissions'
import { Catalogs } from './Catalogs'

vi.mock('../components/CatalogAdmin', () => ({ CatalogAdmin: ({ kind }: { kind: string }) => <div data-testid="catalog-content">{kind}</div> }))

vi.mock('../components/PortNomenclatureAdmin', () => ({ PortNomenclatureAdmin: () => <div data-testid="catalog-content">port-nomenclatures</div> }))

vi.mock('../components/DeviceTemplateAdmin', () => ({ DeviceTemplateAdmin: () => <div data-testid="catalog-content">distribution-device-templates</div> }))

afterEach(() => vi.restoreAllMocks())

const kinds = ['nodes', 'sectors', 'distribution-device-templates', 'port-nomenclatures', 'cpe-models', 'providers', 'service-types', 'deactivation-reasons', 'incident-types', 'internal-incident-types', 'escalation-reasons', 'change-types', 'change-completion-types', 'admin-request-types', 'departments', 'positions']

describe('navegación de Catálogos', () => {
  it('agrupa las categorías, conserva el orden y cambia solo el catálogo seleccionado', () => {
    renderReact(<Catalogs />)
    const nav = screen.getByRole('navigation', { name: 'Catálogos' })
    expect(within(nav).getAllByRole('group').map(group => group.getAttribute('aria-label'))).toEqual(['Red', 'Servicio', 'Tickets e incidencias', 'Cambios', 'Solicitudes', 'Organización'])
    const buttons = within(nav).getAllByRole('button')
    expect(buttons).toHaveLength(16)
    expect(buttons[1]).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('catalog-content')).toHaveTextContent('sectors')
    buttons.forEach((button, index) => {
      fireEvent.click(button)
      expect(buttons.filter(item => item.getAttribute('aria-pressed') === 'true')).toEqual([button])
      expect(screen.getByTestId('catalog-content')).toHaveTextContent(kinds[index])
    })
  })
  it('filtra categorías sin distinguir mayúsculas ni acentos', () => {
    renderReact(<Catalogs />)
    const nav = screen.getByRole('navigation', { name: 'Catálogos' })
    fireEvent.change(within(nav).getByRole('searchbox', { name: 'Filtrar categorías' }), { target: { value: 'FINALIZACION' } })
    expect(within(nav).getAllByRole('button').map(button => button.textContent)).toEqual(['Tipos de finalización de cambios'])
    fireEvent.change(within(nav).getByRole('searchbox'), { target: { value: 'zzz' } })
    expect(within(nav).getByRole('status')).toHaveTextContent('Sin coincidencias.')
  })
  it('oculta categorías sin permiso y elige la primera disponible', () => {
    const can = (code: string) => code === 'catalogs.departments.view' || code === 'catalogs.positions.view'
    renderRaw(<PermissionContext.Provider value={{ permissions: [], can, any: () => false }}><Catalogs /></PermissionContext.Provider>)
    const nav = screen.getByRole('navigation', { name: 'Catálogos' })
    expect(within(nav).getAllByRole('button').map(button => button.textContent)).toEqual(['Departamentos', 'Puestos'])
    expect(screen.getByTestId('catalog-content')).toHaveTextContent('departments')
  })
})
