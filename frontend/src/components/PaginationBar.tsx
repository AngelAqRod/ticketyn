import type { ReactNode } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

/** Presentation only. Each listing keeps its own offsets, limits and availability rules. */
export function PaginationBar({ page, info, onPrevious, onNext, previousDisabled, nextDisabled,
  previousLabel = 'Anterior', nextLabel = 'Siguiente', className = '' }: {
  page: number; info: ReactNode; onPrevious: () => void; onNext: () => void
  previousDisabled: boolean; nextDisabled: boolean; previousLabel?: string; nextLabel?: string; className?: string
}) {
  return <div className={`pagination-bar ${className}`}>
    <div className="pagination-info">{info}</div>
    <div className="pagination-controls" role="group" aria-label="Navegación de páginas">
      <button type="button" className="button-secondary pagination-control" aria-label={previousLabel} title={previousLabel} disabled={previousDisabled} onClick={onPrevious}>
        <ChevronLeft size={15} aria-hidden="true" />
      </button>
      <span className="pagination-current" aria-current="page" aria-label={`Página ${page}`}>{page}</span>
      <button type="button" className="button-secondary pagination-control" aria-label={nextLabel} title={nextLabel} disabled={nextDisabled} onClick={onNext}>
        <ChevronRight size={15} aria-hidden="true" />
      </button>
    </div>
  </div>
}
