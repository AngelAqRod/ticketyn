import { render, screen, fireEvent, waitFor, act } from '../test/render'
import { MemoryRouter, Routes, Route, Link } from 'react-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { PermissionProvider, Can, usePermissions, routeAllowed } from './permissions'
import { AuthGate } from './AuthGate'
import { setSessionToken } from './session'
import { Layout } from '../components/Layout'
import { Catalogs } from '../pages/Catalogs'
import { Reports } from '../pages/Reports'
import { FmsReports } from '../pages/FmsReports'
import { MailNotifications } from '../pages/MailNotifications'
import { ChangeTicketLinks } from '../components/ChangeShared'
import { TicketEscalations } from '../components/TicketEscalations'
import { CircuitActions } from '../components/CircuitActions'
import type { Circuit } from '../types/catalog'

const json=(value:unknown)=>new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}})
beforeEach(()=>{sessionStorage.clear();localStorage.clear()})
afterEach(()=>{vi.useRealTimers();vi.unstubAllGlobals();sessionStorage.clear()})
function show(ui:React.ReactNode, permissions:string[], path='/') {
 return render(<PermissionProvider permissions={permissions}><MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter></PermissionProvider>)
}
it('deniega capacidades ausentes y mantiene independientes consulta y exportación',()=>{
 function Probe(){const access=usePermissions();return <><Can permission="changes.edit">Editar ventana</Can><Can permission="reports.changes.export">Exportar reporte</Can><output>{String(routeAllowed('/catalogs',access))}</output></>}
 show(<Probe/>,['reports.changes.export'])
 expect(screen.queryByText('Editar ventana')).not.toBeInTheDocument()
 expect(screen.getByText('Exportar reporte')).toBeVisible()
 expect(screen.getByText('false')).toBeVisible()
})
it('muestra operaciones y reportería sin Administración para un operador',async()=>{
 vi.stubGlobal('fetch',vi.fn((_path:string)=>Promise.resolve(json({version:'0.6.2'}))))
 show(<Layout/>,['dashboard.view','tickets.view','changes.view','reports.changes.view'])
 expect(screen.getByRole('link',{name:/Control de cambios/})).toBeInTheDocument()
 expect(screen.queryByRole('link',{name:/Catálogos/})).not.toBeInTheDocument()
 expect(screen.queryByRole('link',{name:/Configuración de correo/})).not.toBeInTheDocument()
 await screen.findByText('Ticketyn v0.6.2')
})
it('solo lectura CAM conserva relaciones y oculta todas las mutaciones de vínculos',()=>{
 show(<ChangeTicketLinks items={[{id:4,reference:'INT-4',title:'Mantenimiento'}]} onChange={vi.fn()}/>,['changes.view'])
 expect(screen.getByText('INT-4 — Mantenimiento')).toBeVisible()
 expect(screen.queryByRole('link')).not.toBeInTheDocument()
 expect(screen.queryByRole('button',{name:/Vincular|Desvincular/})).not.toBeInTheDocument()
})
it('un permiso específico CAM habilita vínculos sin Administración ni ficha interna',()=>{
 show(<ChangeTicketLinks items={[]} onChange={vi.fn()}/>,['changes.view','changes.link'])
 expect(screen.getByRole('button',{name:'Vincular ticket interno'})).toBeEnabled()
})
it('un catálogo autorizado no carga ni muestra el primer catálogo no autorizado',async()=>{
 const fetcher=vi.fn((_path:string)=>Promise.resolve(json([])));vi.stubGlobal('fetch',fetcher)
 show(<Catalogs/>,['catalogs.providers.view'],'/catalogs')
 expect(await screen.findByText('No hay proveedores registrados.')).toBeVisible()
 expect(screen.getByRole('button',{name:'Proveedores'})).toBeVisible()
 expect(screen.queryByRole('button',{name:'Sectores'})).not.toBeInTheDocument()
 expect(screen.queryByRole('button',{name:/Nuevo proveedor/})).not.toBeInTheDocument()
 expect(fetcher.mock.calls.every(([path])=>String(path).startsWith('/api/providers'))).toBe(true)
})
it('un rol con exportación CAM puede entrar a reportería sin consultar resúmenes',async()=>{
 const fetcher=vi.fn((_path:string)=>Promise.resolve(json([])));vi.stubGlobal('fetch',fetcher)
 show(<Reports/>,['reports.changes.export'],'/reports')
 expect(await screen.findByRole('heading',{name:'Reportería de Control de cambios'})).toBeVisible()
 expect(await screen.findByRole('button',{name:'Exportar Excel'})).toBeEnabled()
 expect(screen.queryByRole('link',{name:'Tickets'})).not.toBeInTheDocument()
 expect(fetcher.mock.calls.some(([path])=>String(path).includes('/summary'))).toBe(false)
})
it('exportación FMS independiente no consulta resumen ni detalles',async()=>{
 const fetcher=vi.fn((_path:string)=>Promise.resolve(json([])));vi.stubGlobal('fetch',fetcher)
 show(<FmsReports kind="activations"/>,['reports.activations.export'],'/activation-reports')
 expect(await screen.findByRole('button',{name:'Exportar PDF'})).toBeEnabled()
 await waitFor(()=>expect(fetcher).toHaveBeenCalled())
 expect(fetcher.mock.calls.some(([path])=>String(path).includes('/fms/reports/'))).toBe(false)
})
it('SMTP de consulta no muestra guardado, prueba ni consulta eventos no autorizados',async()=>{
 const smtp={host:'localhost',port:587,security:'STARTTLS',auth_method:'NONE',provider:null,username:'',sender_address:'noc@example.com',sender_name:'NOC',allow_unencrypted:false,password_configured:false,configured:true}
 const fetcher=vi.fn((_path:string)=>Promise.resolve(json(smtp)));vi.stubGlobal('fetch',fetcher)
 show(<MailNotifications/>,['mail.transport.view'],'/mail-notifications')
 expect(await screen.findByLabelText(/^Servidor SMTP/)).toBeDisabled()
 expect(screen.queryByRole('button',{name:'Guardar configuración SMTP'})).not.toBeInTheDocument()
 expect(screen.queryByRole('button',{name:'Enviar correo de prueba'})).not.toBeInTheDocument()
 expect(fetcher.mock.calls.every(([path])=>path==='/api/mail-notifications/smtp')).toBe(true)
})
it('acciones de circuito separan edición, eliminación y cambio de estado',()=>{
 const circuit={id:4,circuit_code:'CIR-4',active:true} as Circuit
 show(<CircuitActions circuit={circuit} onEdit={vi.fn()} onDelete={vi.fn()} onToggle={vi.fn()}/>,['circuits.edit'])
 expect(screen.getByRole('button',{name:'Editar CIR-4'})).toBeVisible()
 expect(screen.queryByRole('button',{name:'Desactivar CIR-4'})).not.toBeInTheDocument()
 expect(screen.queryByRole('button',{name:'Eliminar CIR-4'})).not.toBeInTheDocument()
})
it('relee permisos por foco y navegación sin enviar actividad automática',async()=>{
 setSessionToken('opaque-test-token')
 let permissions=['tickets.view','tickets.edit','changes.view']
 const fetcher=vi.fn((_path:string)=>Promise.resolve(json({responsible_id:7,name:'Operador',username:'noc',role:null,role_id:8,role_revision:0,operational_access:true,password_change_required:false,permissions,expires_in:1800,warning_seconds:120})))
 vi.stubGlobal('fetch',fetcher)
 render(<MemoryRouter initialEntries={['/tickets']}><AuthGate><Routes><Route path="/tickets" element={<><Can permission="tickets.edit"><button>Editar ticket</button></Can><Link to="/changes">Cambios</Link></>}/><Route path="/changes" element={<h1>Ventanas</h1>}/></Routes></AuthGate></MemoryRouter>)
 expect(await screen.findByRole('button',{name:'Editar ticket'})).toBeVisible()
 permissions=['tickets.view','changes.view']
 fireEvent(window,new Event('focus'))
 await waitFor(()=>expect(screen.queryByRole('button',{name:'Editar ticket'})).not.toBeInTheDocument())
 expect(screen.getByText('Tus permisos han sido actualizados.')).toBeVisible()
 fireEvent.click(screen.getByRole('link',{name:'Cambios'}))
 expect(await screen.findByRole('heading',{name:'Ventanas'})).toBeVisible()
 expect(fetcher.mock.calls.every(([path])=>path==='/api/auth/me')).toBe(true)
})

