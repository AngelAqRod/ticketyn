import { reportPeriod } from './reportPeriod'

/** Identical effective-date filters for the list and its complete exports. */
export function operationFilters(params: URLSearchParams): URLSearchParams {
  const filters = new URLSearchParams(params)
  if (!filters.has('period')) filters.set('period', 'all')
  const { query } = reportPeriod(filters)
  const result = new URLSearchParams()
  if (query.from) result.set('from_at', query.from)
  if (query.to) result.set('to_at', query.to)
  for (const field of ['customer_id', 'operation_type']) if (filters.get(field)) result.set(field, filters.get(field)!)
  return result
}
