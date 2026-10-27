export const PAGE_SIZE = 50

export interface PageInfo { page: number; pages: number; first: number; last: number; total: number; lastOffset: number }

/** Rango mostrado para `shown` registros desde `offset` de `total` coincidentes. */
export function pageInfo(offset: number, shown: number, total: number, size = PAGE_SIZE): PageInfo {
  const pages = Math.max(1, Math.ceil(total / size))
  return {
    page: Math.floor(offset / size) + 1, pages, total,
    first: shown ? offset + 1 : 0, last: shown ? offset + shown : 0,
    lastOffset: (pages - 1) * size,
  }
}

export const rangeText = ({ first, last, total }: PageInfo) => total === 0 ? 'Mostrando 0 de 0' : `Mostrando ${first}–${last} de ${total}`
export const pageText = (info: PageInfo) => info.total === 0 ? 'Mostrando 0 de 0' : `Página ${info.page} de ${info.pages} · Registros ${info.first}–${info.last} de ${info.total}`
