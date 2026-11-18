import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { PermissionProvider } from '../auth/permissions'
import { InstallationOrderDetail } from './InstallationOrderDetail'
import { installationDocumentBlob, uploadInstallationDocument, saveInstallationDraft } from '../api/installationOrders'
import { setSessionToken, sessionToken } from '../auth/session'
import { InstallationDocuments } from '../components/installation/Documents'
const order={id:3,reference:'OI-000003',customer_id:4,customer:{id:4,name:'Cliente'},author:{id:1,name:'Admin'},order_type:'EXTRAORDINARY',description:'Instalación especial',technical:{service_type:{id:1,name:'Fibra'},node:{id:2,name:'Nodo 2'},sector:null,device:null,port:null,cpe:null},requested_at:'2026-10-28T12:00:00Z',source_request_id:null,circuit:null,documents:[],events:[]}
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();sessionStorage.clear()})
it('shows an extraordinary order with its catalog references and without circuit controls',async()=>{
 vi.stubGlobal('fetch',vi.fn(()=>Promise.resolve(new Response(JSON.stringify(order)))))
 render(<PermissionProvider permissions={['installation_orders.view']}><MemoryRouter initialEntries={['/installation-orders/3']}><Routes><Route path="/installation-orders/:id" element={<InstallationOrderDetail/>}/></Routes></MemoryRouter></PermissionProvider>)
 expect(await screen.findByText('OI-000003')).toBeVisible();expect(screen.getByText('Orden extraordinaria')).toBeVisible();expect(screen.getByText('Instalación especial')).toBeVisible()
 expect(screen.getByText('Fibra')).toBeVisible();expect(screen.getByText('Nodo 2')).toBeVisible();expect(screen.getAllByText('No disponible').length).toBe(4);expect(screen.queryByText('Circuito asociado')).not.toBeInTheDocument()
 expect(screen.queryByRole('button',{name:'Crear circuito'})).not.toBeInTheDocument();expect(screen.queryByRole('link',{name:'Editar orden'})).not.toBeInTheDocument()
})
it('fetches previews with authorization and revokes their blob URL on unmount',async()=>{
 const create=vi.fn(()=> 'blob:private-document'),revoke=vi.fn();vi.stubGlobal('URL',class extends URL {static createObjectURL=create;static revokeObjectURL=revoke})
 sessionStorage.setItem('ticketyn.session','opaque-test');const fetcher=vi.fn((_path:string,_options?:RequestInit)=>Promise.resolve(new Response('valid image')));vi.stubGlobal('fetch',fetcher)
 const mounted=render(<InstallationDocuments documents={[{id:4,original_name:'original.png',media_type:'image/png',size:20,checksum:'abc',created_at:''}]}/>)
 await screen.findByAltText('Documento original: original.png')
 expect(fetcher.mock.calls[0][0]).toBe('/api/installation-documents/4/content')
 expect(new Headers(fetcher.mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer opaque-test')
 expect(screen.getByAltText('Documento original: original.png')).toHaveAttribute('src','blob:private-document')
 mounted.unmount();expect(revoke).toHaveBeenCalledWith('blob:private-document')
})
it('does not preview office documents or load their content automatically',async()=>{
 const fetcher=vi.fn();vi.stubGlobal('fetch',fetcher)
 render(<InstallationDocuments documents={[{id:5,original_name:'original.docx',media_type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',size:20,checksum:'abc',created_at:''}]}/>)
 expect(await screen.findByText('Este formato solo está disponible mediante descarga autorizada.')).toBeVisible();expect(fetcher).not.toHaveBeenCalled()
})

it.each(['preview','upload','draft'])('expires the session on unauthorized %s without putting tokens in a URL',async(kind)=>{
 setSessionToken('expired-token')
 const fetcher=vi.fn((_path:string,_options?:RequestInit)=>Promise.resolve(new Response(JSON.stringify({detail:'Sesión expirada'}),{status:401})))
 vi.stubGlobal('fetch',fetcher)
 const action=kind==='preview'?installationDocumentBlob(4):kind==='upload'?uploadInstallationDocument(3,new File(['data'],'file.pdf')):saveInstallationDraft(2,{},0)
 await expect(action).rejects.toMatchObject({status:401})
 expect(sessionToken()).toBeNull()
 expect(fetcher.mock.calls[0][0]).not.toContain('expired-token')
 expect(new Headers(fetcher.mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer expired-token')
})

it('shows a normal order with the technical data owned by its circuit, read-only',async()=>{
 const normal={...order,order_type:'NORMAL',description:null,circuit:{id:7,circuit_code:'CIR-7'},technical:{service_type:{id:1,name:'Internet'},node:{id:2,name:'Nodo 2'},sector:{id:3,name:'Zona 1'},device:{id:4,name:'CORE A'},port:{id:5,name:'sfp+1'},cpe:null},circuit_location:{address:'Zona 1',latitude:'14.634915',longitude:'-90.506882',additional_notes:'Acceso por el portón'}}
 vi.stubGlobal('fetch',vi.fn(()=>Promise.resolve(new Response(JSON.stringify(normal)))))
 render(<PermissionProvider permissions={['installation_orders.view','installation_orders.link','installation_orders.edit']}><MemoryRouter initialEntries={['/installation-orders/3']}><Routes><Route path="/installation-orders/:id" element={<InstallationOrderDetail/>}/></Routes></MemoryRouter></PermissionProvider>)
 expect(await screen.findByText('Orden normal')).toBeVisible()
 for(const text of ['Internet','Nodo 2','CORE A','sfp+1','No disponible','14.634915, -90.506882','Acceso por el portón'])expect(screen.getByText(text)).toBeVisible()
 expect(screen.getAllByText('Zona 1').length).toBe(2);expect(screen.getByRole('link',{name:'Ver en Google Maps'})).toBeVisible()
 expect(screen.getByText('CIR-7')).toBeVisible();expect(screen.queryByRole('button',{name:'Desvincular circuito'})).not.toBeInTheDocument();expect(screen.queryByRole('button',{name:'Crear circuito'})).not.toBeInTheDocument()
})

function showOrder(data:unknown){
 vi.stubGlobal('fetch',vi.fn(()=>Promise.resolve(new Response(JSON.stringify(data)))))
 render(<PermissionProvider permissions={['installation_orders.view']}><MemoryRouter initialEntries={['/installation-orders/3']}><Routes><Route path="/installation-orders/:id" element={<InstallationOrderDetail/>}/></Routes></MemoryRouter></PermissionProvider>)
}
const normalOrder={...order,order_type:'NORMAL',description:null,circuit:{id:7,circuit_code:'CIR-7'},technical:{service_type:null,node:null,sector:null,device:null,port:null,cpe:null}}
it('opens the circuit location in Google Maps from a normal order, in a new tab and safely',async()=>{
 showOrder({...normalOrder,circuit_location:{address:null,latitude:'14.634915',longitude:'-90.506882',additional_notes:null}})
 const link=await screen.findByRole('link',{name:'Ver en Google Maps'})
 expect(link).toHaveAttribute('href','https://www.google.com/maps/search/?api=1&query=14.634915%2C-90.506882');expect(link).toHaveAttribute('target','_blank');expect(link).toHaveAttribute('rel','noopener noreferrer')
})
it.each([[{address:'Zona 1',latitude:null,longitude:null,additional_notes:null}],[{address:null,latitude:'14.5',longitude:null,additional_notes:null}]])('shows no map action when the circuit has no complete GPS point',async(location)=>{
 showOrder({...normalOrder,circuit_location:location})
 await screen.findByText('Orden normal');expect(screen.queryByRole('link',{name:'Ver en Google Maps'})).not.toBeInTheDocument()
})
it('keeps extraordinary orders unchanged: no location section and no map action',async()=>{
 showOrder({...order,order_type:'EXTRAORDINARY',circuit_location:null})
 await screen.findByText('Orden extraordinaria');expect(screen.queryByRole('link',{name:'Ver en Google Maps'})).not.toBeInTheDocument();expect(screen.queryByText('Ubicación del circuito')).not.toBeInTheDocument()
})
