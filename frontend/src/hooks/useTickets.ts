import { useEffect, useState } from 'react'
import { listTickets } from '../api'
import type { Ticket } from '../types/ticket'

export function useTickets(offset = 0, refresh = 0) {
  const [state, setState] = useState<{ loading: boolean; tickets: Ticket[]; error: string | null }>({
    loading: true, tickets: [], error: null,
  })
  useEffect(() => {
    const controller = new AbortController()
    setState({ loading: true, tickets: [], error: null })
    listTickets({ limit: 50, offset }, controller.signal)
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
  }, [offset, refresh])
  return state
}
