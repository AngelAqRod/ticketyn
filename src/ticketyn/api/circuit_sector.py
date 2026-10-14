"""Sector y Nodo actuales bloqueados y referencias históricas en una sola transacción."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ticketyn.models import Circuit, Sector, Node


def locked_circuit(session: Session, id: int) -> Circuit:
    circuit = session.scalar(select(Circuit).where(Circuit.id == id).with_for_update(of=Circuit).execution_options(populate_existing=True))
    if circuit is None:
        raise HTTPException(404, f'Circuit con id {id} no encontrado')
    return circuit


def validate_assignment(session: Session, model, id: int):
    row = session.scalar(select(model).where(model.id == id).with_for_update(read=True, of=model))
    if row is None:
        raise HTTPException(404, f'{model.__name__} con id {id} no encontrado')
    if not row.active:
        raise HTTPException(422, f'{model.__name__} indicado está inactivo')
    return row


def validate_sector(session: Session, id: int) -> Sector:
    return validate_assignment(session, Sector, id)


def validate_node(session: Session, id: int) -> Node:
    return validate_assignment(session, Node, id)


def resolve_assignment(session: Session, circuit: Circuit, supplied: int | None, field: str, model, label: str) -> int:
    current = getattr(circuit, field)
    if current is not None:
        if supplied is not None and supplied != current:
            validate_assignment(session, model, supplied)
            raise HTTPException(409, f'El circuito ya tiene {label}. Modifícalo desde la edición del circuito.')
        return current
    if supplied is None:
        raise HTTPException(422, f'Selecciona un {label} para el circuito antes de guardar.')
    validate_assignment(session, model, supplied)
    setattr(circuit, field, supplied)
    return supplied


def resolve_sector(session: Session, circuit: Circuit, supplied: int | None) -> int:
    return resolve_assignment(session, circuit, supplied, 'sector_id', Sector, 'Sector')


def resolve_node(session: Session, circuit: Circuit, supplied: int | None) -> int:
    return resolve_assignment(session, circuit, supplied, 'node_id', Node, 'Nodo')
