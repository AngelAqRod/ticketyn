import { Link } from 'react-router'
import { Pencil, Power, Ticket, Trash2 } from 'lucide-react'
import type { Circuit } from '../types/catalog'

/** Same administrative actions in the list and in the circuit heading. */
export function CircuitActions({ circuit, disabled = false, onEdit, onToggle, onDelete }: { circuit: Circuit; disabled?: boolean; onEdit: () => void; onToggle: () => void; onDelete: () => void }) {
  return <><Link className="button-ghost table-action" to={`/tickets?circuit_id=${circuit.id}`} aria-label={`Ver tickets de ${circuit.circuit_code}`}><Ticket size={14} aria-hidden="true" />Ver tickets</Link>
    <button type="button" className="button-secondary table-action" disabled={disabled} onClick={onEdit} aria-label={`Editar ${circuit.circuit_code}`}><Pencil size={14} aria-hidden="true" />Editar</button>
    <button type="button" className={`${circuit.active ? 'button-danger' : 'button-secondary'} table-action`} disabled={disabled} onClick={onToggle} aria-label={`${circuit.active ? 'Desactivar' : 'Activar'} ${circuit.circuit_code}`}><Power size={14} aria-hidden="true" />{circuit.active ? 'Desactivar' : 'Activar'}</button>
    <button type="button" className="button-danger table-action" disabled={disabled} onClick={onDelete} aria-label={`Eliminar ${circuit.circuit_code}`}><Trash2 size={14} aria-hidden="true" />Eliminar</button></>
}
