import { fireEvent, render, screen, waitFor, within } from '../test/render'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { Reports } from './Reports'
import { jsonResponse } from '../test/fixtures'
vi.mock('../components/ReportCharts',()=>({TrendChart:()=> <div aria-label="Evolución"/>,ActivityChart:()=> <div/>,DistributionChart:()=> <div/>,RankingChart:()=> <div/>}))
const summary={period:{from_at:null,to_exclusive:null,timezone:'America/Guatemala',granularity:'day'},generated_at:'2026-10-15T14:00:00Z',sector:null,node:null,responsible:null,kpis:{started:2,closed:1,average_duration_seconds:7200,total_duration_seconds:7200},open_tickets:1,closed_tickets:1,related_tickets:5,with_related:1,without_related:1,trend:[],activity:[],hours:[],weekdays:[],sectors:[],customers:[],circuits:[],incident_types:[],nodes:[],responsibles:[],departments:[],department_durations:[],sector_durations:[],providers:[{id:0,label:'Ninguno',count:1},{id:7,label:'Transporte histórico',count:1}]}
function setup(query='',empty=false){
  vi.stubGlobal('URL',class extends URL {static createObjectURL=vi.fn(()=> 'blob:report');static revokeObjectURL=vi.fn()})
  const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{})
  const mock=vi.fn((url:string)=>{
    if(url.includes('/export/'))return Promise.resolve(new Response(new Blob(['report'])))
    if(url.startsWith('/api/reports/internal-tickets/summary'))return Promise.resolve(jsonResponse(empty?{...summary,kpis:{started:0,closed:0,average_duration_seconds:null,total_duration_seconds:0},providers:[]}:summary))
    if(url.startsWith('/api/providers'))return Promise.resolve(jsonResponse([{id:7,name:'Transporte histórico',active:false,created_at:'2026-01-01T00:00:00Z'}]))
    return Promise.resolve(jsonResponse([]))
  });vi.stubGlobal('fetch',mock)
  render(<MemoryRouter initialEntries={['/reports?scope=internal&period=all'+query]}><Reports/></MemoryRouter>)
  return {mock,click}
}
describe('reportería interna integrada',()=>{
  it('reutiliza reportes y muestra proveedores y relaciones sin clientes ni circuitos',async()=>{
    const {mock,click}=setup()
    await screen.findByRole('heading',{name:'Reportería de tickets internos'})
    await screen.findByText('Tickets de clientes vinculados')
    const strips=document.querySelectorAll('.metric-strip')
    expect(strips).toHaveLength(1)
    expect(strips[0]).toHaveAttribute('data-count','6')
    expect(Array.from(strips[0].querySelectorAll('.metric-item')).map(el=>el.getAttribute('data-color'))).toEqual(['lilac','mint','ice','indigo','amber','cyan'])
    expect(strips[0]).toHaveAttribute('data-layout','internal-summary')
    expect(Array.from(strips[0].querySelectorAll('dt')).map(el=>el.textContent)).toEqual(['Incidencias iniciadas','Incidencias cerradas','Duración promedio','Duración acumulada','Tickets de clientes vinculados','Incidencias con tickets vinculados'])
    expect(within(strips[0] as HTMLElement).getByText('5')).toBeInTheDocument()
    for(const label of ['Abiertos (iniciados)','Cerrados (iniciados)','Incidencias sin tickets vinculados']) expect(screen.queryByText(label)).not.toBeInTheDocument()
    expect(screen.getByText(/No representan afectaciones confirmadas/)).toBeInTheDocument()
    expect(screen.getByRole('navigation',{name:'Ámbito de reportería'})).toBeInTheDocument()
    expect(screen.getByText('Incidencias internas por proveedor')).toBeInTheDocument()
    expect(screen.queryByText('Clientes con más incidencias')).not.toBeInTheDocument()
    expect(screen.queryByText('Circuitos con más incidencias')).not.toBeInTheDocument()
    expect(mock.mock.calls.some(([url])=>url.startsWith('/api/tickets?'))).toBe(false)
    click.mockRestore()
  })
  it.each(['none','7'])('aplica proveedor %s a resumen, detalle y ambas exportaciones',async provider=>{
    const {mock,click}=setup('&provider_id='+provider+'&status=OPEN&department_id=2&incident_type_id=3')
    await screen.findByText('Tickets de clientes vinculados')
    for(const name of ['Exportar PDF','Exportar Excel']){
      fireEvent.click(screen.getByRole('button',{name}))
      await waitFor(()=>expect(screen.getByRole('button',{name})).toBeEnabled())
    }
    await waitFor(()=>expect(click).toHaveBeenCalledTimes(2))
    const paths=mock.mock.calls.filter(([url])=>url.startsWith('/api/reports/internal-tickets/')||url.startsWith('/api/internal-tickets?'))
    expect(paths.length).toBeGreaterThanOrEqual(4)
    for(const [url] of paths){const params=new URL(url,'http://local').searchParams;expect(params.get('status')).toBe('OPEN');expect(params.get('department_id')).toBe('2');expect(params.get('incident_type_id')).toBe('3');expect(params.get(provider==='none'?'without_provider':'provider_id')).toBe(provider==='none'?'true':'7')}
    click.mockRestore()
  })
  it('admite resultados vacíos y solicita una selección en las pestañas individuales',async()=>{
    const {mock,click}=setup('',true)
    await screen.findByText('No hay incidencias iniciadas en este período.')
    fireEvent.click(screen.getByRole('button',{name:'Por nodo'}))
    expect(await screen.findByText('Selecciona un nodo para consultar el reporte.')).toBeInTheDocument()
    expect(screen.getByRole('button',{name:'Exportar PDF'})).toBeDisabled()
    expect(mock.mock.calls.filter(([url])=>url.includes('/summary')).length).toBe(1)
    click.mockRestore()
  })
})
