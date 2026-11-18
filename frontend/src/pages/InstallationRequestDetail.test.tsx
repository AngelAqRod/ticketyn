import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { PermissionProvider } from '../auth/permissions'
import { InstallationRequestDetail } from './InstallationRequestDetail'
const request={id:2,state:'PENDING',sender:'sender@example.test',subject:'Instalar servicio',body:'<img src="https://evil.test/pixel">',received_at:'2026-10-28T12:00:00Z',message_id:'original@test',reviewer:null,order_id:null,draft:null,documents:[],events:[]}
function show(permissions=['installation_requests.review']){return render(<PermissionProvider permissions={permissions}><MemoryRouter initialEntries={['/installation-requests/2']}><Routes><Route path="/installation-requests/:id" element={<InstallationRequestDetail/>}/></Routes></MemoryRouter></PermissionProvider>)}
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
it('saves incomplete versioned draft and never renders active email HTML',async()=>{
 const fetcher=vi.fn((path:string,options?:RequestInit)=>Promise.resolve(new Response(JSON.stringify(path.includes('/draft')?{...request,draft:{data:{notes:''},version:1}}:path.includes('customers')?[]:request))))
 vi.stubGlobal('fetch',fetcher);show()
 expect(await screen.findByText(request.body)).toBeVisible();expect(document.querySelector('img')).toBeNull()
 expect(screen.queryByRole('button',{name:'Registrar orden'})).not.toBeInTheDocument()
 fireEvent.click(screen.getByRole('button',{name:'Guardar borrador'}))
 await screen.findByText('Borrador guardado.')
 const draftCall=fetcher.mock.calls.find(([path])=>path.includes('/draft'))!
 expect(draftCall[1]?.method).toBe('PUT');expect(JSON.parse(String(draftCall[1]?.body))).toMatchObject({version:0,data:{order_type:'NORMAL',notes:null}})
})
it('preserves typed fields after a draft version conflict',async()=>{
 vi.stubGlobal('fetch',vi.fn((path:string)=>Promise.resolve(new Response(JSON.stringify(path.includes('/draft')?{detail:'Otro usuario modificó el borrador.'}:path.includes('customers')?[]:request),{status:path.includes('/draft')?409:200}))))
 show();await screen.findByText(request.subject)
 fireEvent.change(screen.getByLabelText('Observaciones'),{target:{value:'Fibra pendiente'}})
 fireEvent.click(screen.getByRole('button',{name:'Guardar borrador'}))
 await screen.findByText('Otro usuario modificó el borrador.')
 expect(screen.getByLabelText('Observaciones')).toHaveValue('Fibra pendiente')
 expect(screen.getByRole('button',{name:'Guardar borrador'})).toBeDisabled()
})
it('requires a reason before discarding a request',async()=>{
 const fetcher=vi.fn((path:string)=>Promise.resolve(new Response(JSON.stringify(path.includes('customers')?[]:request))))
 vi.stubGlobal('fetch',fetcher);show(['installation_requests.review','installation_requests.discard']);await screen.findByText(request.subject)
 fireEvent.click(screen.getByRole('button',{name:'Descartar solicitud'}));fireEvent.click(screen.getByRole('button',{name:'Confirmar descarte'}))
 await screen.findByText('Indica el motivo del descarte.')
 expect(fetcher.mock.calls.some(([path])=>path.includes('/discard'))).toBe(false)
})
it('keeps typed data mounted when switching mobile capture panes',async()=>{
 vi.stubGlobal('fetch',vi.fn((path:string)=>Promise.resolve(new Response(JSON.stringify(path.includes('customers')?[]:request)))));show();await screen.findByText(request.subject)
 fireEvent.change(screen.getByLabelText('Observaciones'),{target:{value:'Datos sin guardar'}})
 fireEvent.click(screen.getByRole('button',{name:'Documento'}));fireEvent.click(screen.getByRole('button',{name:'Formulario'}))
 expect(screen.getByLabelText('Observaciones')).toHaveValue('Datos sin guardar')
})
