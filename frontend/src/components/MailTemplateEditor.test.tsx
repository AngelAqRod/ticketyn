import { fireEvent, render, screen, waitFor } from '../test/render'
import { describe, expect, it, vi } from 'vitest'
import { MailTemplateEditor } from './MailTemplateEditor'
import { jsonResponse } from '../test/fixtures'
import type { MailField, MailTemplate } from '../api/mailNotifications'

const key = 'fms.activation.created'
const fields: MailField[] = [{ id: 'activation.activation_notes', group: 'Activación FMS', label: 'Notas de activación', format: 'multiline', temporality: 'HISTORICAL', source_paths: [], resolver: 'attribute' }, { id: 'customer.name', group: 'Cliente', label: 'Cliente', format: 'text', temporality: 'CURRENT', source_paths: [], resolver: 'attribute' }]
const empty: MailTemplate = { version: 1, subject: [], body: [] }
const htmlPreview = '<!doctype html><html lang="es"><head><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'"></head><body><table><tr><td>Ticketyn</td></tr><tr><td>NOTAS DE ACTIVACIÓN:<br>Primera línea<br>  Segunda línea</td></tr></table></body></html>'
function setup(options: { initial?: MailTemplate; noActivations?: boolean; failPreview?: boolean; failSave?: boolean; pending?: boolean; legacyPreview?: boolean } = {}) {
  let stored = options.initial ?? structuredClone(empty)
  const mock = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.startsWith('/api/activations?')) return jsonResponse(options.noActivations ? [] : [{ id: 1, reference: 'ACT-0000001', circuit: { circuit_code: 'CIR-1' } }])
    if (path.endsWith('/template')) {
      if (init?.method === 'PATCH') {
        if (options.pending) return new Promise<Response>(() => {})
        if (options.failSave) return jsonResponse({ detail: 'Campo no disponible.' }, 422)
        stored = JSON.parse(String(init.body))
      }
      return jsonResponse(stored)
    }
    if (path.endsWith('/preview')) return options.failPreview ? jsonResponse({ detail: 'La activación seleccionada no existe.' }, 404) : jsonResponse({ subject: 'Asunto real ACT-0000001', body: 'NOTAS DE ACTIVACIÓN:\nPrimera línea\n  Segunda línea\nEtiqueta Mixta: Valor mixto', ...(!options.legacyPreview ? { html_body: htmlPreview } : {}) })
    return jsonResponse({ detail: 'Unexpected' }, 404)
  })
  vi.stubGlobal('fetch', mock)
  const view = render(<MailTemplateEditor eventKey={key} fields={fields} />)
  return { mock, view }
}
async function loaded() { await screen.findByRole('button', { name: 'Guardar plantilla' }); await screen.findByLabelText('Activación para vista previa') }
const writes = (mock: ReturnType<typeof setup>['mock'], method = 'PATCH') => mock.mock.calls.filter(([, init]) => init?.method === method)

