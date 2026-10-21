import { fireEvent, render, screen, waitFor, within } from '../test/render'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { SecurityRoles } from './SecurityRoles'
import { Profile } from './Profile'
import { CatalogAdmin } from '../components/CatalogAdmin'
import { SessionsPanel } from '../components/SessionsPanel'
import { Layout } from '../components/Layout'
import { PermissionProvider } from '../auth/permissions'
import { AuthContext, type Identity } from '../auth/context'
import { operationalChoice } from '../lib/responsibles'
import { ResponsibleAccess } from '../components/ResponsibleAccess'

const date = '2026-10-20T12:00:00Z'
const person = { id: 3, name: 'Ingeniería NOC', username: null as string | null, role_id: null as number | null, role_name: null as string | null, account_exists: false, access_granted: false, effective_access: false, password_change_required: false, active: true, operational_selectable: true, position: { name: 'Ingeniero' }, created_at: date }
const roles = [{ id: 1, code: 'SUPERADMIN', name: 'Superadministrador', description: null, editable: false, duplicable: false, permissions: ['roles.manage','tickets.view'], revision: 0 }, { id: 2, code: 'OPERATOR', name: 'Operador', description: null, editable: false, duplicable: true, permissions: ['tickets.view'], revision: 0 }, { id: 3, code: null, name: 'Personalizado', description: null, editable: true, duplicable: true, permissions: ['tickets.view'], revision: 0 }]
const permissions = [{ code: 'tickets.view', module: 'tickets', label: 'Consultar', requires: [], exclusive: false }, { code: 'tickets.edit', module: 'tickets', label: 'Editar', requires: ['tickets.view'], exclusive: false }, { code: 'roles.manage', module: 'roles', label: 'Administrar', requires: [], exclusive: true }]
const identity: Identity = { responsible_id: 1, username: 'admin', name: 'Admin DEV', role: 'SUPERADMIN', role_revision: 0, permissions: [], expires_in: 1800, warning_seconds: 120, operational_access: true, password_change_required: false }
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type':'application/json' } })
function show(node: React.ReactNode) { return render(<MemoryRouter>{node}</MemoryRouter>) }
beforeEach(() => { vi.spyOn(window, 'confirm').mockReturnValue(true) })
afterEach(() => vi.restoreAllMocks())

it('configura acceso sobre el Responsable existente y muestra la contraseña temporal solo una vez', async () => {
  let account = person
  const fetcher = vi.fn((path: string, init?: RequestInit) => {
    if (path.startsWith('/api/security/roles')) return Promise.resolve(json(roles))
    if (path === '/api/responsibles/3/access' && init?.method === 'POST') { account = { ...person, account_exists:true, username:'noc', role_id:2, role_name:'Operador', access_granted:true, effective_access:true, password_change_required:true } as typeof person; return Promise.resolve(json({ ...account, temporary_password:'test-temporary-value' },201)) }
    if (path === '/api/responsibles/3/access') return Promise.resolve(json(account))
    if (path.startsWith('/api/responsibles/access')) return Promise.resolve(json([account]))
    if (path.startsWith('/api/responsibles')) return Promise.resolve(json([person]))
    return Promise.resolve(json([]))
  }); vi.stubGlobal('fetch',fetcher)
  show(<CatalogAdmin kind="responsibles" administrativeAccess />)
  fireEvent.click(await screen.findByRole('button',{name:'Administrar acceso de Ingeniería NOC'}))
  fireEvent.change(await screen.findByLabelText('Nombre de usuario'),{target:{value:'noc'}})
  fireEvent.change(screen.getByLabelText('Rol de seguridad'),{target:{value:'2'}})
  fireEvent.click(screen.getByLabelText('Habilitar acceso a Ticketyn'))
  fireEvent.click(within(screen.getByRole('region',{name:'Administrar acceso'})).getByRole('button',{name:'Configurar acceso'}))
  expect(await screen.findByText('test-temporary-value')).toBeVisible()
  const writes=fetcher.mock.calls.filter(([,init])=>init?.method==='POST')
  expect(writes).toHaveLength(1); expect(writes[0][0]).toBe('/api/responsibles/3/access')
  expect(JSON.parse(String(writes[0][1]?.body))).toEqual({username:'noc',role_id:2,access_granted:true,password:null})
  fireEvent.click(screen.getByRole('button',{name:'Ocultar contraseña temporal'}));expect(screen.queryByText('test-temporary-value')).not.toBeInTheDocument()
})

