import { fireEvent, render, screen, waitFor } from '../test/render'
import { describe, expect, it, vi } from 'vitest'
import { InternalTicketReportDownload } from './InternalTicketReportDownload'
import { jsonResponse } from '../test/fixtures'

function setup(mode = 'ok') {
  vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn(() => 'blob:report'); static revokeObjectURL = vi.fn() })
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  const fetch = vi.fn((_url: string) => mode === 'pending' ? new Promise<Response>(() => {}) : Promise.resolve(mode === 'error' ? jsonResponse({detail:'No se pudo generar el reporte del ticket.'},500) : new Response(new Blob(['PDF']))))
  vi.stubGlobal('fetch',fetch)
  render(<InternalTicketReportDownload id={7} reference="INT-0000001" />)
  return {click,fetch}
}
describe('PDF individual interno', () => {
  it('descarga el ticket consultado con zona horaria y nombre descriptivo', async () => {
    const {click,fetch}=setup()
    fireEvent.click(screen.getByRole('button',{name:'Exportar PDF'}))
    await waitFor(()=>expect(click).toHaveBeenCalledOnce())
    const url=new URL(fetch.mock.calls[0][0]!, 'http://local')
    expect(url.pathname).toBe('/api/internal-tickets/7/reports/internal/pdf')
    expect(url.searchParams.get('timezone')).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone)
    expect((click.mock.instances[0] as HTMLAnchorElement).download).toBe('Ticket_Interno_INT-0000001.pdf')
    expect(screen.queryByText('Reporte para cliente')).not.toBeInTheDocument()
    click.mockRestore()
  })
  it('evita descargas duplicadas y muestra carga', () => {
    const {click,fetch}=setup('pending')
    const button=screen.getByRole('button',{name:'Exportar PDF'})
    fireEvent.click(button);fireEvent.click(button)
    expect(screen.getByRole('button',{name:'Generando PDF...'})).toBeDisabled()
    expect(fetch).toHaveBeenCalledOnce()
    click.mockRestore()
  })
  it('presenta errores y habilita reintento', async () => {
    const {click}=setup('error')
    fireEvent.click(screen.getByRole('button',{name:'Exportar PDF'}))
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo generar el reporte del ticket.')
    expect(screen.getByRole('button',{name:'Exportar PDF'})).toBeEnabled()
    click.mockRestore()
  })
})
