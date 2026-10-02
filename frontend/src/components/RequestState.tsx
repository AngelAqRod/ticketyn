import { Inbox, CircleAlert, LoaderCircle } from 'lucide-react'

export function RequestState({ loading, error, empty, onRetry }: {
  loading: boolean; error: string | null; empty: boolean; onRetry?: () => void
}) {
  if (loading) return <div role="status" className="panel flex items-center justify-center gap-3 p-16 text-sm text-slate-500"><LoaderCircle size={20} aria-hidden="true" />Cargando...</div>
  if (error) return <div role="alert" className="panel p-10 text-center">
    <CircleAlert className="mx-auto mb-4 text-red-600" size={28} aria-hidden="true" />
    <h2 className="font-semibold text-slate-900">Error al cargar tickets</h2>
    <p className="mx-auto mt-2 max-w-lg text-sm text-slate-600">{error}</p>
    {onRetry && <button className="button-secondary mt-5" onClick={onRetry}>Reintentar</button>}
  </div>
  if (empty) return <div role="status" className="panel p-16 text-center">
    <Inbox className="mx-auto mb-4 text-slate-400" size={32} aria-hidden="true" />
    <h2 className="font-semibold text-slate-900">No hay tickets</h2>
    <p className="mt-2 text-sm text-slate-500">No se encontraron registros en esta página.</p>
  </div>
  return null
}
