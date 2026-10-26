import { X, ChevronDown } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { AriaAttributes, KeyboardEvent, ReactNode } from 'react'

export interface SelectOption { value: string; label: string; disabled?: boolean }
interface Props extends Pick<AriaAttributes, 'aria-describedby' | 'aria-invalid'> {
  dropdownFooter?: ReactNode
  onSearchChange?: (query: string) => void
  remote?: boolean
  id: string
  value: string
  options: SelectOption[]
  onChange: (value: string) => void
  disabled?: boolean
  required?: boolean
  label: string
  placeholder: string
  emptyMessage: string
  noMatchMessage: string
}

function normalizeText(text: string): string {
  return text.toLocaleLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
}

export function SearchableSelect({ id, value, options, onChange, onSearchChange, dropdownFooter, remote = false, disabled = false, required = false, label, placeholder, emptyMessage, noMatchMessage, 'aria-describedby': describedBy, 'aria-invalid': invalid }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState<string | null>(null)
  const root = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const selected = options.find((option) => option.value === value)
  const normalizedQuery = normalizeText(query.trim())
  const matches = remote ? options : options.filter((option) => normalizeText(option.label).includes(normalizedQuery))
  const enabled = matches.filter((option) => !option.disabled)
  const expanded = open && !disabled
  const activeIndex = matches.findIndex((option) => option.value === active && !option.disabled)
  const listId = `${id}-options`

  function close() { setOpen(false); setQuery(''); setActive(null) }
  function show() { if (!disabled) { setOpen(true); setQuery(''); onSearchChange?.(''); setActive(null) } }
  function select(option: SelectOption) {
    if (disabled || option.disabled) return
    onChange(option.value)
    close()
  }
  useLayoutEffect(() => { setOpen(false); setQuery(''); setActive(null) }, [value, disabled])
  useEffect(() => {
    if (!expanded) return
    function outside(event: PointerEvent) {
      if (event.target instanceof Node && !root.current?.contains(event.target)) close()
    }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [expanded])
  useEffect(() => {
    if (expanded && activeIndex >= 0) document.getElementById(`${id}-option-${activeIndex}`)?.scrollIntoView?.({ block: 'nearest' })
  }, [activeIndex, expanded, id])

  function keyboard(event: KeyboardEvent<HTMLInputElement>) {
    if (disabled) return
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (!expanded) { setOpen(true); setQuery('') }
      const choices = expanded ? enabled : options.filter((option) => !option.disabled)
      const index = choices.findIndex((option) => option.value === active)
      const next = event.key === 'ArrowDown' ? (index + 1) % choices.length : (index < 0 ? choices.length - 1 : (index - 1 + choices.length) % choices.length)
      setActive(choices[next]?.value ?? null)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      if (!expanded) show()
      else { const option = enabled.find((item) => item.value === active) ?? enabled[0]; if (option) select(option) }
    } else if (event.key === 'Escape') {
      event.preventDefault(); event.stopPropagation(); close()
    }
  }

  return <div ref={root} className="relative" onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) close() }}>
    <div className="flex items-center gap-1">
      <input ref={input} id={id} role="combobox" type="text" autoComplete="off" className="form-input min-w-0" disabled={disabled}
        aria-describedby={describedBy} aria-invalid={invalid}
        aria-haspopup="listbox" aria-required={required} aria-expanded={expanded} aria-controls={expanded ? listId : undefined} aria-autocomplete="list"
        aria-activedescendant={expanded && activeIndex >= 0 ? `${id}-option-${activeIndex}` : undefined}
        value={expanded ? query : selected?.label ?? ''} placeholder={selected?.label ?? placeholder}
        onFocus={show} onClick={() => { if (!expanded) show() }}
        onChange={(event) => { setOpen(true); setQuery(event.target.value); onSearchChange?.(event.target.value); setActive(null) }} onKeyDown={keyboard} />
      {value && <button type="button" className="combobox-action" disabled={disabled} aria-label={`Limpiar ${label}`} onClick={() => { onChange(''); close() }}><X size={14} aria-hidden="true" /></button>}
      <button type="button" className="combobox-action" disabled={disabled} aria-label={`${expanded ? 'Cerrar' : 'Abrir'} ${label}`} onMouseDown={(event) => event.preventDefault()} onClick={() => { if (expanded) close(); else { input.current?.focus(); show() } }}><ChevronDown size={14} aria-hidden="true" /></button>
    </div>
    {expanded && <div className="combobox-menu">
      {query && <button type="button" className="px-3 py-2 text-xs text-sky-400 hover:text-sky-300 underline font-mono" onMouseDown={(event) => event.preventDefault()} onClick={() => { setQuery(''); onSearchChange?.(''); setActive(null); input.current?.focus() }}>Limpiar búsqueda</button>}
      <ul id={listId} role="listbox" aria-label={label} className="overflow-y-auto py-1">
        {matches.map((option, index) => <li key={option.value} id={`${id}-option-${index}`} role="option" aria-selected={value === option.value} aria-disabled={option.disabled || undefined}
          className={`mx-1 px-3 py-2 text-sm rounded-md transition-colors ${
            option.disabled
              ? 'cursor-not-allowed text-slate-500'
              : active === option.value
              ? 'bg-[#1e3a6d] text-white font-medium'
              : value === option.value
              ? 'bg-[#172a50] text-sky-300 font-semibold'
              : 'cursor-pointer text-slate-100 hover:bg-[#152648] hover:text-white'
          }`}
          onMouseDown={(event) => event.preventDefault()} onMouseEnter={() => { if (!option.disabled) setActive(option.value) }} onClick={() => select(option)}>
          {option.label}{option.disabled && <span className="ml-2 text-xs text-slate-500">(Inactivo)</span>}{value === option.value && <span aria-hidden="true" className="ml-2 text-sky-400 font-bold">✓</span>}
        </li>)}
      </ul>
      {dropdownFooter}
      {!matches.length && <p role="status" className="px-3 py-3 text-sm text-slate-400 font-mono">{options.length ? noMatchMessage : emptyMessage}</p>}
    </div>}
  </div>
}
