import { useSearchParams } from 'react-router'

export function useUrlFilters(keys: readonly string[]) {
  const [params, setParams] = useSearchParams()
  function change(values: Record<string, string>, resetPage = true) {
    setParams((current) => {
      const next = new URLSearchParams(current)
      for (const [key, value] of Object.entries(values)) value ? next.set(key, value) : next.delete(key)
      if (resetPage) next.delete('offset')
      return next
    })
  }
  function clear() {
    setParams((current) => {
      const next = new URLSearchParams(current)
      for (const key of [...keys, 'offset']) next.delete(key)
      return next
    })
  }
  return { params, change, clear }
}
