import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { PermissionProvider } from '../auth/permissions'
import { InstallationOrders } from './InstallationOrders'
afterEach(() => { cleanup(); vi.unstubAllGlobals() })
it('filters inbox without creating an order and hides unauthorized manual registration', async () => {
 const fetcher = vi.fn((path: string, _options?: RequestInit) => Promise.resolve(new Response(JSON.stringify(path.includes('summary') ? {pending:2,reviewing:1,processed:0,discarded:0,to_attend:3} : []), {headers:{'X-Total-Count':'0'}})))
 vi.stubGlobal('fetch', fetcher)
 render(<PermissionProvider permissions={['installation_requests.review']}><MemoryRouter><InstallationOrders /></MemoryRouter></PermissionProvider>)
 expect(await screen.findByText(/recibir un correo no crea una orden/i)).toBeVisible()
 expect(screen.queryByRole('link', {name:'Registrar orden manual'})).not.toBeInTheDocument()
 fireEvent.click(screen.getByLabelText('Con borrador'))
 await waitFor(() => expect(fetcher.mock.calls.some(([path]) => path.includes('has_draft=true'))).toBe(true))
 expect(fetcher.mock.calls.every(([, options]) => !options?.method)).toBe(true)
})

it('shows the modality of each order and filters by it', async () => {
 const rows=[{id:1,reference:'OI-000001',order_type:'NORMAL',customer:{name:'Cliente'},technical:{service_type:{name:'Internet'}},requested_at:'2026-10-28T12:00:00Z',author:{name:'Admin'},circuit:null},{id:2,reference:'OI-000002',order_type:'EXTRAORDINARY',customer:{name:'Cliente'},technical:{service_type:null},requested_at:'2026-10-28T12:00:00Z',author:{name:'Admin'},circuit:null}]
 const fetcher = vi.fn((path: string, _options?: RequestInit) => Promise.resolve(new Response(JSON.stringify(path.includes('customers')?[]:rows), {headers:{'X-Total-Count':'2'}})))
 vi.stubGlobal('fetch', fetcher)
 render(<PermissionProvider permissions={['installation_orders.view']}><MemoryRouter><InstallationOrders /></MemoryRouter></PermissionProvider>)
 expect(await screen.findByText('Extraordinaria',{selector:'span'})).toBeVisible();expect(screen.getByText('Normal',{selector:'span'})).toBeVisible()
 fireEvent.change(screen.getByLabelText('Tipo de orden'),{target:{value:'EXTRAORDINARY'}})
 await waitFor(() => expect(fetcher.mock.calls.some(([path]) => path.includes('order_type=EXTRAORDINARY'))).toBe(true))
})