describe('Editor de plantillas', () => {
  it('inicia vacío, muestra campos amigables y permite ordenar y eliminar elementos', async () => {
    const { mock } = setup(); await loaded()
    expect(screen.getByText('Sin elementos de asunto.')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Agregar texto al asunto'))
    fireEvent.change(screen.getByLabelText('Texto fijo 1'), { target: { value: 'Prefijo | ' } })
    fireEvent.click(screen.getByText('Agregar campo al asunto'))
    fireEvent.change(screen.getByLabelText('Campo de asunto 2'), { target: { value: 'customer.name' } })
    expect(screen.queryByText('customer.name')).not.toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Subir elemento de asunto 2'))
    expect(screen.getByLabelText('Campo de asunto 1')).toHaveValue('customer.name')
    expect(screen.getByLabelText('Texto fijo 2')).toHaveValue('Prefijo | ')
    fireEvent.click(screen.getByLabelText('Bajar elemento de asunto 1'))
    fireEvent.click(screen.getByLabelText('Eliminar elemento de asunto 1'))
    fireEvent.click(screen.getByText('Guardar plantilla'))
    await screen.findByText('Plantilla guardada.')
    expect(JSON.parse(String(writes(mock)[0][1]?.body))).toEqual({ ...empty, subject: [{ type: 'field', field_id: 'customer.name' }] })
  })
  it('configura etiquetas y bloques del cuerpo, guarda y recupera su orden', async () => {
    const { mock, view } = setup(); await loaded()
    fireEvent.click(screen.getByText('Agregar introducción'))
    fireEvent.change(screen.getByLabelText('Introducción 1'), { target: { value: 'Estimados,\nAviso técnico.' } })
    fireEvent.click(screen.getByText('Agregar campo al cuerpo'))
    fireEvent.change(screen.getByLabelText('Campo de cuerpo 2'), { target: { value: 'activation.activation_notes' } })
    expect(screen.getByLabelText('Etiqueta 2')).toHaveDisplayValue('Por defecto')
    fireEvent.change(screen.getByLabelText('Etiqueta 2'), { target: { value: 'CUSTOM' } })
    expect(screen.getByLabelText('Etiqueta 2')).toHaveDisplayValue('Personalizado')
    fireEvent.change(screen.getByLabelText('Etiqueta personalizada 2'), { target: { value: 'Detalles técnicos' } })
    fireEvent.click(screen.getByText('Agregar firma'))
    fireEvent.change(screen.getByLabelText('Firma 3'), { target: { value: 'Saludos, NOC' } })
    fireEvent.click(screen.getByLabelText('Subir elemento de cuerpo 3'))
    fireEvent.click(screen.getByText('Guardar plantilla')); await screen.findByText('Plantilla guardada.')
    const saved = JSON.parse(String(writes(mock)[0][1]?.body))
    expect(saved.body.map((block: { type: string }) => block.type)).toEqual(['introduction', 'signature', 'field'])
    expect(saved.body[2]).toMatchObject({ label_mode: 'CUSTOM', custom_label: 'Detalles técnicos' })
    view.unmount(); render(<MailTemplateEditor eventKey={key} fields={fields} />); await loaded()
    expect(screen.getByLabelText('Firma 2')).toHaveValue('Saludos, NOC')
    expect(screen.getByLabelText('Etiqueta personalizada 3')).toHaveValue('Detalles técnicos')
    fireEvent.change(screen.getByLabelText('Etiqueta 3'), { target: { value: 'DEFAULT' } })
    expect(screen.queryByLabelText('Etiqueta personalizada 3')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('Guardar plantilla')); await screen.findByText('Plantilla guardada.')
    expect(JSON.parse(String(writes(mock)[1][1]?.body)).body[2].custom_label).toBeNull()
  })
  it('genera vista previa con cambios no guardados y la invalida al editar', async () => {
    const { mock } = setup(); await loaded()
    fireEvent.click(screen.getByText('Agregar texto al asunto'))
    fireEvent.change(screen.getByLabelText('Texto fijo 1'), { target: { value: 'Borrador' } })
    fireEvent.change(screen.getByLabelText('Activación para vista previa'), { target: { value: '1' } })
    fireEvent.click(screen.getByText('Generar vista previa'))
    await screen.findByText('Asunto real ACT-0000001')
    const frame = screen.getByTitle('Vista previa HTML del correo')
    expect(frame).toHaveAttribute('srcdoc', htmlPreview)
    expect(frame).toHaveAttribute('sandbox', '')
    expect(frame).toHaveAttribute('referrerpolicy', 'no-referrer')
    expect(screen.getByText(/Primera línea/).textContent).toBe('NOTAS DE ACTIVACIÓN:\nPrimera línea\n  Segunda línea\nEtiqueta Mixta: Valor mixto')
    expect(writes(mock)).toHaveLength(0)
    expect(JSON.parse(String(writes(mock, 'POST')[0][1]?.body))).toEqual({ activation_id: 1, template: { ...empty, subject: [{ type: 'text', text: 'Borrador' }] } })
    fireEvent.change(screen.getByLabelText('Texto fijo 1'), { target: { value: 'Otro' } })
    expect(screen.queryByText('Asunto real ACT-0000001')).not.toBeInTheDocument()
    expect(screen.queryByTitle('Vista previa HTML del correo')).not.toBeInTheDocument()
    expect(mock.mock.calls.some(([path]) => path.includes('/send'))).toBe(false)
  })
  it('muestra un estado vacío sin activaciones y bloquea la vista previa', async () => {
    setup({ noActivations: true })
    await screen.findByText('No hay activaciones disponibles en esta página.')
    expect(screen.getByText('Generar vista previa')).toBeDisabled()
  })
  it('muestra el error comprensible de una activación inexistente', async () => {
    setup({ failPreview: true }); await loaded()
    fireEvent.change(screen.getByLabelText('Activación para vista previa'), { target: { value: '1' } })
    fireEvent.click(screen.getByText('Generar vista previa'))
    expect(await screen.findByRole('alert')).toHaveTextContent('La activación seleccionada no existe.')
  })
  it('conserva el borrador si falla el guardado', async () => {
    setup({ failSave: true }); await loaded()
    fireEvent.click(screen.getByText('Agregar texto al asunto'))
    fireEvent.change(screen.getByLabelText('Texto fijo 1'), { target: { value: 'Conservar' } })
    fireEvent.click(screen.getByText('Guardar plantilla'))
    expect(await screen.findByRole('alert')).toHaveTextContent('Campo no disponible.')
    expect(screen.getByLabelText('Texto fijo 1')).toHaveValue('Conservar')
  })
  it('impide solicitudes simultáneas durante el guardado', async () => {
    const { mock } = setup({ pending: true }); await loaded()
    fireEvent.click(screen.getByText('Guardar plantilla'))
    fireEvent.click(screen.getByText('Procesando plantilla…'))
    await waitFor(() => expect(writes(mock)).toHaveLength(1))
    expect(screen.getByText('Procesando plantilla…')).toBeDisabled()
  })
  it('mantiene el texto plano disponible sin insertar el documento HTML en el editor', async () => {
    const { mock } = setup(); await loaded()
    fireEvent.change(screen.getByLabelText('Activación para vista previa'), { target: { value: '1' } })
    fireEvent.click(screen.getByText('Generar vista previa'))
    await screen.findByTitle('Vista previa HTML del correo')
    const summary = screen.getByText('Contenido de texto plano')
    expect(summary.closest('details')).toHaveAttribute('open')
    expect(screen.getByText(/Primera línea/)).toBeInTheDocument()
    // The server document is isolated in srcdoc, not rendered in the parent DOM.
    expect(screen.queryByText('Ticketyn')).not.toBeInTheDocument()
    expect(writes(mock)).toHaveLength(0)
    expect(writes(mock, 'POST')).toHaveLength(1)
    expect(mock.mock.calls.some(([path]) => /smtp|notification$|\/send/.test(path))).toBe(false)
  })
  it('conserva la vista previa de texto si la API anterior no entrega HTML', async () => {
    setup({ legacyPreview: true }); await loaded()
    fireEvent.change(screen.getByLabelText('Activación para vista previa'), { target: { value: '1' } })
    fireEvent.click(screen.getByText('Generar vista previa'))
    await screen.findByText('Asunto real ACT-0000001')
    expect(screen.getByText(/Primera línea/)).toBeInTheDocument()
    expect(screen.queryByTitle('Vista previa HTML del correo')).not.toBeInTheDocument()
  })
})

it('guarda bloques de texto vacíos sin impedir la vista previa', async () => {
  const { mock } = setup(); await loaded()
  fireEvent.click(screen.getByText('Agregar texto al asunto'))
  fireEvent.click(screen.getByText('Agregar introducción'))
  fireEvent.click(screen.getByText('Agregar firma'))
  fireEvent.click(screen.getByText('Guardar plantilla')); await screen.findByText('Plantilla guardada.')
  expect(JSON.parse(String(writes(mock)[0][1]?.body))).toEqual({ ...empty, subject: [{ type: 'text', text: '' }], body: [{ type: 'introduction', text: '' }, { type: 'signature', text: '' }] })
  fireEvent.change(screen.getByLabelText('Activación para vista previa'), { target: { value: '1' } })
  fireEvent.click(screen.getByText('Generar vista previa'))
  await screen.findByText('Asunto real ACT-0000001')
  expect(writes(mock)).toHaveLength(1)
  expect(writes(mock, 'POST')).toHaveLength(1)
})
