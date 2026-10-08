import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TicketReportDownload } from './TicketReportDownload'
import { jsonResponse } from '../test/fixtures'

function setup(fetcher: (path: string) => Promise<Response>) {
  vi.stubGlobal('fetch', vi.fn(fetcher))
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = vi.fn(() => 'blob:report')
    static revokeObjectURL = vi.fn()
  })
  const filenames: string[] = []
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function(this: HTMLAnchorElement) { filenames.push(this.download) })
  render(<TicketReportDownload ticketId={27} />)
  fireEvent.click(screen.getByText('Exportar PDF'))
  return { fetch: vi.mocked(fetch), click, filenames }
}
afterEach(() => vi.restoreAllMocks())

describe('PDF individual de ticket', () => {
  it.each(['internal', 'customer'] as const)('descarga %s con URL relativa, zona local y nombre identificable', async (kind) => {
    const { fetch, filenames } = setup(() => Promise.resolve(new Response(new Blob(['%PDF-1.4'], { type: 'application/pdf' }))))
    fireEvent.click(screen.getByRole('button', { name: kind === 'internal' ? 'Reporte técnico interno' : 'Reporte para cliente' }))
    await waitFor(() => expect(filenames).toHaveLength(1))
    const path = new URL(fetch.mock.calls[0][0] as string, 'http://test')
    expect(path.pathname).toBe(`/api/tickets/27/reports/${kind}/pdf`)
    expect(Object.fromEntries(path.searchParams)).toEqual({ timezone: Intl.DateTimeFormat().resolvedOptions().timeZone })
    expect(filenames).toEqual([`ticketyn-ticket-27-${kind === 'internal' ? 'interno' : 'cliente'}.pdf`])
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:report')
    expect(screen.getByRole('button', { name: 'Exportar PDF' })).toHaveAttribute('aria-expanded', 'false')
  })

  it('mantiene la página y permite reintentar un error sin filtrar información interna desde React', async () => {
    let fail = true
    const { fetch, filenames } = setup(() => Promise.resolve(fail ? jsonResponse({ detail: 'No se pudo generar el reporte del ticket.' }, 500) : new Response('PDF')))
    fireEvent.click(screen.getByRole('button', { name: 'Reporte para cliente' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo generar el reporte')
    expect(screen.getByText('Exportar PDF')).toBeInTheDocument()
    fail = false
    fireEvent.click(screen.getByRole('button', { name: 'Reporte para cliente' }))
    await waitFor(() => expect(filenames).toHaveLength(1))
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('bloquea descargas duplicadas y ambas opciones durante la generación', async () => {
    let finish!: (response: Response) => void
    const { fetch } = setup(() => new Promise<Response>((resolve) => { finish = resolve }))
    fireEvent.click(screen.getByRole('button', { name: 'Reporte técnico interno' }))
    fireEvent.click(screen.getByRole('button', { name: 'Reporte técnico interno' }))
    expect(screen.getByRole('button', { name: 'Reporte para cliente' })).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('Generando reporte')
    expect(fetch).toHaveBeenCalledTimes(1)
    await act(async () => finish(new Response('PDF')))
  })

  it('Escape cierra las opciones y devuelve foco al control de exportación', () => {
    setup(() => Promise.resolve(new Response('PDF')))
    fireEvent.keyDown(screen.getByRole('button', { name: 'Reporte técnico interno' }), { key: 'Escape' })
    expect(screen.getByRole('button', { name: 'Exportar PDF' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.getByText('Exportar PDF')).toHaveFocus()
  })
})


describe('portal PDF y viewport', () => {
  it.each([320, 390, 1440])('muestra las dos opciones fuera del encabezado con overflow clip a %s px', (width) => {
    vi.stubGlobal('innerWidth', width)
    vi.stubGlobal('innerHeight', 200)
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function(this: HTMLElement) {
      return { left: width - 140, right: width - 16, top: 120, bottom: 156, width: 124, height: this.tagName === 'BUTTON' ? 36 : 100, x: 0, y: 0, toJSON() {} }
    })
    const rendered = render(<header className="record-header" style={{ overflow: 'clip', isolation: 'isolate' }}><TicketReportDownload ticketId={27} /></header>)
    fireEvent.click(screen.getByRole('button', { name: 'Exportar PDF' }))
    const popup = screen.getByRole('group', { name: 'Tipos de reporte PDF' })
    expect(popup.parentElement).toBe(document.body)
    expect(rendered.container).not.toContainElement(popup)
    expect(screen.getByRole('button', { name: 'Reporte técnico interno' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Reporte para cliente' })).toBeVisible()
    expect(popup).toHaveClass('fixed', 'z-50')
    const left = parseFloat(popup.style.left), top = parseFloat(popup.style.top)
    expect(left).toBeGreaterThanOrEqual(16)
    expect(left + parseFloat(popup.style.width)).toBeLessThanOrEqual(width - 16)
    expect(top).toBeGreaterThanOrEqual(16)
    expect(top + 100).toBeLessThanOrEqual(184)
  })

  it('clic exterior cierra; teclado permite recorrer opciones y Escape devuelve foco', () => {
    render(<><TicketReportDownload ticketId={27} /><button>Fuera</button></>)
    const trigger = screen.getByRole('button', { name: 'Exportar PDF' })
    fireEvent.keyDown(trigger, { key: 'ArrowDown' })
    const internal = screen.getByRole('button', { name: 'Reporte técnico interno' })
    const customer = screen.getByRole('button', { name: 'Reporte para cliente' })
    expect(internal).toHaveFocus()
    fireEvent.keyDown(internal, { key: 'ArrowDown' }); expect(customer).toHaveFocus()
    fireEvent.keyDown(customer, { key: 'Home' }); expect(internal).toHaveFocus()
    fireEvent.keyDown(internal, { key: 'End' }); expect(customer).toHaveFocus()
    fireEvent.keyDown(customer, { key: 'Escape' }); expect(trigger).toHaveFocus()
    expect(screen.queryByRole('group')).not.toBeInTheDocument()
    fireEvent.click(trigger)
    fireEvent.pointerDown(screen.getByRole('button', { name: 'Fuera' }))
    expect(screen.queryByRole('group')).not.toBeInTheDocument()
  })

  it('recalcula su posición al cambiar viewport y elimina el portal al desmontar', () => {
    const rendered = render(<TicketReportDownload ticketId={27} />)
    fireEvent.click(screen.getByRole('button', { name: 'Exportar PDF' }))
    vi.stubGlobal('innerWidth', 320)
    fireEvent(window, new Event('resize'))
    const popup = screen.getByRole('group')
    expect(parseFloat(popup.style.left) + parseFloat(popup.style.width)).toBeLessThanOrEqual(304)
    rendered.unmount()
    expect(screen.queryByRole('group')).not.toBeInTheDocument()
  })
})
