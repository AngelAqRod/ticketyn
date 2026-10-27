import { render, screen, within } from '../test/render'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { TicketTable } from './TicketTable'
import { ticket } from '../test/fixtures'

const now = Date.parse('2026-06-01T12:00:00Z')
const ago = (ms: number) => new Date(now - ms).toISOString()
const H = 3_600_000
const open = (id: number, age: number, extra = {}) => ({ ...ticket, id, reference: `T-${id}`, start_at: ago(age), ...extra })
const show = (tickets: typeof ticket[], hidden?: Parameters<typeof TicketTable>[0]['hidden']) =>
  render(<MemoryRouter><TicketTable tickets={tickets} now={now} hidden={hidden} /></MemoryRouter>)
const row = (reference: string) => screen.getByText(reference).closest('tr')!

describe('antigüedad y estado en TicketTable', () => {
  it('los abiertos llevan franja por tramo y duración en texto', () => {
    show([open(1, 45 * 60_000), open(2, 2 * H + 15 * 60_000), open(3, 9 * H), open(4, 28 * H)])
    expect([1, 2, 3, 4].map((id) => row(`T-${id}`).dataset.age)).toEqual(['lt_1h', '1_to_4h', '4_to_24h', 'gt_24h'])
    expect(['45 min', '2 h 15 min', '9 h', '1 d 4 h'].map((text) => screen.getByText(text).dataset.age)).toEqual(['lt_1h', '1_to_4h', '4_to_24h', 'gt_24h'])
    expect(within(row('T-1')).getByText('Abierto')).toBeInTheDocument()   // el badge no depende del tramo
  })
  it('los cerrados no tienen franja ni acumulan antigüedad y conservan su duración histórica', () => {
    show([open(5, 100 * H, { status: 'CLOSED', end_at: ago(98 * H), duration_seconds: 7200 })])
    expect(row('T-5').dataset.age).toBeUndefined()
    expect(row('T-5')).toHaveClass('ticket-state-closed')
    expect(within(row('T-5')).getByText('Cerrado')).toBeInTheDocument()
    expect(within(row('T-5')).getByText('2 h')).toBeInTheDocument()
    expect(within(row('T-5')).queryByText(/\dd/)).not.toBeInTheDocument()
  })
  it('un inicio futuro no se clasifica y se indica con texto', () => {
    show([open(6, -H)])
    expect(row('T-6').dataset.age).toBeUndefined()
    expect(within(row('T-6')).getByText('Inicio futuro')).toBeInTheDocument()
  })
  it('responsable en texto normal y «Sin asignar» en gris cursiva', () => {
    show([open(7, H, { responsible: { id: 1, name: 'Ana Pérez', active: true } }), open(8, H, { responsible: null })])
    expect(within(row('T-7')).getByText('Ana Pérez')).toHaveClass('text-slate-200')
    expect(within(row('T-7')).getByText('Ana Pérez')).not.toHaveClass('text-amber-300/90')
    expect(within(row('T-8')).getByText('Sin asignar', { selector: 'span.italic' })).toHaveClass('text-slate-400')
  })
  it('encabezado fijo en un único contenedor de scroll y columnas ocultas', () => {
    const { container } = show([open(9, H)], ['node', 'end'])
    expect(container.querySelector('.table-scroll table.sticky-head')).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Nodo' })).not.toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Descripción' })).toBeInTheDocument()
    expect(row('T-9').querySelectorAll('td, th')).toHaveLength(screen.getAllByRole('columnheader').length)
  })
})
