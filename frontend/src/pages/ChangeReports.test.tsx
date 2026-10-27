import { fireEvent, render, screen, waitFor } from '../test/render'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { ChangeReports } from './ChangeReports'
import { jsonResponse } from '../test/fixtures'
import type { ChangeSummary } from '../types/change'

vi.mock('../components/ReportCharts',()=>({
  TrendChart:()=> <div role="img" aria-label="Evolución de cambios" />,
  DistributionChart:({title,rows,integerCounts=false}:{title:string;rows:unknown[];integerCounts?:boolean})=> <div role="img" aria-label={title} data-rows={JSON.stringify(rows)} data-integer-counts={String(integerCounts)} />,
}))
const summary:ChangeSummary={
 kpis:{total:2,finished:1,scheduled:1,executing:0,average_seconds:900,total_seconds:900,evaluable:1,better:1,on_time:0,exceeded:0,not_evaluable:1,saved_seconds:900,exceeded_seconds:0,planned_evaluable_seconds:1800,real_evaluable_seconds:900,late_starts:0,percentages:{better:100,on_time:0,exceeded:0}},
 statuses:[{id:1,label:'En ejecución',count:0},{id:2,label:'Finalizado',count:1},{id:0,label:'Agendado',count:1}],
 change_types:[{id:1,label:'Mantenimiento',count:1},{id:null,label:'Sin clasificar',count:1}],completion_types:[{id:1,label:'Finalizado con éxito',count:1}],sectors:Array.from({length:8},(_,id)=>({id,label:'Sector '+id,count:id})),nodes:[],departments:[],participants:[{id:1,label:'Persona A',manager:2,support:1,count:3},{id:2,label:'Persona B',manager:0,support:2,count:2},{id:3,label:'Persona C',manager:1,support:0,count:1}],trend:[],granularity:'day',generated_at:'2026-10-15T12:00:00Z',
}
function setup(empty=false){
 const mock=vi.fn((url:string)=>{
  if(url.startsWith('/api/change-reports/summary')){
   const filtered=new URL(url,'http://local').searchParams.has('status')
   return Promise.resolve(jsonResponse({...summary,participants:empty?[]:filtered?[{id:1,label:'Persona A',manager:1,support:0,count:1}]:summary.participants,statuses:empty?[]:filtered?[{id:2,label:'Finalizado',count:1}]:summary.statuses}))
  }
  if(url.startsWith('/api/change-types'))return Promise.resolve(jsonResponse([{id:1,name:'Mantenimiento',active:true,created_at:'2026-01-01T00:00:00Z'}]))
  return Promise.resolve(jsonResponse([]))
 });vi.stubGlobal('fetch',mock)
 render(<MemoryRouter initialEntries={['/reports?scope=changes']}><ChangeReports/></MemoryRouter>)
 return mock
}
function stateRows(){return JSON.parse(screen.getByRole('img',{name:'Cambios por Estado'}).getAttribute('data-rows')!)}
describe('gráficos de Control de cambios',()=>{
 it('fija orden y colores Capsule NOC sin ocultar el estado de conteo cero',async()=>{
  setup();await screen.findByRole('img',{name:'Cambios por Estado'})
  expect(stateRows()).toEqual([{label:'Agendado',color:'#176BDF',count:1},{label:'Finalizado',color:'#9673D6',count:1},{label:'En ejecución',color:'#319C81',count:0}])
 })
 it('conserva las tres categorías y sus colores al cambiar filtros',async()=>{
  const mock=setup();await screen.findByRole('img',{name:'Cambios por Estado'})
  fireEvent.click(screen.getByRole('button',{name:'Finalizado'}))
  await waitFor(()=>expect(mock.mock.calls.some(([url])=>url.includes('status=FINISHED'))).toBe(true))
  await waitFor(()=>expect(stateRows().map((row:{count:number})=>row.count)).toEqual([0,1,0]))
  expect(stateRows().map((row:{label:string})=>row.label)).toEqual(['Agendado','Finalizado','En ejecución'])
  expect(stateRows().map((row:{color:string})=>row.color)).toEqual(['#176BDF','#9673D6','#319C81'])
 })
 it('muestra las tres categorías incluso sin estados devueltos',async()=>{
  setup(true);await screen.findByRole('img',{name:'Cambios por Estado'})
  expect(stateRows().map((row:{count:number})=>row.count)).toEqual([0,0,0])
  expect(stateRows()).toHaveLength(3)
 })
 it('repite los seis colores oficiales sin omitir categorías cero ni cambiar los datos',async()=>{
  setup();await screen.findByRole('img',{name:'Cambios por Sector'})
  const rows=JSON.parse(screen.getByRole('img',{name:'Cambios por Sector'}).getAttribute('data-rows')!)
  expect(rows.map((row:{color:string})=>row.color)).toEqual(['#176BDF','#9673D6','#319C81','#D69A46','#568DB5','#218FAD','#176BDF','#9673D6'])
  expect(rows.map(({color,...row}:{color:string})=>row)).toEqual(summary.sectors)
  for(const name of ['Cambios por Tipo de finalización','Eficiencia (%) · solo cambios evaluables','Duraciones de cambios evaluables (horas)']){
   const data=JSON.parse(screen.getByRole('img',{name}).getAttribute('data-rows')!)
   expect(data[0].color).toBe('#176BDF')
   if(data.length>1)expect(data[1].color).toBe('#9673D6')
  }
 })
 it('separa encargados y apoyo sin sumar ambos roles ni atribuir apoyos vacíos',async()=>{
  const mock=setup()
  const managers=await screen.findByRole('img',{name:'Cambios por encargado de ejecución'})
  const support=screen.getByRole('img',{name:'Cambios por personal de apoyo'})
  expect(JSON.parse(managers.getAttribute('data-rows')!)).toEqual([{id:1,label:'Persona A',count:2,color:'#176BDF'},{id:3,label:'Persona C',count:1,color:'#9673D6'}])
  expect(JSON.parse(support.getAttribute('data-rows')!)).toEqual([{id:1,label:'Persona A',count:1,color:'#176BDF'},{id:2,label:'Persona B',count:2,color:'#9673D6'}])
  expect(screen.queryByRole('img',{name:'Participación del personal'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Finalizado'}))
  await waitFor(()=>expect(mock.mock.calls.some(([url])=>url.includes('status=FINISHED'))).toBe(true))
  await waitFor(()=>expect(JSON.parse(screen.getByRole('img',{name:'Cambios por personal de apoyo'}).getAttribute('data-rows')!)).toEqual([]))
  expect(JSON.parse(screen.getByRole('img',{name:'Cambios por encargado de ejecución'}).getAttribute('data-rows')!)).toEqual([{id:1,label:'Persona A',count:1,color:'#176BDF'}])
 })
 it('mantiene ambas gráficas independientes sin participantes',async()=>{
  setup(true)
  for(const name of ['Cambios por encargado de ejecución','Cambios por personal de apoyo']){
   expect(await screen.findByRole('img',{name})).toHaveAttribute('data-rows','[]')
  }
 })
 it('muestra clasificación histórica y envía el filtro de tipo de cambio',async()=>{
  const mock=setup()
  const graph=await screen.findByRole('img',{name:'Cambios por Tipo de cambio'})
  expect(JSON.parse(graph.getAttribute('data-rows')!)).toEqual([{id:1,label:'Mantenimiento',count:1,color:'#176BDF'},{id:null,label:'Sin clasificar',count:1,color:'#9673D6'}])
  const filter=screen.getByRole('combobox',{name:'Tipo de cambio'})
  fireEvent.change(filter,{target:{value:'1'}})
  await waitFor(()=>expect(mock.mock.calls.some(([url])=>url.startsWith('/api/change-reports/summary?')&&url.includes('change_type_id=1'))).toBe(true))
 })
 it('pide enteros solo en cantidades de cambios, incluido Tipo de finalización',async()=>{
  setup();await screen.findByRole('img',{name:'Cambios por Estado'})
  for(const name of ['Cambios por Estado','Cambios por Tipo de cambio','Cambios por Tipo de finalización','Cambios por Sector','Cambios por Nodo','Cambios por Departamento','Cambios por encargado de ejecución','Cambios por personal de apoyo'])expect(screen.getByRole('img',{name})).toHaveAttribute('data-integer-counts','true')
  for(const name of ['Eficiencia (%) · solo cambios evaluables','Duraciones de cambios evaluables (horas)'])expect(screen.getByRole('img',{name})).toHaveAttribute('data-integer-counts','false')
 })
})
