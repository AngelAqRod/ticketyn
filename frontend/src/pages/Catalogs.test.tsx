import { fireEvent, render, screen, within } from '../test/render'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Catalogs } from './Catalogs'

vi.mock('../components/CatalogAdmin', () => ({ CatalogAdmin: ({ kind }: { kind: string }) => <div data-testid="catalog-content">{kind}</div> }))

vi.mock('../components/PortNomenclatureAdmin', () => ({ PortNomenclatureAdmin: () => <div data-testid="catalog-content">port-nomenclatures</div> }))

afterEach(()=>vi.restoreAllMocks())

function scrollingStrip(initialWidth=300){
  render(<Catalogs />)
  const viewport=screen.getByRole('group',{name:'Categorías de catálogos'}) as HTMLDivElement
  const buttons=within(viewport).getAllByRole('button')
  let width=initialWidth
  const total=buttons.length*124+2
  Object.defineProperties(viewport,{clientWidth:{configurable:true,get:()=>width},scrollWidth:{configurable:true,get:()=>total}})
  vi.spyOn(viewport,'getBoundingClientRect').mockImplementation(()=>new DOMRect(0,0,width,36))
  buttons.forEach((button,index)=>vi.spyOn(button,'getBoundingClientRect').mockImplementation(()=>new DOMRect(3+index*124-viewport.scrollLeft,0,120,30)))
  const scroll=vi.fn((options?:ScrollToOptions|number,_y?:number)=>{viewport.scrollLeft=typeof options==='number'?options:options?.left??0;fireEvent.scroll(viewport)})
  viewport.scrollTo=scroll
  fireEvent.resize(window)
  return{viewport,buttons,scroll,total,resize:(next:number)=>{width=next;fireEvent.resize(window)}}
}

describe('selector de Catálogos', () => {
  it('conserva el orden canónico y cambia únicamente el catálogo seleccionado', () => {
    render(<Catalogs />)
    const nav = screen.getByRole('navigation', { name: 'Catálogos' })
    const buttons = within(within(nav).getByRole('group',{name:'Categorías de catálogos'})).getAllByRole('button')
    expect(buttons.map(button => button.textContent)).toEqual(['Sectores', 'Departamentos', 'Tipos de incidencia', 'Nodos', 'Puestos', 'Motivos de escalamiento', 'Tipos de servicio', 'Motivos de baja', 'Modelos de CPE', 'Tipos de incidencia interna', 'Proveedores', 'Tipos de finalización de cambios', 'Tipos de cambio', 'Nomenclaturas de puertos'])
    expect(buttons[0]).toHaveAttribute('aria-pressed', 'true')
    buttons.forEach((button, index) => {
      fireEvent.click(button)
      expect(button).toHaveAttribute('aria-pressed', 'true')
      expect(buttons.filter(item => item.getAttribute('aria-pressed') === 'true')).toHaveLength(1)
      expect(screen.getByTestId('catalog-content')).toHaveTextContent(['sectors', 'departments', 'incident-types', 'nodes', 'positions', 'escalation-reasons', 'service-types', 'deactivation-reasons', 'cpe-models', 'internal-incident-types', 'providers', 'change-completion-types', 'change-types', 'port-nomenclatures'][index])
    })
  })
  it('desplaza solo la barra y deshabilita flechas e indicadores en cada extremo',()=>{
    const {viewport,scroll,total}=scrollingStrip()
    const previous=screen.getByRole('button',{name:'Catálogos anteriores'})
    const next=screen.getByRole('button',{name:'Catálogos siguientes'})
    expect(previous).toBeDisabled();expect(next).toBeEnabled()
    expect(document.querySelector('.catalog-selector-overflow-left')).not.toHaveClass('is-visible')
    expect(document.querySelector('.catalog-selector-overflow-right')).toHaveClass('is-visible')
    fireEvent.click(next)
    expect(scroll).toHaveBeenLastCalledWith({left:240,behavior:'smooth'})
    expect(previous).toBeEnabled()
    viewport.scrollLeft=total-viewport.clientWidth;fireEvent.scroll(viewport)
    expect(next).toBeDisabled()
    expect(document.querySelector('.catalog-selector-overflow-right')).not.toHaveClass('is-visible')
    const calls=scroll.mock.calls.length;fireEvent.click(next);expect(scroll).toHaveBeenCalledTimes(calls)
    fireEvent.click(previous);expect(next).toBeEnabled()
    viewport.scrollLeft=0;fireEvent.scroll(viewport);expect(previous).toBeDisabled()
  })
  it('revela la opción activa y conserva la posición cuando ya está visible',()=>{
    const {viewport,buttons,scroll,total}=scrollingStrip()
    fireEvent.click(buttons.at(-1)!)
    expect(viewport.scrollLeft).toBe(total-viewport.clientWidth)
    expect(buttons.at(-1)).toHaveAttribute('aria-pressed','true')
    expect(screen.getByTestId('catalog-content')).toHaveTextContent('port-nomenclatures')
    scroll.mockClear();fireEvent.click(buttons.at(-1)!);expect(scroll).not.toHaveBeenCalled()
    fireEvent.click(buttons[0]);expect(viewport.scrollLeft).toBe(0)
  })
  it('recalcula extremos y mantiene la selección visible al redimensionar',()=>{
    const {viewport,buttons,total,resize}=scrollingStrip()
    fireEvent.click(buttons.at(-1)!)
    resize(220);expect(viewport.scrollLeft).toBe(total-220)
    resize(total+50)
    expect(screen.getByRole('button',{name:'Catálogos siguientes'})).toBeDisabled()
    // Browsers clamp scrollLeft when the viewport becomes wider than its content.
    viewport.scrollLeft=0;fireEvent.scroll(viewport)
    expect(screen.getByRole('button',{name:'Catálogos anteriores'})).toBeDisabled()
  })
  it('respeta movimiento reducido y revela opciones que reciben foco por teclado',()=>{
    vi.stubGlobal('matchMedia',vi.fn(()=>({matches:true})))
    const {buttons,scroll}=scrollingStrip()
    fireEvent.focus(buttons.at(-1)!)
    expect(scroll).toHaveBeenLastCalledWith(expect.objectContaining({behavior:'auto'}))
    expect(buttons[0]).toHaveAttribute('aria-pressed','true')
    fireEvent.click(screen.getByRole('button',{name:'Catálogos anteriores'}))
    expect(scroll).toHaveBeenLastCalledWith(expect.objectContaining({behavior:'auto'}))
  })
  it('mantiene ambas flechas deshabilitadas cuando todas las opciones caben',()=>{
    const {scroll}=scrollingStrip(2400)
    expect(screen.getByRole('button',{name:'Catálogos anteriores'})).toBeDisabled()
    expect(screen.getByRole('button',{name:'Catálogos siguientes'})).toBeDisabled()
    expect(scroll).not.toHaveBeenCalled()
  })

})
