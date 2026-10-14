import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { Layout } from './Layout'
import { jsonResponse } from '../test/fixtures'

describe('Versión desde el backend',()=>{
  it.each(['0.4.2','8.2.1'])('muestra la versión real %s independiente del bundle',async(version)=>{
    vi.stubGlobal('fetch',vi.fn((path:string)=>Promise.resolve(jsonResponse(path==='/health'?{status:'ok'}:{version}))))
    render(<MemoryRouter><Layout /></MemoryRouter>)
    expect(await screen.findByText(`Ticketyn v${version}`)).toBeInTheDocument()
    expect(await screen.findByText('API conectada')).toBeInTheDocument()
  })
  it.each([undefined,'invalid'])('conserva conectividad si la versión no es válida (%s)',async(version)=>{
    vi.stubGlobal('fetch',vi.fn((path:string)=>Promise.resolve(jsonResponse(path==='/health'?{status:'ok'}:{version}))))
    render(<MemoryRouter><Layout /></MemoryRouter>)
    expect(await screen.findByText('API conectada')).toBeInTheDocument()
    expect(screen.getByLabelText('Versión de Ticketyn')).toHaveTextContent('versión no disponible')
  })
  it('backend no disponible conserva estado neutro',async()=>{
    vi.stubGlobal('fetch',vi.fn(()=>Promise.reject(new Error('offline'))))
    render(<MemoryRouter><Layout /></MemoryRouter>)
    expect(await screen.findByText('API no disponible')).toBeInTheDocument()
    expect(screen.getByLabelText('Versión de Ticketyn')).toHaveTextContent('versión no disponible')
  })
})
