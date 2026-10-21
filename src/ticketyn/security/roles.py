"""Role definitions and bounded account-management authority; no account UI here."""
from sqlalchemy import select, func, literal, delete
from sqlalchemy.dialects.postgresql import insert
from fastapi import HTTPException
from ticketyn.models import Responsible
from ticketyn.models.security import SecurityRole, SecurityPermission, SecurityRolePermission
from ticketyn.security.permissions import PERMISSIONS, DEFAULT_GRANTS, EXCLUSIVE, expanded_context, normalize_permissions


def seed_permissions(session):
    session.execute(insert(SecurityPermission).values([
        {'code': item.code, 'description': item.module + ': ' + item.label} for item in PERMISSIONS.values()
    ]).on_conflict_do_nothing())


def role_grants(session, role):
    if role.code in DEFAULT_GRANTS:
        return DEFAULT_GRANTS[role.code]
    if role.code is not None:
        return frozenset()
    stored = set(session.scalars(select(SecurityRolePermission.permission_code).where(SecurityRolePermission.role_id == role.id)))
    # Deny unknown or exclusive grants even if a malformed database row exists.
    return frozenset(stored & PERMISSIONS.keys() - EXCLUSIVE)


def effective_permissions(session, role):
    return expanded_context(role_grants(session, role))


def require(actor, *permissions):
    if actor is None or not set(permissions) <= actor.permissions:
        raise HTTPException(403, 'No tienes permiso para realizar esta operación')


def authorize_account_change(session, actor, target, assigned_role=None, *, permission='accounts.manage'):
    require(actor, permission)
    if actor.role == 'SUPERADMIN':
        return
    if actor.id == target.id:
        raise HTTPException(403, 'No puedes administrar tu propia cuenta por esta vía')
    target_role = session.get(SecurityRole, target.security_role_id) if target.security_role_id else None
    if target_role is not None:
        if target_role.code in {'SUPERADMIN', 'ADMIN'} or not effective_permissions(session, target_role) < actor.permissions:
            raise HTTPException(403, 'No puedes administrar cuentas equivalentes o superiores')
    if assigned_role is not None:
        if assigned_role.code in {'SUPERADMIN', 'ADMIN'} or not effective_permissions(session, assigned_role) < actor.permissions:
            raise HTTPException(403, 'El rol excede tus facultades de administración')


def assign_role(session, actor, responsible_id, role_id):
    from ticketyn.security.service import lock_security, audit, ensure_not_last_superadmin
    lock_security(session)
    item = session.scalar(select(Responsible).where(Responsible.id == responsible_id).with_for_update(of=Responsible))
    role = session.get(SecurityRole, role_id)
    if item is None or role is None:
        raise HTTPException(404, 'Responsable o rol no encontrado')
    authorize_account_change(session, actor, item, role)
    if not item.username:
        raise HTTPException(422, 'El Responsable no tiene una cuenta configurada')
    if item.security_role_id != role.id:
        if role.code != 'SUPERADMIN':
            ensure_not_last_superadmin(session, item)
        before = item.security_role_id
        item.security_role_id = role.id
        # Permissions are re-read on every request; keep sessions valid for a role change.
        audit(session, 'ACCOUNT_ROLE_CHANGED', item.id, actor.id, details={'before_role_id': before, 'after_role_id': role.id})
    return item


def locked_role(session, id):
    from ticketyn.security.service import lock_security
    lock_security(session)
    role = session.scalar(select(SecurityRole).where(SecurityRole.id == id).with_for_update())
    if role is None:
        raise HTTPException(404, 'Rol no encontrado')
    return role


def unique_name(session, name, exclude=None):
    query = select(SecurityRole.id).where(func.lower(SecurityRole.name.collate('C.utf8')) == func.lower(literal(name).collate('C.utf8')))
    if exclude is not None:
        query = query.where(SecurityRole.id != exclude)
    if session.scalar(query.limit(1)) is not None:
        raise HTTPException(409, 'Ya existe un rol con ese nombre')


def create_role(session, actor, name, description=None):
    from ticketyn.security.service import lock_security, audit
    require(actor, 'roles.manage')
    lock_security(session)
    unique_name(session, name)
    role = SecurityRole(name=name, description=description)
    session.add(role); session.flush()
    audit(session, 'ROLE_CREATED', actor_id=actor.id, details={'role_id': role.id, 'name': role.name})
    return role


def update_role(session, actor, id, values):
    from ticketyn.security.service import audit
    require(actor, 'roles.manage')
    role = locked_role(session, id)
    if role.code is not None:
        raise HTTPException(403, 'Los roles predeterminados son fijos')
    before = {'name': role.name, 'description': role.description, 'permissions': sorted(role_grants(session, role))}
    if 'name' in values:
        unique_name(session, values['name'], role.id)
        role.name = values['name']
    if 'description' in values:
        role.description = values['description']
    if 'permissions' in values:
        grants = normalize_permissions(values['permissions'], before['permissions'])
        session.execute(delete(SecurityRolePermission).where(SecurityRolePermission.role_id == role.id))
        session.add_all(SecurityRolePermission(role_id=role.id, permission_code=code) for code in sorted(grants))
        session.flush()
    after = {'name': role.name, 'description': role.description, 'permissions': sorted(role_grants(session, role))}
    if before != after:
        role.revision += 1
        audit(session, 'ROLE_CHANGED', actor_id=actor.id, details={'role_id': role.id, 'before': before, 'after': after})
    return role


def duplicate_role(session, actor, source_id, name, description=None):
    from ticketyn.security.service import audit
    require(actor, 'roles.manage')
    source = locked_role(session, source_id)
    if source.code in {'SUPERADMIN', 'ADMIN'}:
        raise HTTPException(403, 'Superadministrador y Administrador no pueden duplicarse')
    grants = normalize_permissions(role_grants(session, source))
    role = create_role(session, actor, name, description)
    session.add_all(SecurityRolePermission(role_id=role.id, permission_code=code) for code in sorted(grants))
    audit(session, 'ROLE_DUPLICATED', actor_id=actor.id, details={'role_id': role.id, 'source_role_id': source.id})
    return role


def delete_role(session, actor, id):
    from ticketyn.security.service import audit
    require(actor, 'roles.manage')
    role = locked_role(session, id)
    if role.code is not None:
        raise HTTPException(403, 'Los roles predeterminados no pueden eliminarse')
    if session.scalar(select(Responsible.id).where(Responsible.security_role_id == role.id).limit(1)) is not None:
        raise HTTPException(409, 'El rol tiene Responsables asignados')
    audit(session, 'ROLE_DELETED', actor_id=actor.id, details={'role_id': role.id, 'name': role.name})
    session.delete(role)
