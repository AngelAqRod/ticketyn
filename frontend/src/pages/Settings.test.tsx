import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { Settings } from './Settings'
import { jsonResponse } from '../test/fixtures'
const config = { id: 1, prefix: 'TEST', separator: '-', next_number: 27, padding: 3 }
function setup(options: { loadError?: boolean; pending?: boolean; saveError?: boolean; pendingSave?: boolean } = {}) {
  const mock = vi.fn((path: string, request?: RequestInit) => {
    if (request?.method === 'PATCH') {
      if (options.pendingSave) return new Promise<Response>(() => {})
      return Promise.resolve(options.saveError ? jsonResponse({ detail: 'El número ya fue utilizado' }, 409) : jsonResponse({ ...config, ...JSON.parse(String(request.body)) }))
    }
    if (options.pending) return new Promise<Response>(() => {})
    return Promise.resolve(options.loadError ? jsonResponse({ detail: 'Configuración no disponible' }, 503) : jsonResponse(config))
  })
  vi.stubGlobal('fetch', mock)
  render(<MemoryRouter initialEntries={['/settings']}><Settings /></MemoryRouter>)
  return mock
}
async function loaded() { await waitFor(() => expect(screen.getByLabelText('Prefijo')).toHaveValue('TEST')) }
describe('configuración de numeración', () => {
  it('carga GET inicial y valores existentes', async () => {
    const mock = setup(); await loaded()
    expect(mock).toHaveBeenCalledWith('/api/settings/ticket-number', expect.any(Object))
    expect(screen.getByLabelText('Próximo número')).toHaveValue(27)
    expect(screen.getByLabelText('Separador')).toHaveValue('-')
    expect(screen.getByLabelText('Longitud / Padding')).toHaveValue(3)
    expect(screen.getByLabelText('Próxima referencia')).toHaveTextContent('TEST-027')
  })
  it('actualiza preview sin POST/PATCH ni consumo de número', async () => {
    const mock = setup(); await loaded()
    fireEvent.change(screen.getByLabelText('Longitud / Padding'), { target: { value: '4' } })
    expect(screen.getByLabelText('Próxima referencia')).toHaveTextContent('TEST-0027')
    fireEvent.change(screen.getByLabelText('Separador'), { target: { value: '----' } })
    expect(screen.getByLabelText('Próxima referencia')).toHaveTextContent('TEST----0027')
    expect(mock).toHaveBeenCalledTimes(1)
    expect(screen.getByText('Los cambios afectan únicamente a los tickets creados posteriormente.')).toBeInTheDocument()
  })
  it('permite prefijo/separador vacíos y padding cero', async () => {
    const mock = setup(); await loaded()
    for (const label of ['Prefijo', 'Separador']) fireEvent.change(screen.getByLabelText(label), { target: { value: '' } })
    fireEvent.change(screen.getByLabelText('Longitud / Padding'), { target: { value: '0' } })
    expect(screen.getByLabelText('Próxima referencia')).toHaveTextContent('27')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    await screen.findByText('Configuración guardada correctamente.')
    expect(JSON.parse(String(mock.mock.calls.find(([, opts]) => opts?.method === 'PATCH')![1]?.body))).toEqual({ prefix: '', separator: '', padding: 0 })
  })
  it('PATCH envía solo los campos modificados, sin sobrescribir el contador', async () => {
    const mock = setup(); await loaded()
    fireEvent.change(screen.getByLabelText('Prefijo'), { target: { value: 'NEW' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    await screen.findByText('Configuración guardada correctamente.')
    const request = mock.mock.calls.find(([, opts]) => opts?.method === 'PATCH')![1]!
    expect(JSON.parse(String(request.body))).toEqual({ prefix: 'NEW' })
    expect(screen.getByLabelText('Próxima referencia')).toHaveTextContent('NEW-027')
  })
  it('muestra loading', () => { setup({ pending: true }); expect(screen.getByRole('status')).toHaveTextContent('Cargando configuración...') })
  it('muestra errores al cargar y permite reintentar', async () => { setup({ loadError: true }); expect(await screen.findByRole('alert')).toHaveTextContent('Configuración no disponible'); expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument() })
  it('muestra saving y evita doble envío', async () => {
    const mock = setup({ pendingSave: true }); await loaded()
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    expect(screen.getByRole('button', { name: 'Guardando...' })).toBeDisabled()
    expect(screen.getByLabelText('Prefijo')).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Guardando...' }))
    expect(mock.mock.calls.filter(([, opts]) => opts?.method === 'PATCH')).toHaveLength(1)
  })
  it('conserva el formulario ante conflicto 409', async () => {
    setup({ saveError: true }); await loaded()
    fireEvent.change(screen.getByLabelText('Próximo número'), { target: { value: '1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('El número ya fue utilizado')
    expect(screen.getByLabelText('Próximo número')).toHaveValue(1)
  })
  it.each(['21', '-1', '2147483647'])('protege preview y envío con padding inválido %s', async (value) => {
    const mock = setup(); await loaded()
    fireEvent.change(screen.getByLabelText('Longitud / Padding'), { target: { value } })
    expect(screen.getByLabelText('Próxima referencia')).toHaveTextContent('—')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    expect(screen.getByRole('alert')).toHaveTextContent('entre 0 y 20')
    expect(mock.mock.calls.filter(([, opts]) => opts?.method === 'PATCH')).toHaveLength(0)
  })
  it('permite padding 20 sin recortar el número', async () => {
    setup(); await loaded()
    fireEvent.change(screen.getByLabelText('Longitud / Padding'), { target: { value: '20' } })
    expect(screen.getByLabelText('Próxima referencia')).toHaveTextContent('TEST-00000000000000000027')
  })
})
