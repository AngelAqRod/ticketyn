import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { FormField } from './FormField'
import { SearchableSelect } from './SearchableSelect'

describe('asociación accesible de errores de campos', () => {
  it('describe un control anidado sin marcar otros botones como inválidos', () => {
    render(<><FormField id="date" label="Fecha" describedBy="date-error" invalid>
      <div><input id="date" type="date" aria-describedby="date-help" /><button type="button">Ahora</button></div>
    </FormField><p id="date-help">Fecha local</p><p id="date-error">Fecha inválida</p></>)
    expect(screen.getByLabelText('Fecha')).toHaveAttribute('aria-describedby', 'date-help date-error')
    expect(screen.getByLabelText('Fecha')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('button')).not.toHaveAttribute('aria-invalid')
  })

  it('propaga las asociaciones al input real de SearchableSelect', () => {
    render(<><FormField id="customer" label="Cliente" describedBy="customer-error" invalid>
      <div><SearchableSelect id="customer" label="Cliente" value="" onChange={vi.fn()} options={[]} placeholder="Selecciona" emptyMessage="Vacío" noMatchMessage="Vacío" /></div>
    </FormField><p id="customer-error">Selecciona un cliente</p></>)
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-describedby', 'customer-error')
    expect(screen.getByRole('combobox')).toHaveAttribute('aria-invalid', 'true')
  })

  it('retira la asociación y estado inválido cuando desaparece el error', () => {
    const { rerender } = render(<FormField id="name" label="Nombre" describedBy="name-error" invalid><input id="name" /></FormField>)
    rerender(<FormField id="name" label="Nombre"><input id="name" /></FormField>)
    expect(screen.getByLabelText('Nombre')).not.toHaveAttribute('aria-describedby')
    expect(screen.getByLabelText('Nombre')).not.toHaveAttribute('aria-invalid')
  })
})
