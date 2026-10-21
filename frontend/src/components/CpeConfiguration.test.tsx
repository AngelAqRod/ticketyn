import { fireEvent, render, screen, waitFor } from '../test/render'
import { describe, it, expect, vi } from 'vitest'
import { CpeConfiguration } from './CpeConfiguration'
import { jsonResponse } from '../test/fixtures'
const text = '  /interface\n\tset name="<script>alert(1)</script>"\n  secret=example  \n'
function setup(fail = false, pending = false) {
  const mock = vi.fn((_path: string, options?: RequestInit) => options?.method === 'PATCH' ? pending ? new Promise<Response>(() => {}) : Promise.resolve(fail ? jsonResponse({ detail:'Error al guardar' },500) : jsonResponse({ configuration: JSON.parse(String(options.body)).configuration })) : Promise.resolve(jsonResponse({ configuration: text })))
  vi.stubGlobal('fetch', mock); render(<CpeConfiguration circuitId={4} />); return mock
}
describe('Configuración CPE', () => {
  it('lee con formato literal, sin interpretar HTML', async () => {
    setup()
    const pre = await screen.findByLabelText('Configuración guardada')
    expect(pre.textContent).toBe(text)
    expect(pre.querySelector('script')).toBeNull()
    expect(pre).toHaveClass('overflow-auto', 'whitespace-pre', 'font-mono')
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })
  it('cancela sin guardar y persiste sin trim al guardar', async () => {
    const mock = setup(); await screen.findByLabelText('Configuración guardada')
    fireEvent.click(screen.getByRole('button',{ name:'Editar' }))
    const editor = screen.getByRole('textbox')
    expect(editor).toHaveFocus()
    fireEvent.change(editor,{ target:{ value:'Borrador' } })
    fireEvent.click(screen.getByRole('button',{ name:'Cancelar' }))
    expect(screen.getByLabelText('Configuración guardada').textContent).toBe(text)
    expect(mock.mock.calls.some(([,options])=>options?.method==='PATCH')).toBe(false)
    fireEvent.click(screen.getByRole('button',{ name:'Editar' }))
    const updated = '   texto\n\tcon formato  \n'
    fireEvent.change(screen.getByRole('textbox'),{ target:{value:updated} })
    fireEvent.click(screen.getByRole('button',{ name:'Guardar' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Configuración guardada')
    expect(screen.getByLabelText('Configuración guardada').textContent).toBe(updated)
    expect(JSON.parse(String(mock.mock.calls.find(([,options])=>options?.method==='PATCH')![1]?.body)).configuration).toBe(updated)
  })
  it('conserva el borrador y permite corregir un error', async () => {
    setup(true); await screen.findByLabelText('Configuración guardada')
    fireEvent.click(screen.getByRole('button',{ name:'Editar' }))
    fireEvent.change(screen.getByRole('textbox'),{target:{value:'Datos conservados'}})
    fireEvent.click(screen.getByRole('button',{name:'Guardar'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('Error al guardar')
    expect(screen.getByRole('textbox')).toHaveValue('Datos conservados')
    expect(screen.getByRole('button',{name:'Guardar'})).toBeEnabled()
  })
  it('bloquea envíos duplicados', async () => {
    const mock=setup(false,true); await screen.findByLabelText('Configuración guardada')
    fireEvent.click(screen.getByRole('button',{name:'Editar'})); const button=screen.getByRole('button',{name:'Guardar'})
    fireEvent.click(button); fireEvent.click(button)
    await waitFor(()=>expect(mock.mock.calls.filter(([,options])=>options?.method==='PATCH')).toHaveLength(1))
    expect(button).toBeDisabled()
  })
})
