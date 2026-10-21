import { Can } from '../auth/permissions'
import { Link } from 'react-router'
import { Pencil, Power, Ticket, Trash2 } from 'lucide-react'
import type { Circuit } from '../types/catalog'

/** Same administrative actions in the list and in the circuit heading. */
export function CircuitActions({ circuit, disabled = false, onEdit, onToggle, onDelete }: { circuit: Circuit; disabled?: boolean; onEdit: () => void; onToggle: () => void; onDelete: () => void }) {
  return <>
    <Can permission="tickets.view">
      <Link className="button-ghost table-action rounded-full text-sky-400 hover:text-sky-300 font-mono text-xs inline-flex items-center gap-1.5" to={`/tickets?circuit_id=${circuit.id}`} aria-label={`Ver tickets de ${circuit.circuit_code}`}>
        <Ticket size={13} aria-hidden="true" />
        Ver tickets
      </Link>
    </Can>
    <Can permission="circuits.edit">
      <button type="button" className="button-secondary table-action rounded-full" disabled={disabled} onClick={onEdit} aria-label={`Editar ${circuit.circuit_code}`}>
        <Pencil size={13} aria-hidden="true" />
        Editar
      </button>
    </Can>
    <Can permission="circuits.edit">
      <Can permission={circuit.active ? "lifecycle.deactivate" : "lifecycle.reactivate"}>
        <button type="button" className={`${circuit.active ? 'button-danger' : 'button-secondary'} table-action rounded-full`} disabled={disabled} onClick={onToggle} aria-label={`${circuit.active ? 'Desactivar' : 'Activar'} ${circuit.circuit_code}`}>
          <Power size={13} aria-hidden="true" />
          {circuit.active ? 'Desactivar' : 'Activar'}
        </button>
      </Can>
    </Can>
    <Can permission="circuits.delete">
      <button type="button" className="button-danger table-action rounded-full" disabled={disabled} onClick={onDelete} aria-label={`Eliminar ${circuit.circuit_code}`}>
        <Trash2 size={13} aria-hidden="true" />
        Eliminar
      </button>
    </Can>
  </>
}
