import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeAll, afterAll, describe, expect, it, vi } from 'vitest'
import App from '../App'
import type { InternalTicket } from '../types/internalTicket'
import { jsonResponse } from '../test/fixtures'
import { InternalTicketSelect } from '../components/InternalTicketSelect'

const originalShow = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal')
const originalClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close')
beforeAll(() => {
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value(this: HTMLDialogElement) { this.setAttribute('open', '') } })
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value(this: HTMLDialogElement) { this.removeAttribute('open') } })
})
afterAll(() => {
  if (originalShow) Object.defineProperty(HTMLDialogElement.prototype, 'showModal', originalShow)
  else Reflect.deleteProperty(HTMLDialogElement.prototype, 'showModal')
  if (originalClose) Object.defineProperty(HTMLDialogElement.prototype, 'close', originalClose)
  else Reflect.deleteProperty(HTMLDialogElement.prototype, 'close')
})

const catalog={id:1,name:'NOC',active:true,created_at:'2026-01-01T12:00:00Z'}
const ticket: InternalTicket={id:7,ticket_number:1,reference:'INT-0000001',title:'Energía en nodo central',description:'Sin energía comercial',sector_id:1,node_id:null,department_id:1,incident_type_id:1,responsible_id:null,provider_id:null,resolution:null,start_at:'2026-10-15T14:00:00Z',end_at:null,status:'OPEN',duration_seconds:null,created_at:'2026-10-15T14:05:00Z',updated_at:'2026-10-15T14:05:00Z',sector:catalog,node:null,department:catalog,incident_type:catalog,responsible:null,provider:null,related_count:0}
function setup(path='/internal-tickets', overrides: Partial<typeof ticket> = {}) {
  const current = {...ticket, ...overrides}
  const mock=vi.fn((url:string,init?:RequestInit)=>{
    const u=new URL(url,'http://test')
    if(u.pathname==='/health')return Promise.resolve(jsonResponse({status:'ok'}))
    if(u.pathname==='/api/system/version')return Promise.resolve(jsonResponse({version:'0.5.0'}))
    if(init?.method==='POST'||init?.method==='PATCH')return Promise.resolve(jsonResponse({...current,...JSON.parse(String(init.body))},201))
    if(u.pathname.endsWith('/related'))return Promise.resolve(jsonResponse({total:0,items:[]}))
    if(u.pathname.endsWith('/updates'))return Promise.resolve(jsonResponse({items:[],next_cursor:null}))
    if(u.pathname.endsWith('/escalations'))return Promise.resolve(jsonResponse([]))
    if(u.pathname==='/api/internal-tickets/7')return Promise.resolve(jsonResponse(current))
    if(u.pathname==='/api/internal-tickets')return Promise.resolve(jsonResponse([current]))
    return Promise.resolve(jsonResponse([catalog]))
  })
  vi.stubGlobal('fetch',mock)
  render(<MemoryRouter initialEntries={[path]}><App/></MemoryRouter>)
  return mock
}
describe('Tickets internos',()=>{
  it('lista sin columnas de cliente/circuito y consulta filtros desde backend',async()=>{
    const mock=setup();const table=await screen.findByRole('table',{name:'Tickets internos'})
    expect(within(table).getByRole('link',{name:'INT-0000001'})).toHaveAttribute('href','/internal-tickets/7')
    expect(within(table).queryByRole('columnheader',{name:'Cliente'})).not.toBeInTheDocument()
    expect(within(table).queryByRole('columnheader',{name:'Circuito'})).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Atribuible a proveedor'),{target:{value:'none'}})
    await waitFor(()=>expect(mock.mock.calls.some(([url])=>url.includes('without_provider=true'))).toBe(true))
    fireEvent.click(screen.getByRole('button',{name:'Hoy'}))
    await waitFor(()=>expect(mock.mock.calls.some(([url])=>url.startsWith('/api/internal-tickets?')&&url.includes('from=')&&url.includes('to='))).toBe(true))
  })
  it('crea sin cliente/circuito, exige sector y muestra seguimiento interno',async()=>{
    const mock=setup('/internal-tickets/new')
    await waitFor(()=>expect(screen.getByRole('button',{name:'Guardar'})).toBeEnabled())
    expect(screen.queryByLabelText(/^Cliente/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText(/^Circuito/)).not.toBeInTheDocument()
    expect(screen.queryByText('Contenido autorizado para cliente')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'Guardar'}))
    expect(await screen.findByText('Completa los campos obligatorios antes de guardar.')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/^Título/),{target:{value:'Caída de energía'}})
    fireEvent.change(screen.getByLabelText(/^Descripción/),{target:{value:'Infraestructura afectada'}})
    for(const label of ['Sector','Departamento','Tipo de incidencia interna']){
      fireEvent.focus(screen.getByRole('combobox',{name:new RegExp(`^${label}`)}))
      fireEvent.click(screen.getByRole('option',{name:'NOC'}))
    }
    fireEvent.click(screen.getByRole('button',{name:'Guardar'}))
    await screen.findByRole('heading',{name:'INT-0000001'})
    const write=mock.mock.calls.find(([url,init])=>url==='/api/internal-tickets'&&init?.method==='POST')!
    const body=JSON.parse(String(write[1]!.body))
    expect(body).toMatchObject({sector_id:1,node_id:null,provider_id:null})
    expect(body).not.toHaveProperty('customer_id');expect(body).not.toHaveProperty('circuit_id')
    fireEvent.click(screen.getByRole('button',{name:'Nueva intervención'}))
    await screen.findByRole('dialog')
    expect(screen.queryByLabelText('Visibilidad')).not.toBeInTheDocument()
    expect(screen.queryByText('Visible para cliente')).not.toBeInTheDocument()
  })
  it('detalle conserva estado independiente, relaciones y acciones internas',async()=>{
    setup('/internal-tickets/7')
    await screen.findByRole('heading',{name:'INT-0000001'})
    expect(screen.getByRole('link',{name:'Editar ticket interno'})).toHaveAttribute('href','/internal-tickets/7/edit')
    expect(await screen.findByText('Sin tickets relacionados')).toBeInTheDocument()
    expect(screen.getByRole('button',{name:'Exportar PDF'})).toBeInTheDocument()
    expect(screen.getByRole('button',{name:'Nuevo escalamiento'})).toBeInTheDocument()
  })
  it('búsqueda remota encuentra descripciones que no forman parte de la etiqueta',async()=>{
    const mock=vi.fn(()=>Promise.resolve(jsonResponse([ticket])))
    vi.stubGlobal('fetch',mock)
    render(<MemoryRouter><InternalTicketSelect value="" onChange={vi.fn()}/></MemoryRouter>)
    const input=screen.getByRole('combobox')
    fireEvent.focus(input);fireEvent.change(input,{target:{value:'comercial'}})
    expect(await screen.findByRole('option',{name:'INT-0000001 — Energía en nodo central'})).toBeInTheDocument()
    expect(mock.mock.calls.length).toBe(1)
  })
})

