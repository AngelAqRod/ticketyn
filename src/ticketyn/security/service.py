"""Transactional security mutations. Callers commit; audit failures roll back changes."""
from dataclasses import dataclass
from sqlalchemy import select, func, literal
from sqlalchemy.dialects.postgresql import insert
from fastapi import HTTPException
from ticketyn.models import Responsible
from ticketyn.models.security import SecurityRole, SecurityConfig, SecurityAudit, DEFAULT_ROLES
from ticketyn.security.passwords import hash_password, validate_password

@dataclass(frozen=True)
class Principal:
    id: int
    username: str
    name: str
    role: str | None
    revision: int
    temporary: bool
    idle_seconds: int
    role_revision: int
    role_id: int = 0
    permissions: frozenset[str] = frozenset()


def seed_foundation(session):
    # Safe for CLI on a freshly migrated installation, and metadata-based tests.
    session.execute(insert(SecurityConfig).values(id=1).on_conflict_do_nothing())
    for code, name in DEFAULT_ROLES:
        session.execute(insert(SecurityRole).values(code=code, name=name).on_conflict_do_nothing())
    from ticketyn.security.roles import seed_permissions
    seed_permissions(session)


def lock_security(session):
    config = session.scalar(select(SecurityConfig).where(SecurityConfig.id == 1).with_for_update())
    if config is None:
        raise HTTPException(503, 'La configuración de seguridad no está preparada')
    return config


def audit(session, event, target_id=None, actor_id=None, source='HTTP', success=True, details=None):
    from ticketyn.security.audit import EVENTS, clean_details, clean_source
    if event not in EVENTS or event == 'LEGACY':
        raise ValueError('Evento de auditoría no permitido')
    session.add(SecurityAudit(event=event, target_id=target_id, actor_id=actor_id, source=clean_source(source), success=success, details=clean_details(event, details)))
    session.flush()


def principal(session, account_id):
    row = session.execute(select(Responsible, SecurityRole).join(SecurityRole, Responsible.security_role_id == SecurityRole.id).where(Responsible.id == account_id)).first()
    if row is None:
        return None
    account, role = row
    if not account.active or not account.access_granted or not account.password_hash or not account.username:
        return None
    config = session.get(SecurityConfig, 1)
    if config is None:
        return None
    from ticketyn.security.roles import effective_permissions
    return Principal(account.id, account.username, account.name, role.code, account.access_revision, account.password_change_required, config.idle_minutes * 60, role.revision, role.id, effective_permissions(session, role))


def ensure_not_last_superadmin(session, item):
    role = session.get(SecurityRole, item.security_role_id) if item.security_role_id else None
    if not (role and role.code == 'SUPERADMIN' and item.active and item.access_granted):
        return
    count = session.scalar(select(func.count()).select_from(Responsible).join(SecurityRole, Responsible.security_role_id == SecurityRole.id).where(SecurityRole.code == 'SUPERADMIN', Responsible.active.is_(True), Responsible.access_granted.is_(True)))
    if count <= 1:
        raise HTTPException(409, 'Debe permanecer al menos un Superadministrador activo')


def change_operational_status(session, item, active, actor_id=None):
    if item.active == active:
        return
    if item.username and actor_id is not None:
        from ticketyn.security.roles import authorize_account_change
        authorize_account_change(session, principal(session, actor_id), item)
    if not active:
        ensure_not_last_superadmin(session, item)
    item.active = active
    item.access_revision += 1
    audit(session, 'RESPONSIBLE_REACTIVATED' if active else 'RESPONSIBLE_DEACTIVATED', item.id, actor_id)


def set_access(session, account_id, enabled, actor_id=None):
    lock_security(session)
    item = session.scalar(select(Responsible).where(Responsible.id == account_id).with_for_update(of=Responsible))
    if item is None:
        raise HTTPException(404, 'Responsable no encontrado')
    if actor_id is not None:
        from ticketyn.security.roles import authorize_account_change
        authorize_account_change(session, principal(session, actor_id), item)
    if enabled and not item.active:
        raise HTTPException(422, 'No se puede habilitar acceso para un Responsable inactivo')
    if enabled and not (item.username and item.password_hash and item.security_role_id):
        raise HTTPException(422, 'La cuenta no está configurada')
    if item.access_granted != enabled:
        if not enabled:
            ensure_not_last_superadmin(session, item)
        item.access_granted = enabled
        item.access_revision += 1
        audit(session, 'ACCESS_ENABLED' if enabled else 'ACCESS_DISABLED', item.id, actor_id)
    return item


def reset_password(session, account_id, password, actor_id=None, source='HTTP'):
    encoded = hash_password(password)
    lock_security(session)
    item = session.scalar(select(Responsible).where(Responsible.id == account_id).with_for_update(of=Responsible))
    if item is None or not item.username:
        raise HTTPException(404, 'Cuenta no encontrada')
    if actor_id is not None:
        from ticketyn.security.roles import authorize_account_change
        authorize_account_change(session, principal(session, actor_id), item)
    item.password_hash = encoded
    item.password_change_required = True
    item.access_revision += 1
    audit(session, 'PASSWORD_RESET', item.id, actor_id, source)
    return item


def bootstrap(session, responsible_id, username, password, source='CLI', *, responsible_name=None):
    if not isinstance(username, str) or not username or len(username) > 100 or any(ord(char) < 32 or ord(char) == 127 for char in username):
        raise ValueError('El usuario debe contener entre 1 y 100 caracteres sin controles')
    encoded = hash_password(password)
    seed_foundation(session)
    lock_security(session)
    role = session.scalar(select(SecurityRole).where(SecurityRole.code == 'SUPERADMIN'))
    if session.scalar(select(Responsible.id).where(Responsible.security_role_id == role.id).limit(1)):
        raise ValueError('El bootstrap ya fue realizado; utiliza la recuperación de contraseña')
    if responsible_id is None:
        from ticketyn.schemas.responsible import ResponsibleCreate
        from ticketyn.api.crud import validate_catalog_name
        values = ResponsibleCreate(name=responsible_name).model_dump()
        item = Responsible(**values)
        validate_catalog_name(session, item)
        session.add(item)
        session.flush()
    else:
        item = session.scalar(select(Responsible).where(Responsible.id == responsible_id).with_for_update(of=Responsible))
    if item is None or not item.active or item.username:
        raise ValueError('Selecciona un Responsable existente, activo y sin cuenta')
    if session.scalar(select(Responsible.id).where(func.lower(Responsible.username.collate('C.utf8')) == func.lower(literal(username).collate('C.utf8')))):
        raise ValueError('El nombre de usuario ya está reservado')
    item.username = username
    item.password_hash = encoded
    item.security_role_id = role.id
    item.access_granted = True
    item.password_change_required = True
    item.access_revision += 1
    item.active = True
    item.operational_selectable = False
    audit(session, 'BOOTSTRAP_SUPERADMIN', item.id, source=source)
    return item


def recover_superadmin(session, password, source='CLI'):
    lock_security(session)
    ids = session.scalars(select(Responsible.id).join(SecurityRole, Responsible.security_role_id == SecurityRole.id).where(SecurityRole.code == 'SUPERADMIN')).all()
    if len(ids) != 1:
        raise ValueError('La recuperación requiere exactamente una cuenta Superadministrador existente')
    return reset_password(session, ids[0], password, source=source)
