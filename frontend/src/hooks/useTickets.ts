import { useEffect, useState } from 'react'
import { listTickets } from '../api'
import type { Ticket, TicketQuery } from '../types/ticket'

export function useTickets(offset = 0, refresh = 0, filters: TicketQuery = {}, validationError: string | null = null) {
  const [state, setState] = useState<{ loading: boolean; tickets: Ticket[]; error: string | null }>({
    loading: true, tickets: [], error: null,
  })
  const filterKey = JSON.stringify(filters)
  useEffect(() => {
    if (validationError) { setState({ loading: false, tickets: [], error: validationError }); return }
    const controller = new AbortController()
    setState({ loading: true, tickets: [], error: null })
    listTickets({ ...JSON.parse(filterKey) as TicketQuery, limit: 50, offset }, controller.signal)
      .then((tickets) => {
        if (!controller.signal.aborted) setState({ loading: false, tickets, error: null })
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setState({
          loading: false, tickets: [],
          error: error instanceof Error ? error.message : 'Ocurrió un error inesperado.',
        })
      })
    return () => controller.abort()
  }, [offset, refresh, filterKey, validationError])
  return state
}