it('pagina la búsqueda remota manteniendo abierto el selector y permite seleccionar otro resultado',async()=>{
  const rows=Array.from({length:20},(_,i)=>({...ticket,id:i+1,reference:`INT-${i+1}`}))
  const mock=vi.fn((url:string)=>Promise.resolve(jsonResponse(new URL(url,'http://test').searchParams.get('offset')==='20'?[{...ticket,id:21,reference:'INT-21'}]:rows)))
  vi.stubGlobal('fetch',mock)
  const changed=vi.fn()
  render(<MemoryRouter><InternalTicketSelect value="" onChange={changed}/></MemoryRouter>)
  fireEvent.focus(screen.getByRole('combobox'))
  const next=await screen.findByRole('button',{name:'Más resultados'})
  fireEvent.mouseDown(next);fireEvent.click(next)
  fireEvent.click(await screen.findByRole('option',{name:'INT-21 — Energía en nodo central'}))
  expect(changed).toHaveBeenCalledWith('21')
  expect(mock.mock.calls.some(([url])=>url.includes('offset=20'))).toBe(true)
})


it('guarda seguimiento interno sin opciones de cliente',async()=>{
  const mock=setup('/internal-tickets/7')
  await screen.findByRole('heading',{name:'INT-0000001'})
  fireEvent.click(screen.getByRole('button',{name:'Nueva intervención'}))
  const dialog=await screen.findByRole('dialog')
  await waitFor(()=>expect(within(dialog).getByRole('button',{name:'Registrar actualización'})).toBeEnabled())
  fireEvent.change(within(dialog).getByLabelText(/^Descripción/),{target:{value:'Verificación técnica'}})
  fireEvent.click(within(dialog).getByRole('button',{name:'Registrar actualización'}))
  await waitFor(()=>expect(mock.mock.calls.some(([url,init])=>url==='/api/internal-tickets/7/updates'&&init?.method==='POST')).toBe(true))
  const call=mock.mock.calls.find(([url,init])=>url==='/api/internal-tickets/7/updates'&&init?.method==='POST')!
  expect(JSON.parse(String(call[1]!.body)).visibility).toBe('INTERNAL')
})


it('permite atribuir proveedor a un interno cerrado conservando estado y fin',async()=>{
  const mock=setup('/internal-tickets/7/edit',{status:'CLOSED',end_at:'2026-10-15T16:00:00Z'})
  await waitFor(()=>expect(screen.getByRole('button',{name:'Guardar cambios'})).toBeEnabled())
  fireEvent.focus(screen.getByRole('combobox',{name:'Atribuible a proveedor'}))
  fireEvent.click(screen.getByRole('option',{name:'NOC'}))
  fireEvent.click(screen.getByRole('button',{name:'Guardar cambios'}))
  await waitFor(()=>expect(mock.mock.calls.some(([url,init])=>url==='/api/internal-tickets/7'&&init?.method==='PATCH')).toBe(true))
  const call=mock.mock.calls.find(([url,init])=>url==='/api/internal-tickets/7'&&init?.method==='PATCH')!
  expect(JSON.parse(String(call[1]!.body))).toMatchObject({provider_id:1,status:'CLOSED',end_at:'2026-10-15T16:00:00Z'})
})
