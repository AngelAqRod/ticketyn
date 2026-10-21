"""Account administration over existing Responsibles; callers own the transaction."""
from fastapi import HTTPException
from sqlalchemy import select, func, literal
from ticketyn.models import Responsible
from ticketyn.models.security import SecurityRole
from ticketyn.schemas.responsible import ResponsibleResponse
from ticketyn.security import roles
from ticketyn.security.service import lock_security, principal, audit, set_access


def locked_account(session, actor_id, id):
    lock_security(session)
    actor = principal(session, actor_id)
    item = session.scalar(select(Responsible).where(Responsible.id == id).with_for_update(of=Responsible))
    if item is None:
        raise HTTPException(404, 'Responsable no encontrado')
    roles.authorize_account_change(session, actor, item)
    return actor, item


def account_view(session, item):
    role = session.get(SecurityRole, item.security_role_id) if item.security_role_id else None
    return {**ResponsibleResponse.model_validate(item).model_dump(mode='json'),
            'account_exists': item.username is not None, 'username': item.username,
            'role_id': item.security_role_id, 'role_name': role.name if role else None,
            'access_granted': item.access_granted,
            'effective_access': bool(item.active and item.access_granted and item.username and item.password_hash and role),
            'password_change_required': item.password_change_required}


def username_available(session, username, id):
    duplicate = session.scalar(select(Responsible.id).where(
        func.lower(Responsible.username.collate('C.utf8')) == func.lower(literal(username).collate('C.utf8')),
        Responsible.id != id).limit(1))
    if duplicate is not None:
        raise HTTPException(409, 'El nombre de usuario ya está reservado')


def create_account(session, actor_id, id, username, role_id, encoded_password, granted):
    actor, item = locked_account(session, actor_id, id)
    if item.username is not None:
        raise HTTPException(409, 'El Responsable ya tiene una cuenta')
    role = session.get(SecurityRole, role_id)
    if role is None:
        raise HTTPException(404, 'Rol no encontrado')
    roles.authorize_account_change(session, actor, item, role)
    if granted and not item.active:
        raise HTTPException(422, 'No se puede habilitar acceso para un Responsable inactivo')
    username_available(session, username, id)
    item.username, item.password_hash, item.security_role_id = username, encoded_password, role.id
    item.access_granted = granted
    item.password_change_required = True
    item.access_revision += 1
    audit(session, 'ACCOUNT_CREATED', id, actor.id, details={'username': username, 'role_id': role.id, 'access_granted': granted})
    return item


def update_account(session, actor_id, id, values):
    actor, item = locked_account(session, actor_id, id)
    if item.username is None:
        raise HTTPException(404, 'Cuenta no encontrada')
    if 'username' in values and values['username'] != item.username:
        username_available(session, values['username'], id)
        before = item.username
        item.username = values['username']
        item.access_revision += 1
        audit(session, 'ACCOUNT_USERNAME_CHANGED', id, actor.id, details={'before': before, 'after': item.username})
    if 'role_id' in values:
        roles.assign_role(session, actor, id, values['role_id'])
    if 'access_granted' in values:
        set_access(session, id, values['access_granted'], actor.id)
    return item