it('separa los permisos de edición operativa y administración del acceso',async()=>{
  const fetcher=vi.fn((path:string)=>Promise.resolve(json(path.startsWith('/api/responsibles')?[person]:[])));vi.stubGlobal('fetch',fetcher)
  show(<PermissionProvider permissions={['catalogs.responsibles.view','catalogs.responsibles.edit']}><CatalogAdmin kind="responsibles" administrativeAccess /></PermissionProvider>)
  fireEvent.click(await screen.findByRole('button',{name:'Editar Ingeniería NOC'}))
  expect(screen.getByLabelText('Seleccionable en operaciones')).toBeChecked()
  expect(screen.queryByRole('button',{name:/Administrar acceso/})).not.toBeInTheDocument()
  expect(fetcher.mock.calls.some(([path])=>path.includes('/access'))).toBe(false)
})

it('muestra los roles fijos sin acciones prohibidas y crea roles vacíos',async()=>{
  const fetcher=vi.fn((path:string,init?:RequestInit)=>Promise.resolve(json(path==='/api/security/permissions'?permissions:init?.method==='POST'?{...roles[2],id:4,name:'Nuevo',permissions:[]}:roles)));vi.stubGlobal('fetch',fetcher)
  show(<SecurityRoles />)
  expect(await screen.findByRole('button',{name:'Consultar Superadministrador'})).toBeVisible()
  expect(screen.queryByRole('button',{name:'Duplicar Superadministrador'})).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Duplicar Operador'})).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'Nuevo rol personalizado'}))
  fireEvent.change(screen.getByLabelText('Nombre del rol'),{target:{value:'Nuevo'}})
  fireEvent.click(screen.getByRole('button',{name:'Guardar rol'}))
  expect(await screen.findByText('Rol guardado correctamente.')).toBeVisible()
  const writes=fetcher.mock.calls.filter(([,init])=>init?.method==='POST')
  expect(JSON.parse(String(writes[0][1]?.body))).toEqual({name:'Nuevo',description:null})
})

it('edita dependencias recibidas de la API e impide seleccionar facultades exclusivas',async()=>{
  let saved=roles[2]
  const fetcher=vi.fn((path:string,init?:RequestInit)=>{if(init?.method==='PATCH'){saved={...saved,...JSON.parse(String(init.body))};return Promise.resolve(json(saved))}return Promise.resolve(json(path==='/api/security/permissions'?permissions:roles))});vi.stubGlobal('fetch',fetcher)
  show(<SecurityRoles />)
  fireEvent.click(await screen.findByRole('button',{name:'Editar Personalizado'}))
  fireEvent.click(screen.getByText(/^Tickets ·/))
  fireEvent.click(screen.getByRole('checkbox',{name:'Editar'}))
  expect(screen.getByRole('checkbox',{name:'Consultar'})).toBeChecked()
  fireEvent.click(screen.getByText(/^Roles ·/))
  expect(screen.getByRole('checkbox',{name:/Administrar.*Exclusivo/s})).toBeDisabled()
  fireEvent.click(screen.getByRole('button',{name:'Guardar rol'}))
  await screen.findByText('Rol guardado correctamente.')
  expect(saved.permissions).toEqual(['tickets.edit','tickets.view'])
})

it('Mi perfil muestra el Responsable, departamento, su rol y las sesiones sin permitir autoasignación',async()=>{
  vi.stubGlobal('fetch',vi.fn((path:string)=>Promise.resolve(json(path==='/api/auth/profile'?{...person,username:'noc',role_name:'Operador',department:{name:'NOC'}}:[]))))
  show(<Profile />)
  expect(await screen.findByText('Ingeniería NOC')).toBeVisible()
  expect(screen.getByText('NOC')).toBeVisible()
  expect(screen.getByText('Ingeniero')).toBeVisible();expect(screen.getByText('Operador')).toBeVisible()
  expect(screen.getByRole('form',{name:'Cambiar contraseña'})).toBeVisible()
  expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
})

it('Mi perfil muestra Sin asignar cuando no tiene departamento configurado',async()=>{
  vi.stubGlobal('fetch',vi.fn((path:string)=>Promise.resolve(json(path==='/api/auth/profile'?{...person,username:'noc',role_name:'Operador',department:null}:[]))))
  show(<Profile />)
  expect(await screen.findByText('Ingeniería NOC')).toBeVisible()
  expect(screen.getByText('Sin asignar')).toBeVisible()
})

