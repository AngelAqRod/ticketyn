import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import { TicketTable } from './TicketTable'
import { ticket } from '../test/fixtures'

describe('Nodo histórico en el listado', () => {
  it.each([true, false])('no sustituye el Nodo histórico con el actual (%s)', (hasNode) => {
    const data = { ...ticket, node_id: hasNode ? 7 : null, node: hasNode ? { id: 7, name: 'UFINET', active: true } : null,
      circuit: Object.assign({ ...ticket.circuit! }, { node: { id: 8, name: 'NODO ACTUAL DIFERENTE' } }) }
    render(<MemoryRouter><TicketTable tickets={[data]} /></MemoryRouter>)
    const table = screen.getByRole('table')
    expect(within(table).getAllByText(hasNode ? 'UFINET' : 'Sin asignar').length).toBeGreaterThan(0)
    expect(within(table).queryByText('NODO ACTUAL DIFERENTE')).not.toBeInTheDocument()
  })
})
