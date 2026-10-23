import { fireEvent,render,screen,waitFor,within } from '../test/render'
import { MemoryRouter } from 'react-router'
import { beforeEach,describe,expect,it,vi } from 'vitest'
// Authentication is exercised in auth/AuthGate.test.tsx; these tests isolate operational routing.
vi.mock('../auth/AuthGate', () => ({ AuthGate: ({ children }: { children: React.ReactNode }) => children }))

import App from '../App'
import { jsonResponse } from '../test/fixtures'
import type { Change } from '../types/change'
vi.mock('../components/ReportCharts',()=>({TrendChart:()=> <div/>,DistributionChart:()=> <div/>,ActivityChart:()=> <div/>,RankingChart:()=> <div/>}))
const catalog={id:1,name:'NOC',active:true,created_at:'2026-01-01T00:00:00Z'}
const person={...catalog,name:'Encargado NOC',department_id:1,department:catalog}
const item:Change={change_type_id:1,change_type:catalog,id:1,reference:'CAM-0000001',ticket_number:1,title:'Actualización de transporte',description:'Configuración histórica',sector_id:1,node_id:null,manager_id:1,manager_name:person.name,department_id:1,department_name:'NOC',support:[],status:'FINISHED',proposed_start:'2026-10-15T17:00:00Z',proposed_end:'2026-10-15T21:00:00Z',actual_start:'2026-10-15T19:00:00Z',actual_end:'2026-10-15T21:00:00Z',completion_type_id:1,completion_name:'Finalizado con éxito',efficiency_eligible:true,final_notes:'Finalizado',created_at:'2026-10-16T00:00:00Z',updated_at:'2026-10-16T00:00:00Z',sector:catalog,node:null,internal_tickets:[],planned_seconds:14400,actual_seconds:7200,efficiency:'BETTER',efficiency_label:'Mayor eficiencia',variation_percent:50,saved_seconds:7200,exceeded_seconds:0,late_start:true}
function setup(path='/changes',empty=false,initialSupport:Change['support']=[],overrides:Partial<Change>={},unavailable=false,customItems?:Change[]){
 vi.stubGlobal('URL',class extends URL {static createObjectURL=vi.fn(()=> 'blob:changes');static revokeObjectURL=vi.fn()})
 const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{})
 const mock=vi.fn((url:string,init?:RequestInit)=>{
  const u=new URL(url,'http://local')
  if(u.pathname==='/health')return Promise.resolve(jsonResponse({status:'ok'}))
  if(u.pathname==='/api/system/version')return Promise.resolve(jsonResponse({version:'0.5.0'}))
  if(u.pathname.includes('/export/')||u.pathname.endsWith('/reports/pdf'))return Promise.resolve(new Response(new Blob(['pdf'])))
  if(init?.method==='POST'||init?.method==='PATCH')return Promise.resolve(jsonResponse({...item,...JSON.parse(String(init.body))},init.method==='POST'?201:200))
  if(u.pathname==='/api/changes')return Promise.resolve(jsonResponse({total:empty?0:(customItems?customItems.length:1),items:empty?[]:(customItems??[item])}))
  if(u.pathname==='/api/changes/1')return Promise.resolve(jsonResponse({...item,...overrides,support:initialSupport}))
  if(u.pathname.endsWith('/updates'))return Promise.resolve(jsonResponse({total:0,items:[]}))
  if(u.pathname.endsWith('/audit'))return Promise.resolve(jsonResponse([]))
  if(u.pathname==='/api/change-types')return Promise.resolve(jsonResponse([catalog,{...catalog,id:2,name:'Tipo inactivo',active:false}]))
  if(u.pathname==='/api/responsibles')return Promise.resolve(jsonResponse([{...person,operational_selectable:!unavailable},{...person,id:2,name:'Apoyo NOC',operational_selectable:!unavailable},{...person,id:3,name:'Segundo apoyo NOC'}]))
  if(u.pathname==='/api/change-completion-types')return Promise.resolve(jsonResponse([{...catalog,name:'Finalizado con éxito',applies_efficiency:true}]))
  if(u.pathname==='/api/settings/change-number')return Promise.resolve(jsonResponse({id:1,prefix:'CAM',separator:'-',next_number:1,padding:7}))
  if(u.pathname==='/api/settings/ticket-number')return Promise.resolve(jsonResponse({id:1,prefix:'T',separator:'-',next_number:1,padding:7}))
  return Promise.resolve(jsonResponse([catalog]))
 });vi.stubGlobal('fetch',mock)
 render(<MemoryRouter initialEntries={[path]}><App/></MemoryRouter>)
 return {mock,click}
}
beforeEach(()=>localStorage.clear())
it('excluye encargados no seleccionables en nuevas ventanas',async()=>{
 setup('/changes/new',false,[],{},true)
 const manager=await screen.findByLabelText(/Encargado de ejecución/)
 await waitFor(()=>expect(within(manager).getByRole('option',{name:'Segundo apoyo NOC'})).toBeInTheDocument())
 expect(within(manager).queryByRole('option',{name:'Encargado NOC'})).not.toBeInTheDocument()
 expect(within(manager).queryByRole('option',{name:'Apoyo NOC'})).not.toBeInTheDocument()
})
it('conserva el encargado histórico no seleccionable al editar sin ofrecer nuevos no seleccionables',async()=>{
 setup('/changes/1/edit',false,[{id:2,name:'Apoyo NOC'}],{},true)
 const manager=await screen.findByLabelText(/Encargado de ejecución/)
 await waitFor(()=>expect(manager).toHaveValue('1'))
 expect(within(manager).getByRole('option',{name:'Encargado NOC'})).toBeInTheDocument()
 expect(within(manager).queryByRole('option',{name:'Apoyo NOC'})).not.toBeInTheDocument()
 expect(screen.getByRole('button',{name:/Quitar Apoyo NOC/})).toBeInTheDocument()
})
describe('Control de cambios',()=>{
 it('integra navegación, listado y resultados independientes de puntualidad',async()=>{
  const {click}=setup()
  const table=await screen.findByRole('table',{name:'Control de cambios'})
  expect(within(table).getByRole('link',{name:item.reference})).toHaveAttribute('href','/changes/1')
  expect(within(table).getByText(/Mayor eficiencia · 50%/)).toBeInTheDocument()
  expect(within(table).getByText('Inicio tardío')).toBeInTheDocument()
  expect(screen.getByRole('link',{name:/Control de cambios/})).toHaveAttribute('href','/changes')
  click.mockRestore()
 })
 it('conserva filtros al cambiar a calendario y permite navegar años',async()=>{
  const {mock,click}=setup('/changes?sector_id=1&day=2026-10-15')
  await screen.findByRole('table',{name:'Control de cambios'})
  fireEvent.click(screen.getByRole('button',{name:'Calendario'}))
  await screen.findByLabelText('Calendario de cambios')
  expect(screen.getByRole('combobox',{name:'Sector'})).toHaveValue('1')
  fireEvent.change(screen.getByLabelText('Fecha del calendario'),{target:{value:'2035-01-15'}})
  await waitFor(()=>expect(mock.mock.calls.some(([url])=>url.startsWith('/api/changes?')&&url.includes('2035-01-01'))).toBe(true))
  fireEvent.click(screen.getByRole('button',{name:'Listado'}))
  await screen.findByRole('table',{name:'Control de cambios'})
  expect(localStorage.getItem('ticketyn-change-view')).toBe('list')
  click.mockRestore()
 })
 it.each(['month','week'])('mantiene eventos y encabezados de días alineados en vista %s',async mode=>{
  const {click}=setup('/changes?view=calendar&calendar='+mode+'&day=2026-10-15')
  const calendar=await screen.findByLabelText('Calendario de cambios')
  const headers=within(calendar).getByLabelText('Días de la semana')
  expect(Array.from(headers.children).map(child=>child.textContent)).toEqual(['LUNES','MARTES','MIÉRCOLES','JUEVES','VIERNES','SÁBADO','DOMINGO'])
  const date=within(calendar).getByRole('link',{name:'Jueves, 2026-10-15'})
  expect(date).toHaveAttribute('href','/changes/new?date=2026-10-15')
  expect(date).toHaveClass('change-calendar-date')
  const event=within(calendar).getByRole('link',{name:/CAM-0000001/})
  expect(event).toHaveClass('change-calendar-event','change-status-FINISHED')
  expect(event).toHaveAttribute('href','/changes/1')
  expect(Array.from(event.children).map(child=>child.textContent)).toEqual(['15/10 11:00 → 15/10 15:00','CAM-0000001','Actualización de transporte','Finalizado'])
  expect(calendar.querySelectorAll('.change-calendar-cell')).toHaveLength(mode==='month'?31:7)
  if(mode==='month')expect(calendar.querySelectorAll('.change-calendar-placeholder')).toHaveLength(3)
  click.mockRestore()
 })
 it('destaca únicamente la fecha actual de Guatemala sin cambiar su navegación',async()=>{
  const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'America/Guatemala',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())
  const {click}=setup('/changes?view=calendar&calendar=month&day='+today)
  const calendar=await screen.findByLabelText('Calendario de cambios')
  const current=calendar.querySelectorAll('[aria-current="date"]')
  expect(current).toHaveLength(1)
  expect(current[0]).toHaveAttribute('href','/changes/new?date='+today)
  click.mockRestore()
 })
 it('implementa Industrial Split Cut 2.0, Technical Frame B y Corner Frame E con fidelidad visual',async()=>{
  const {click}=setup('/changes?view=calendar&calendar=month&day=2026-10-15')
  const header=await screen.findByLabelText('Cabecera del calendario')
  expect(header).toHaveClass('industrial-split-cut-header')
  expect(header.querySelector('.isc-top-accent')).toBeInTheDocument()
  expect(header.querySelector('.isc-diagonal-border')).toBeInTheDocument()

  // Nivel superior: bloque de fecha e información temporal
  expect(within(header).getByText('OCT')).toBeInTheDocument()
  expect(within(header).getByText('15')).toBeInTheDocument()
  expect(within(header).getByText('Octubre 2026')).toBeInTheDocument()
  expect(within(header).getByText(/Jueves · Semana 42/)).toBeInTheDocument()

  // Nivel inferior: controles existentes
  expect(within(header).getByRole('button',{name:'Período anterior'})).toBeInTheDocument()
  expect(within(header).getByRole('button',{name:'Período siguiente'})).toBeInTheDocument()
  expect(within(header).getByRole('button',{name:'Hoy'})).toBeInTheDocument()
  expect(within(header).getByLabelText('Fecha del calendario')).toHaveValue('2026-10-15')
  expect(within(header).getByRole('button',{name:'Mes'})).toHaveAttribute('aria-pressed','true')

  // Technical Frame B
  const calendar=await screen.findByLabelText('Calendario de cambios')
  const weekdayHeaders=calendar.querySelectorAll('.technical-frame-b')
  expect(weekdayHeaders).toHaveLength(7)
  for(let i=0;i<5;i++){
   expect(weekdayHeaders[i]).toHaveClass('technical-frame-b--weekday')
   expect(weekdayHeaders[i].querySelector('.tf-b-bracket-tl')).toBeInTheDocument()
   expect(weekdayHeaders[i].querySelector('.tf-b-bracket-br')).toBeInTheDocument()
   expect(weekdayHeaders[i].querySelector('.tf-b-top-line')).toBeInTheDocument()
   expect(weekdayHeaders[i].querySelector('.tf-b-diagonal-line')).toBeInTheDocument()
  }
  expect(weekdayHeaders[5]).toHaveClass('technical-frame-b--weekend')
  expect(weekdayHeaders[6]).toHaveClass('technical-frame-b--weekend')

  // Corner Frame E
  const cellWithChanges=calendar.querySelector('.corner-frame-e--has-changes')
  expect(cellWithChanges).toBeInTheDocument()
  expect(cellWithChanges?.querySelector('.cf-e-bracket-tl')).toBeInTheDocument()
  expect(cellWithChanges?.querySelector('.cf-e-bracket-br')).toBeInTheDocument()
  expect(cellWithChanges?.querySelector('.cf-e-top-line')).toBeInTheDocument()
  expect(cellWithChanges?.querySelector('.cf-e-diagonal-line')).toBeInTheDocument()

  const cellNoChanges=calendar.querySelector('.corner-frame-e--no-changes')
  expect(cellNoChanges).toBeInTheDocument()

  click.mockRestore()
 })
 it('destaca HOY y activa segmentos ámbar cuando la fecha seleccionada es hoy',async()=>{
  const today=new Intl.DateTimeFormat('sv-SE',{timeZone:'America/Guatemala',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())
  const {click}=setup('/changes?view=calendar&calendar=month&day='+today)
  const header=await screen.findByLabelText('Cabecera del calendario')
  expect(within(header).getByText('HOY')).toHaveClass('isc-date-block-today')
  const calendar=await screen.findByLabelText('Calendario de cambios')
  const todayCell=calendar.querySelector('.corner-frame-e--today')
  expect(todayCell).toBeInTheDocument()
  click.mockRestore()
 })
 it('renderiza tarjetas de cambios con diseño Technical Cut y formato de intervalo completo',async()=>{
  const midnightScheduled: Change = {
   ...item,
   id: 2,
   reference: 'CAM-0000002',
   title: 'Mantenimiento de fibra',
   status: 'SCHEDULED',
   proposed_start: '2026-10-16T05:00:00Z',
   proposed_end: '2026-10-16T09:00:00Z',
  }
  const executingChange: Change = {
   ...item,
   id: 3,
   reference: 'CAM-0000003',
   title: 'Corte de energía programado',
   status: 'EXECUTING',
   proposed_start: '2026-10-15T15:00:00Z',
   proposed_end: '2026-10-15T16:30:00Z',
  }
  const {click}=setup('/changes?view=calendar&calendar=month&day=2026-10-15',false,[],{},false,[item,midnightScheduled,executingChange])
  const calendar=await screen.findByLabelText('Calendario de cambios')

  // 1. Tarjeta FINISHED
  const finishedCard=within(calendar).getByRole('link',{name:/CAM-0000001/})
  expect(finishedCard).toHaveClass('change-calendar-event','technical-cut-card','change-status-FINISHED')
  expect(finishedCard).toHaveAttribute('href','/changes/1')
  expect(Array.from(finishedCard.children).map(child=>child.textContent)).toEqual([
   '15/10 11:00 → 15/10 15:00',
   'CAM-0000001',
   'Actualización de transporte',
   'Finalizado'
  ])

  // 2. Tarjeta SCHEDULED (cruce de medianoche)
  const scheduledCard=within(calendar).getByRole('link',{name:/CAM-0000002/})
  expect(scheduledCard).toHaveClass('change-calendar-event','technical-cut-card','change-status-SCHEDULED')
  expect(scheduledCard).toHaveAttribute('href','/changes/2')
  expect(Array.from(scheduledCard.children).map(child=>child.textContent)).toEqual([
   '15/10 23:00 → 16/10 03:00',
   'CAM-0000002',
   'Mantenimiento de fibra',
   'Agendado'
  ])

  // 3. Tarjeta EXECUTING
  const executingCard=within(calendar).getByRole('link',{name:/CAM-0000003/})
  expect(executingCard).toHaveClass('change-calendar-event','technical-cut-card','change-status-EXECUTING')
  expect(executingCard).toHaveAttribute('href','/changes/3')
  expect(Array.from(executingCard.children).map(child=>child.textContent)).toEqual([
   '15/10 09:00 → 15/10 10:30',
   'CAM-0000003',
   'Corte de energía programado',
   'En ejecución'
  ])

  click.mockRestore()
 })
 it('implementa vista semanal Extended Grid con 7 columnas, Technical Frame B, Corner Frame E y eventos estructurados',async()=>{
  const {click}=setup('/changes?view=calendar&calendar=week&day=2026-10-15')
  const calendar=await screen.findByLabelText('Calendario de cambios')

  // Clase específica de vista semanal
  expect(calendar).toHaveClass('change-calendar','change-calendar-week')

  // 7 encabezados LUNES a DOMINGO
  const headers=within(calendar).getByLabelText('Días de la semana')
  expect(Array.from(headers.children).map(child=>child.textContent)).toEqual(['LUNES','MARTES','MIÉRCOLES','JUEVES','VIERNES','SÁBADO','DOMINGO'])

  // 7 celdas alineadas
  const cells=calendar.querySelectorAll('.change-calendar-cell')
  expect(cells).toHaveLength(7)

  // Celdas de fin de semana (Sábado y Domingo, índices 5 y 6) tienen variante borgoña
  expect(cells[5]).toHaveClass('corner-frame-e--weekend')
  expect(cells[6]).toHaveClass('corner-frame-e--weekend')

  // Celdas de lunes a viernes no son fin de semana
  for(let i=0;i<5;i++){
   expect(cells[i]).not.toHaveClass('corner-frame-e--weekend')
  }

  // Día jueves 15/10 (índice 3) tiene cambios y contenedor de eventos estructurado
  const thursdayCell=cells[3]
  expect(thursdayCell).toHaveClass('corner-frame-e--has-changes')
  const eventsContainer=thursdayCell.querySelector('.change-calendar-events')
  expect(eventsContainer).toBeInTheDocument()

  // Tarjeta de cambio dentro del contenedor de eventos
  const event=within(thursdayCell as HTMLElement).getByRole('link',{name:/CAM-0000001/})
  expect(event).toHaveClass('change-calendar-event','technical-cut-card','change-status-FINISHED')
  expect(event).toHaveAttribute('href','/changes/1')

  // Cápsula de fecha siempre visible en el heading
  const dateLink=within(thursdayCell as HTMLElement).getByRole('link',{name:'Jueves, 2026-10-15'})
  expect(dateLink).toHaveAttribute('href','/changes/new?date=2026-10-15')

  // Días sin cambios tienen clase corner-frame-e--no-changes
  expect(cells[0]).toHaveClass('corner-frame-e--no-changes')

  click.mockRestore()
 })
 it('implementa vista diaria Technical Timeline Expandida (B2) con cronología, encabezado de jornada y tarjeta expandida',async()=>{
  const {click}=setup('/changes?view=calendar&calendar=day&day=2026-10-15')
  const calendar=await screen.findByLabelText('Calendario de cambios')
  expect(calendar).toHaveClass('change-calendar-day-timeline')

  // Encabezado de jornada
  const dayHeader=within(calendar).getByLabelText('Encabezado de jornada')
  expect(dayHeader).toHaveClass('timeline-day-header')
  expect(within(dayHeader).getByText('JUEVES · 15 OCTUBRE 2026')).toBeInTheDocument()

  // Cronología
  const stream=within(calendar).getByLabelText('Cronología de cambios')
  expect(stream).toHaveClass('timeline-stream')

  // Columna horaria izquierda
  expect(within(stream).getByText('11:00')).toHaveClass('timeline-time-start')
  expect(within(stream).getByText('Fin: 15:00')).toHaveClass('timeline-time-end')

  // Tarjeta Technical Cut expandida
  const event=within(stream).getByRole('link',{name:/CAM-0000001/})
  expect(event).toHaveClass('change-calendar-event','technical-cut-card','timeline-expanded-card','change-status-FINISHED')
  expect(event).toHaveAttribute('href','/changes/1')

  // Jerarquía: Código, Estado, Título, Intervalo
  expect(within(event).getByText('CAM-0000001')).toHaveClass('change-card-ref')
  expect(within(event).getByText('Finalizado')).toHaveClass('change-card-status')
  expect(within(event).getByText('Actualización de transporte')).toHaveClass('change-card-title')
  expect(within(event).getByText('15/10 11:00 → 15/10 15:00')).toBeInTheDocument()

  click.mockRestore()
 })
 it('muestra estado vacío discreto en vista diaria cuando no hay ventanas de mantenimiento',async()=>{
  const {click}=setup('/changes?view=calendar&calendar=day&day=2026-10-15',true)
  const calendar=await screen.findByLabelText('Calendario de cambios')

  // Encabezado de jornada se conserva
  expect(within(calendar).getByText('JUEVES · 15 OCTUBRE 2026')).toBeInTheDocument()

  // Mensaje discreto de estado vacío
  expect(within(calendar).getByText('Sin ventanas de mantenimiento programadas para este día')).toBeInTheDocument()
  expect(calendar.querySelector('.timeline-stream')).not.toBeInTheDocument()

  click.mockRestore()
 })
 it('ordena cronológicamente múltiples eventos y cruces de medianoche en la vista diaria',async()=>{
  const changeEarly: Change = {
   ...item,
   id: 10,
   reference: 'CAM-0000010',
   title: 'Revisión matutina',
   status: 'FINISHED',
   proposed_start: '2026-10-15T14:00:00Z',
   proposed_end: '2026-10-15T15:30:00Z',
  }
  const changeMid: Change = {
   ...item,
   id: 11,
   reference: 'CAM-0000011',
   title: 'Migración en ejecución',
   status: 'EXECUTING',
   proposed_start: '2026-10-15T18:00:00Z',
   proposed_end: '2026-10-15T20:00:00Z',
  }
  const changeLateMidnight: Change = {
   ...item,
   id: 12,
   reference: 'CAM-0000012',
   title: 'Corte nocturno con cruce de medianoche',
   status: 'SCHEDULED',
   proposed_start: '2026-10-16T05:00:00Z',
   proposed_end: '2026-10-16T09:00:00Z',
  }

  // Desordenados intencionalmente en la respuesta simulada
  const {click}=setup('/changes?view=calendar&calendar=day&day=2026-10-15',false,[],{},false,[changeLateMidnight, changeEarly, changeMid])
  const calendar=await screen.findByLabelText('Calendario de cambios')
  const stream=within(calendar).getByLabelText('Cronología de cambios')
  const itemsRendered=stream.querySelectorAll('.timeline-item')
  expect(itemsRendered).toHaveLength(3)

  // 1. Primer evento ordenado: 08:00 (changeEarly)
  expect(within(itemsRendered[0] as HTMLElement).getByText('08:00')).toBeInTheDocument()
  expect(within(itemsRendered[0] as HTMLElement).getByText('Fin: 09:30')).toBeInTheDocument()
  expect(within(itemsRendered[0] as HTMLElement).getByText('CAM-0000010')).toBeInTheDocument()
  expect(within(itemsRendered[0] as HTMLElement).getByText('Finalizado')).toBeInTheDocument()

  // 2. Segundo evento ordenado: 12:00 (changeMid)
  expect(within(itemsRendered[1] as HTMLElement).getByText('12:00')).toBeInTheDocument()
  expect(within(itemsRendered[1] as HTMLElement).getByText('Fin: 14:00')).toBeInTheDocument()
  expect(within(itemsRendered[1] as HTMLElement).getByText('CAM-0000011')).toBeInTheDocument()
  expect(within(itemsRendered[1] as HTMLElement).getByText('En ejecución')).toBeInTheDocument()

  // 3. Tercer evento ordenado: 23:00 con cruce de medianoche (changeLateMidnight)
  expect(within(itemsRendered[2] as HTMLElement).getByText('23:00')).toBeInTheDocument()
  expect(within(itemsRendered[2] as HTMLElement).getByText('Fin: 03:00')).toBeInTheDocument()
  expect(within(itemsRendered[2] as HTMLElement).getByText('CAM-0000012')).toBeInTheDocument()
  expect(within(itemsRendered[2] as HTMLElement).getByText('Agendado')).toBeInTheDocument()
  expect(within(itemsRendered[2] as HTMLElement).getByText('15/10 23:00 → 16/10 03:00')).toBeInTheDocument()

  click.mockRestore()
 })
 it.each(['list','calendar'])('comparte filtro por tipo de cambio en %s',async view=>{
  const {mock,click}=setup('/changes?view='+view+'&day=2026-10-15')
  const filter=await screen.findByRole('combobox',{name:'Tipo de cambio'})
  fireEvent.change(filter,{target:{value:'1'}})
  await waitFor(()=>expect(mock.mock.calls.some(([url])=>url.startsWith('/api/changes?')&&url.includes('change_type_id=1'))).toBe(true))
  click.mockRestore()
 })
 it.each([null,2])('permite editar clasificación histórica %s sin perder el tipo inactivo',async typeId=>{
  const {mock,click}=setup('/changes/1/edit',false,[],{change_type_id:typeId,change_type:typeId?{...catalog,id:2,name:'Tipo inactivo',active:false}:null})
  const field=await screen.findByRole('combobox',{name:'Tipo de cambio'})
  expect(field).toBeRequired()
  expect(field).toHaveValue(typeId?'2':'')
  if(typeId)expect(screen.getByRole('option',{name:'Tipo inactivo (Inactivo)'})).toBeEnabled()
  else{
   expect(field).toBeInvalid()
   fireEvent.change(field,{target:{value:'1'}})
  }
  fireEvent.click(screen.getByRole('button',{name:'Guardar cambio'}))
  await waitFor(()=>expect(mock.mock.calls.some(([,init])=>init?.method==='PATCH')).toBe(true))
  const body=JSON.parse(String(mock.mock.calls.find(([,init])=>init?.method==='PATCH')![1]!.body))
  expect(body.change_type_id).toBe(typeId??1)
  click.mockRestore()
 })
 it('ofrece únicamente tipos activos al crear',async()=>{
  const {click}=setup('/changes/new')
  const field=await screen.findByRole('combobox',{name:'Tipo de cambio'})
  expect(field).toBeRequired()
  expect(within(field).queryByRole('option',{name:'Tipo inactivo (Inactivo)'})).not.toBeInTheDocument()
  click.mockRestore()
 })
 it('crea sin ticket interno y deriva departamento en solo lectura',async()=>{
  const {mock,click}=setup('/changes/new')
  const title=await screen.findByRole('textbox',{name:'Título'})
  fireEvent.change(title,{target:{value:'Cambio nuevo'}})
  fireEvent.change(screen.getByLabelText(/^Descripción/),{target:{value:'Operación NOC'}})
  fireEvent.change(screen.getByLabelText(/^Sector/),{target:{value:'1'}})
   fireEvent.change(screen.getByLabelText(/^Tipo de cambio/),{target:{value:'1'}})
  fireEvent.change(screen.getByLabelText(/^Encargado de ejecución/),{target:{value:'1'}})
  expect(screen.getByLabelText('Departamento')).toHaveValue('NOC')
  expect(screen.getByLabelText('Departamento')).toHaveAttribute('readonly')
  fireEvent.click(screen.getByRole('button',{name:'Guardar cambio'}))
  await screen.findByRole('heading',{name:item.reference})
  const body=JSON.parse(String(mock.mock.calls.find(([url,init])=>url==='/api/changes'&&init?.method==='POST')![1]!.body))
  expect(body.internal_ticket_ids).toEqual([])
  expect(body.support_ids).toEqual([])
  expect(body).not.toHaveProperty('department_id')
  expect(body.status).toBe('SCHEDULED')
  click.mockRestore()
 })
 it.each(['/changes/new','/changes/1/edit'])('permite quitar todos los apoyos y guardar desde %s',async path=>{
  const {mock,click}=setup(path,false,[{id:2,name:'Apoyo NOC'}])
  const support=await screen.findByRole('combobox',{name:'Personal de apoyo'})
  expect(support).not.toBeRequired()
  if(path.endsWith('/new')){
   fireEvent.change(screen.getByRole('textbox',{name:'Título'}),{target:{value:'Cambio sin apoyo'}})
   fireEvent.change(screen.getByLabelText(/^Descripción/),{target:{value:'Operación individual'}})
   fireEvent.change(screen.getByLabelText(/^Sector/),{target:{value:'1'}})
   fireEvent.change(screen.getByLabelText(/^Tipo de cambio/),{target:{value:'1'}})
   fireEvent.change(screen.getByLabelText(/^Encargado de ejecución/),{target:{value:'1'}})
   fireEvent.click(support)
   fireEvent.change(support,{target:{value:'Apoyo NOC'}})
   fireEvent.click(within(screen.getByRole('listbox',{name:'Personal de apoyo'})).getByRole('option',{name:'Apoyo NOC'}))
   fireEvent.click(support)
   fireEvent.click(within(screen.getByRole('listbox',{name:'Personal de apoyo'})).getByRole('option',{name:'Segundo apoyo NOC'}))
   expect(screen.getByRole('button',{name:'Quitar Apoyo NOC'})).toBeInTheDocument()
   expect(screen.getByRole('button',{name:'Quitar Segundo apoyo NOC'})).toBeInTheDocument()
  }else expect(screen.getByRole('button',{name:'Quitar Apoyo NOC'})).toBeInTheDocument()
  fireEvent.click(support)
  expect(within(screen.getByRole('listbox',{name:'Personal de apoyo'})).queryByRole('option',{name:person.name})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'Limpiar personal de apoyo'}))
  expect(support).toHaveValue('')
  expect(support).toHaveAttribute('placeholder','Sin personal de apoyo')
  expect(screen.queryByRole('button',{name:/^Quitar .*apoyo NOC/i})).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Limpiar personal de apoyo'})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'Guardar cambio'}))
  await waitFor(()=>expect(mock.mock.calls.some(([url,init])=>url===(path.endsWith('/new')?'/api/changes':'/api/changes/1')&&init?.method===(path.endsWith('/new')?'POST':'PATCH'))).toBe(true))
  const call=mock.mock.calls.find(([url,init])=>url===(path.endsWith('/new')?'/api/changes':'/api/changes/1')&&init?.method===(path.endsWith('/new')?'POST':'PATCH'))!
  expect(JSON.parse(String(call[1]!.body)).support_ids).toEqual([])
  click.mockRestore()
 })
 it.each(['/changes/new','/changes/1/edit'])('usa minutos y conserva segundos históricos sin editar desde %s',async path=>{
  const {mock,click}=setup(path,false,[],{status:'EXECUTING',proposed_start:'2026-10-16T05:00:00Z',proposed_end:'2026-10-16T09:00:00Z',actual_start:'2026-10-16T05:00:50Z',actual_end:null,completion_type_id:null,final_notes:null})
  await screen.findByRole('textbox',{name:'Título'})
  if(path.endsWith('/new')){
   fireEvent.change(screen.getByRole('textbox',{name:'Título'}),{target:{value:'Trabajo nocturno'}})
   fireEvent.change(screen.getByLabelText(/^Descripción/),{target:{value:'Cruce de medianoche'}})
   fireEvent.change(screen.getByLabelText(/^Sector/),{target:{value:'1'}})
   fireEvent.change(screen.getByLabelText(/^Tipo de cambio/),{target:{value:'1'}})
   fireEvent.change(screen.getByLabelText(/^Encargado de ejecución/),{target:{value:'1'}})
   fireEvent.change(screen.getByLabelText(/^Estado/),{target:{value:'EXECUTING'}})
   for(const [label,value] of [['Inicio propuesto','2026-10-15T23:00:00'],['Fin propuesto','2026-10-16T03:00:00'],['Inicio real','2026-10-15T23:00']]){
    fireEvent.change(screen.getByLabelText(new RegExp('^'+label)),{target:{value}})
   }
  }
  await waitFor(()=>expect(screen.getByLabelText(/^Inicio real/)).toHaveValue('2026-10-15T23:00'))
  expect(screen.getByLabelText(/^Inicio real/)).toBeRequired()
  expect(screen.getByLabelText(/^Inicio real/)).toHaveAttribute('step','60')
  expect(screen.getByLabelText(/^Fin real/)).not.toBeRequired()
  expect(screen.getByLabelText(/^Tipo de finalización/)).not.toBeRequired()
  expect(screen.getByLabelText(/^Notas finales/)).not.toBeRequired()
  fireEvent.click(screen.getByRole('button',{name:'Guardar cambio'}))
  const method=path.endsWith('/new')?'POST':'PATCH'
  await waitFor(()=>expect(mock.mock.calls.some(([,init])=>init?.method===method)).toBe(true))
  const body=JSON.parse(String(mock.mock.calls.find(([,init])=>init?.method===method)![1]!.body))
  expect(body).toMatchObject({status:'EXECUTING',proposed_start:path.endsWith('/new')?'2026-10-16T05:00:00.000Z':'2026-10-16T05:00:00Z',proposed_end:path.endsWith('/new')?'2026-10-16T09:00:00.000Z':'2026-10-16T09:00:00Z',actual_start:path.endsWith('/new')?'2026-10-16T05:00:00.000Z':'2026-10-16T05:00:50Z',actual_end:null,completion_type_id:null,final_notes:null})
  click.mockRestore()
 })
 it('edita fechas a minutos sin alterar los segundos de los demás campos históricos',async()=>{
  const originalDates={proposed_start:'2026-10-16T05:00:12Z',proposed_end:'2026-10-16T09:00:23Z',actual_start:'2026-10-16T05:00:50Z',actual_end:'2026-10-16T09:00:42Z'}
  const {mock,click}=setup('/changes/1/edit',false,[],originalDates)
  await screen.findByRole('textbox',{name:'Título'})
  for(const [label,value] of [['Inicio propuesto','2026-10-15T23:00'],['Fin propuesto','2026-10-16T03:00'],['Inicio real','2026-10-15T23:00'],['Fin real','2026-10-16T03:00']]){
   const input=screen.getByLabelText(new RegExp('^'+label)) as HTMLInputElement
   expect(input).toHaveValue(value)
   expect(input).toHaveAttribute('step','60')
   expect(input.validity.stepMismatch).toBe(false)
  }
  fireEvent.change(screen.getByLabelText(/^Fin real/),{target:{value:'2026-10-16T03:10'}})
  fireEvent.click(screen.getByRole('button',{name:'Guardar cambio'}))
  await waitFor(()=>expect(mock.mock.calls.some(([,init])=>init?.method==='PATCH')).toBe(true))
  const body=JSON.parse(String(mock.mock.calls.find(([,init])=>init?.method==='PATCH')![1]!.body))
  expect(body).toMatchObject({...originalDates,actual_end:'2026-10-16T09:10:00.000Z'})
  click.mockRestore()
 })
 it('detalle mantiene seguimiento posterior y descarga individual',async()=>{
  const {mock,click}=setup('/changes/1')
  await screen.findByRole('heading',{name:item.reference})
  fireEvent.click(screen.getByRole('button',{name:'Exportar PDF'}))
  await waitFor(()=>expect(click).toHaveBeenCalled())
  expect(mock.mock.calls.some(([url])=>url.startsWith('/api/changes/1/reports/pdf'))).toBe(true)
  fireEvent.click(screen.getByRole('button',{name:'Nueva intervención'}))
  expect(await screen.findByLabelText(/^Descripción de la actividad/)).toBeInTheDocument()
  expect(screen.queryByText('Visible para cliente')).not.toBeInTheDocument()
  click.mockRestore()
 })
 it('configuración reutiliza la numeración sin consumir la vista previa',async()=>{
  const {mock,click}=setup('/settings')
  fireEvent.click(await screen.findByRole('button',{name:'Numeración de cambios'}))
  const form=await screen.findByRole('form',{name:'Numeración de cambios'})
  await waitFor(()=>expect(within(form).getByLabelText('Prefijo')).toHaveValue('CAM'))
  expect(within(form).getByLabelText('Próximo número')).toHaveValue(1)
  expect(mock.mock.calls.some(([,init])=>init?.method==='POST')).toBe(false)
  click.mockRestore()
 })
 it('catálogo permite administrar elegibilidad',async()=>{
  const {click}=setup('/catalogs')
  fireEvent.click(await screen.findByRole('button',{name:'Tipos de finalización de cambios'}))
  fireEvent.click(await screen.findByRole('button',{name:'Nuevo tipo de finalización'}))
  expect(screen.getByLabelText('Aplica para eficiencia')).toBeInTheDocument()
  click.mockRestore()
 })
})