it('dirige el cambio de contraseña propia al perfil para no perder una contraseña temporal al invalidar la sesión',async()=>{
  const fetcher=vi.fn((path:string,_init?:RequestInit)=>Promise.resolve(json(path.startsWith('/api/security/roles')?roles:{...person,id:identity.responsible_id,username:identity.username,account_exists:true,role_id:1,role_name:'Superadministrador'})))
  vi.stubGlobal('fetch',fetcher)
  show(<AuthContext.Provider value={{identity,busy:false,logout:vi.fn(async()=>{}),refresh:vi.fn(async()=>{}),accept:vi.fn()}}><ResponsibleAccess id={identity.responsible_id} onClose={vi.fn()} onSaved={vi.fn()} /></AuthContext.Provider>)
  expect(await screen.findByRole('link',{name:'Mi perfil'})).toHaveAttribute('href','/profile')
  expect(screen.queryByRole('button',{name:'Restablecer contraseña'})).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Contraseña temporal')).not.toBeInTheDocument()
  expect(fetcher.mock.calls.every(([,init])=>!(init as RequestInit | undefined)?.method)).toBe(true)
})

it('identifica la sesión actual y revoca otras sin renovar actividad',async()=>{
  const rows=[{id:'a'.repeat(32),name:'NOC',username:'noc',responsible_id:1,current:true,ip:'127.0.0.1',agent:'Firefox/1 Linux',last_activity:date,expires_in:1800},{id:'b'.repeat(32),name:'NOC',username:'noc',responsible_id:1,current:false,ip:'127.0.0.2',agent:'Chrome/1 Windows',last_activity:date,expires_in:1800}]
  const fetcher=vi.fn((path:string,init?:RequestInit)=>Promise.resolve(json(init?.method==='POST'?{closed:1}:rows)));vi.stubGlobal('fetch',fetcher)
  show(<SessionsPanel />)
  expect(await screen.findByText('Sesión actual')).toBeVisible();expect(screen.getByText('Firefox · Linux')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'Cerrar las demás sesiones'}))
  expect(await screen.findByText('Sesiones cerradas correctamente.')).toBeVisible()
  expect(fetcher.mock.calls.some(([path])=>path==='/api/auth/sessions/close-others')).toBe(true)
  expect(fetcher.mock.calls.some(([path])=>path==='/api/auth/activity')).toBe(false)
})

it('integra el usuario en el encabezado azul y conserva navegación por permisos',async()=>{
  const logout=vi.fn(async()=>{})
  vi.stubGlobal('fetch',vi.fn((path:string)=>Promise.resolve(json(path==='/health'?{status:'ok'}:{version:'0.6.2'}))))
  render(<MemoryRouter><AuthContext.Provider value={{identity,busy:false,logout,accept:vi.fn(),refresh:vi.fn(async()=>{})}}><PermissionProvider permissions={['catalogs.responsibles.view','sessions.manage']}><Routes><Route element={<Layout />}><Route path="*" element={<p>Contenido</p>}/></Route></Routes></PermissionProvider></AuthContext.Provider></MemoryRouter>)
  const header=screen.getByRole('banner')
  expect(within(header).getByText('Admin DEV')).toBeVisible();expect(within(header).getByRole('link',{name:'Mi perfil'})).toHaveAttribute('href','/profile')
  expect(within(header).getByRole('button',{name:'Cerrar sesión'})).toBeVisible()
  const nav=screen.getByRole('navigation');expect(within(nav).getByRole('link',{name:'Responsables'})).toHaveAttribute('href','/responsibles')
  expect(within(nav).getByRole('link',{name:'Sesiones'})).toBeVisible();expect(within(nav).queryByRole('link',{name:'Roles y permisos'})).not.toBeInTheDocument()
  fireEvent.click(within(header).getByRole('button',{name:'Cerrar sesión'}));expect(logout).toHaveBeenCalledTimes(1)
  await waitFor(()=>expect(within(header).getByText('API conectada')).toBeVisible())
})

it('excluye opciones no seleccionables pero conserva las históricas sin depender del acceso',()=>{
  const unavailable={id:1,active:true,operational_selectable:false,access_granted:true}
  expect(operationalChoice(unavailable)).toBe(false)
  expect(operationalChoice(unavailable,[1])).toBe(true)
  const withoutAccess = {...unavailable,id:2,operational_selectable:true,access_granted:false}
  expect(operationalChoice(withoutAccess)).toBe(true)
})
