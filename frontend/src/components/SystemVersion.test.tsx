import { render, screen, waitFor } from '../test/render'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { Layout } from './Layout'
import { jsonResponse } from '../test/fixtures'

describe('Versión del frontend y contraste con la API',()=>{
  it.each(['0.4.2','8.2.1'])('no permite que la API %s cambie la identificación del bundle',async(version)=>{
    vi.stubGlobal('fetch',vi.fn((path:string)=>Promise.resolve(jsonResponse(path==='/health'?{status:'ok'}:{version}))))
    render(<MemoryRouter><Layout /></MemoryRouter>)
    expect(await screen.findByText('API conectada')).toBeInTheDocument()
    const badge = screen.getByLabelText('Versión de Ticketyn')
    expect(badge).toHaveTextContent(`Ticketyn v${__TICKETYN_FRONTEND_VERSION__}`)
    expect(badge).toHaveAttribute('title', expect.stringContaining(`La API informa ${version}`))
    expect(screen.queryByText(`Ticketyn v${version}`)).not.toBeInTheDocument()
    expect(badge).toHaveClass('header-version-badge')
    expect(badge.parentElement).toContainElement(screen.getByRole('status'))
  })
  it('confirma coincidencia cuando el endpoint informa la misma versión', async () => {
    const fetcher = vi.fn((path: string) => Promise.resolve(jsonResponse(path === '/health' ? {status: 'ok'} : {version: __TICKETYN_FRONTEND_VERSION__})))
    vi.stubGlobal('fetch', fetcher)
    render(<MemoryRouter><Layout /></MemoryRouter>)
    await waitFor(() => expect(screen.getByLabelText('Versión de Ticketyn')).toHaveAttribute('title', expect.stringContaining('Coincide con la versión informada por la API.')))
    expect(fetcher.mock.calls.filter(([path]) => path === '/api/system/version')).toHaveLength(1)
    expect(screen.getAllByText(`Ticketyn v${__TICKETYN_FRONTEND_VERSION__}`)).toHaveLength(1)
  })
  it.each([undefined, null, 'invalid', '1.2.3\n'])('conserva conectividad si la versión no es válida (%s)',async(version)=>{
    vi.stubGlobal('fetch',vi.fn((path:string)=>Promise.resolve(jsonResponse(path==='/health'?{status:'ok'}:{version}))))
    render(<MemoryRouter><Layout /></MemoryRouter>)
    expect(await screen.findByText('API conectada')).toBeInTheDocument()
    expect(screen.getByLabelText('Versión de Ticketyn')).toHaveTextContent(`Ticketyn v${__TICKETYN_FRONTEND_VERSION__}`)
    expect(screen.getByLabelText('Versión de Ticketyn')).toHaveAttribute('title', expect.stringContaining('La versión de la API no está disponible.'))
  })
  it('backend no disponible conserva la identificación conocida del frontend',async()=>{
    vi.stubGlobal('fetch',vi.fn(()=>Promise.reject(new Error('offline'))))
    render(<MemoryRouter><Layout /></MemoryRouter>)
    expect(await screen.findByText('API no disponible')).toBeInTheDocument()
    expect(screen.getByLabelText('Versión de Ticketyn')).toHaveTextContent(`Ticketyn v${__TICKETYN_FRONTEND_VERSION__}`)
  })
  it.each([403, 404, 500])('una respuesta HTTP %s de versión no cambia la conectividad ni el bundle', async (status) => {
    vi.stubGlobal('fetch', vi.fn((path: string) => Promise.resolve(path === '/health' ? jsonResponse({status: 'ok'}) : jsonResponse({detail: 'No disponible'}, status))))
    render(<MemoryRouter><Layout /></MemoryRouter>)
    expect(await screen.findByText('API conectada')).toBeInTheDocument()
    expect(screen.getByLabelText('Versión de Ticketyn')).toHaveTextContent(`Ticketyn v${__TICKETYN_FRONTEND_VERSION__}`)
    expect(screen.getByLabelText('Versión de Ticketyn')).toHaveAttribute('title', expect.stringContaining('La versión de la API no está disponible.'))
  })
})
