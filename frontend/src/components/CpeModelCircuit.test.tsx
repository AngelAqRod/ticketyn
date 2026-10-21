import { fireEvent, render, screen, waitFor } from '../test/render'
import { MemoryRouter } from 'react-router'
import { it, expect, vi } from 'vitest'
import { CatalogAdmin } from './CatalogAdmin'
import { jsonResponse } from '../test/fixtures'

it('conserva un modelo inactivo y permite reemplazarlo por uno activo en el editor compartido',async()=>{
  const created_at='2026-01-01T00:00:00Z'
  const inactive={id:7,name:'Modelo anterior',active:false,created_at}, active={id:8,name:'Modelo activo',active:true,created_at}
  const circuit={id:1,customer_id:1,circuit_code:'C-1',description:'Circuito',active:true,created_at,node_id:1,sector_id:1,cpe_model_id:7,cpe_model:inactive}
  const saved=vi.fn()
  const mock=vi.fn((path:string,options?:RequestInit)=>{
    if(options?.method==='PATCH')return Promise.resolve(jsonResponse({...circuit,...JSON.parse(String(options.body)),cpe_model:active}))
    if(path.includes('/cpe-models'))return Promise.resolve(jsonResponse([inactive,active]))
    if(path.includes('/service-types'))return Promise.resolve(jsonResponse([]))
    if(path.includes('/customers'))return Promise.resolve(jsonResponse([{id:1,customer_code:'C',name:'Cliente',active:true,created_at}]))
    return Promise.resolve(jsonResponse([{id:1,name:'Asignación',active:true,created_at}]))
  })
  vi.stubGlobal('fetch',mock)
  render(<MemoryRouter><CatalogAdmin kind="circuits" circuitEditor={{item:circuit,onSaved:saved,onCancel:vi.fn(),onBusyChange:vi.fn()}} /></MemoryRouter>)
  const input=screen.getByRole('combobox',{name:'Modelo de CPE actual'})
  await waitFor(()=>expect(input).toHaveValue('Modelo anterior'))
  fireEvent.click(input)
  expect(await screen.findByRole('option',{name:/^Modelo anterior/})).toHaveAttribute('aria-disabled','true')
  fireEvent.click(screen.getByRole('option',{name:'Modelo activo'}))
  fireEvent.click(screen.getByRole('button',{name:'Guardar'}))
  await waitFor(()=>expect(saved).toHaveBeenCalled())
  const payload=JSON.parse(String(mock.mock.calls.find(([,options])=>options?.method==='PATCH')![1]?.body))
  expect(payload.cpe_model_id).toBe(8)
  expect(payload).not.toHaveProperty('cpe_configuration')
})
