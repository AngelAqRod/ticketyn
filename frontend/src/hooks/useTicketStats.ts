import { useEffect, useState } from 'react'
import { getTicketStats } from '../api'
import type { TicketStats } from '../types/ticket'

export function useTicketStats(refresh = 0) {
  const [state, setState] = useState<{ loading: boolean; stats: TicketStats | null; error: string | null }>({
    loading: true, stats: null, error: null,
  })
  useEffect(() => {
    const controller = new AbortController()
    setState({ loading: true, stats: null, error: null })
    getTicketStats(controller.signal)
      .then((stats) => {
        if (!controller.signal.aborted) setState({ loading: false, stats, error: null })
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setState({
          loading: false, stats: null,
          error: error instanceof Error ? error.message : 'Ocurrió un error inesperado.',
        })
      })
    return () => controller.abort()
  }, [refresh])
  return state
}
