"""Check new assignments only; callers retain unchanged historical relations."""
from fastapi import HTTPException


def selectable(person):
    if not person.operational_selectable:
        raise HTTPException(422, 'El Responsable no está disponible para nuevas asignaciones operativas')
    return person
