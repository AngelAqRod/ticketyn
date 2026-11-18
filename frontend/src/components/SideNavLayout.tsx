import { useState, type ReactNode } from 'react'
import { Search } from 'lucide-react'
import '../styles/sideNav.css'

export interface SideNavGroup<T extends string> { label: string; items: { id: T; label: string }[] }

interface Props<T extends string> {
  label: string
  groups: SideNavGroup<T>[]
  active: T | undefined
  onSelect: (id: T) => void
  searchLabel?: string
  children: ReactNode
}

const plain = (text: string) => text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()

/** Navegación lateral agrupada + contenido; en pantallas angostas la navegación pasa arriba. */
export function SideNavLayout<T extends string>({ label, groups, active, onSelect, searchLabel, children }: Props<T>) {
  const [query, setQuery] = useState('')
  const visible = groups.map(group => ({ ...group, items: group.items.filter(item => plain(item.label).includes(plain(query.trim()))) })).filter(group => group.items.length)
  return <div className="side-layout">
    <nav aria-label={label} className="side-nav">
      {searchLabel && <label className="side-nav-search"><Search size={16} aria-hidden="true" />
        <input type="search" aria-label={searchLabel} placeholder={searchLabel} value={query} onChange={event => setQuery(event.target.value)} /></label>}
      {visible.map(group => <div key={group.label} role="group" aria-label={group.label} className="side-nav-group">
        <p className="side-nav-heading">{group.label}</p>
        {group.items.map(item => <button type="button" key={item.id} className="side-nav-item" aria-pressed={item.id === active} onClick={() => onSelect(item.id)}>{item.label}</button>)}
      </div>)}
      {!visible.length && <p className="side-nav-empty" role="status">Sin coincidencias.</p>}
    </nav>
    <div className="side-content">{children}</div>
  </div>
}