it('un auditor conserva el historial de escalamientos sin crear, editar ni finalizar',async()=>{
 const entry={id:4,status:'ACTIVE',requester:null,recipient:null,reason:{id:1,name:'Apoyo técnico'},started_at:'2026-10-20T10:00:00Z',created_at:'2026-10-20T10:00:00Z',updated_at:'2026-10-20T10:00:00Z',description:'Intervención histórica'}
 vi.stubGlobal('fetch',vi.fn(()=>Promise.resolve(json([entry]))))
 show(<TicketEscalations ticketId={1}/>,['tickets.view'])
 expect(await screen.findByText('Intervención histórica')).toBeVisible()
 expect(screen.getByRole('button',{name:'Ver intervenciones'})).toBeVisible()
 expect(screen.queryByRole('button',{name:'Nuevo escalamiento'})).not.toBeInTheDocument()
 expect(screen.queryByRole('button',{name:'Editar escalamiento'})).not.toBeInTheDocument()
 expect(screen.queryByRole('button',{name:'Finalizar escalamiento'})).not.toBeInTheDocument()
})

it('una ruta directa no autorizada muestra acceso denegado sin montar el módulo',async()=>{
 setSessionToken('opaque-test-token')
 vi.stubGlobal('fetch',vi.fn(()=>Promise.resolve(json({responsible_id:7,name:'Operador',username:'noc',role:'OPERATOR',role_revision:0,operational_access:true,password_change_required:false,permissions:['tickets.view'],expires_in:1800,warning_seconds:120}))))
 const mount=vi.fn()
 function Module(){mount();return <h1>Administración restringida</h1>}
 render(<MemoryRouter initialEntries={['/mail-notifications']}><AuthGate><Module/></AuthGate></MemoryRouter>)
 expect(await screen.findByRole('heading',{name:'Acceso denegado'})).toBeVisible()
 expect(mount).not.toHaveBeenCalled()
 expect(screen.getByRole('button',{name:'Ir a un módulo autorizado'})).toBeEnabled()
})

it('redirige a otro módulo si se retira el permiso del módulo actual',async()=>{
 setSessionToken('opaque-test-token')
 let permissions=['tickets.view','changes.view']
 const fetcher=vi.fn((_path:string)=>Promise.resolve(json({responsible_id:7,name:'Operador',username:'noc',role:null,role_revision:0,operational_access:true,password_change_required:false,permissions,expires_in:1800,warning_seconds:120})))
 vi.stubGlobal('fetch',fetcher)
 render(<MemoryRouter initialEntries={['/tickets']}><AuthGate><Routes><Route path="/tickets" element={<h1>Tickets autorizados</h1>}/><Route path="/changes" element={<h1>Ventanas autorizadas</h1>}/></Routes></AuthGate></MemoryRouter>)
 expect(await screen.findByRole('heading',{name:'Tickets autorizados'})).toBeVisible()
 permissions=['changes.view']
 fireEvent(window,new Event('focus'))
 expect(await screen.findByRole('heading',{name:'Ventanas autorizadas'})).toBeVisible()
 expect(screen.queryByRole('heading',{name:'Tickets autorizados'})).not.toBeInTheDocument()
 expect(fetcher.mock.calls.every(([path])=>path==='/api/auth/me')).toBe(true)
})
