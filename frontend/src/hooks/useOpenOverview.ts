import { useEffect, useState } from 'react'
import { getOpenOverview } from '../api'
import type { OpenOverview } from '../types/ticket'

export function useOpenOverview(refresh = 0) {
  const [state, setState] = useState<{ loading: boolean; overview: OpenOverview | null; error: string | null }>({
    loading: true, overview: null, error: null,
  })
  useEffect(() => {
    const controller = new AbortController()
    setState({ loading: true, overview: null, error: null })
    getOpenOverview(controller.signal)
      .then((overview) => { if (!controller.signal.aborted) setState({ loading: false, overview, error: null }) })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setState({
          loading: false, overview: null,
          error: error instanceof Error ? error.message : 'Ocurrió un error inesperado.',
        })
      })
    return () => controller.abort()
  }, [refresh])
  return state
}
