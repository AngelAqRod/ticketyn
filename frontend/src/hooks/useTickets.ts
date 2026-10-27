import { useEffect, useState } from 'react'
import { listTicketsPage } from '../api'
import type { Ticket, TicketQuery } from '../types/ticket'

/** `total` es el número filtrado completo (X-Total-Count); si la API no lo envía, null. */
export function useTickets(offset = 0, refresh = 0, filters: TicketQuery = {}, validationError: string | null = null) {
  const [state, setState] = useState<{ loading: boolean; tickets: Ticket[]; total: number | null; error: string | null }>({
    loading: true, tickets: [], total: null, error: null,
  })
  const filterKey = JSON.stringify(filters)
  useEffect(() => {
    if (validationError) { setState({ loading: false, tickets: [], total: null, error: validationError }); return }
    const controller = new AbortController()
    setState({ loading: true, tickets: [], total: null, error: null })
    listTicketsPage({ limit: 50, ...JSON.parse(filterKey) as TicketQuery, offset }, controller.signal)
      .then(({ tickets, total }) => {
        if (!controller.signal.aborted) setState({ loading: false, tickets, total, error: null })
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setState({
          loading: false, tickets: [], total: null,
          error: error instanceof Error ? error.message : 'Ocurrió un error inesperado.',
        })
      })
    return () => controller.abort()
  }, [offset, refresh, filterKey, validationError])
  return state
}
