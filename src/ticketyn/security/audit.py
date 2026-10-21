"""Security events and a bounded, explicit projection of their public metadata."""
import re
from datetime import timezone

from fastapi import HTTPException
from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.orm import aliased

from ticketyn.models import Responsible
from ticketyn.models.security import SecurityAudit
from ticketyn.security.permissions import PERMISSIONS


EVENTS = {
    'LOGIN_SUCCEEDED': 'Inicio de sesión correcto',
    'LOGIN_FAILED_GROUP': 'Inicio de sesión incorrecto (grupo)',
    'PASSWORD_CHANGED': 'Cambio de contraseña',
    'PASSWORD_RESET': 'Restablecimiento de contraseña',
    'ACCESS_ENABLED': 'Acceso habilitado',
    'ACCESS_DISABLED': 'Acceso deshabilitado',
    'ACCOUNT_CREATED': 'Acceso configurado',
    'ACCOUNT_USERNAME_CHANGED': 'Nombre de usuario modificado',
    'ACCOUNT_ROLE_CHANGED': 'Rol del Responsable modificado',
    'ROLE_CREATED': 'Rol creado',
    'ROLE_CHANGED': 'Rol o permisos modificados',
    'ROLE_DUPLICATED': 'Rol duplicado',
    'ROLE_DELETED': 'Rol eliminado',
    'SESSION_CLOSED': 'Sesión cerrada',
    'SESSION_TERMINATED_ADMIN': 'Sesión revocada por administración',
    'BOOTSTRAP_SUPERADMIN': 'Primer Superadministrador configurado',
    'RESPONSIBLE_DEACTIVATED': 'Responsable desactivado',
    'RESPONSIBLE_REACTIVATED': 'Responsable reactivado',
    # Preserve the Phase 3 producer; do not add operational audit instrumentation.
    'RESPONSIBLE_AVAILABILITY_CHANGED': 'Disponibilidad operativa modificada',
    'AUDIT_RETENTION_CHANGED': 'Conservación de auditoría modificada',
    'LEGACY': 'Evento histórico',
}


def text(value, maximum):
    if not isinstance(value, str):
        return None
    return ''.join(char for char in value[:maximum] if char.isprintable())


def positive_id(value):
    return value if type(value) is int and value > 0 else None


def clean_details(event, supplied):
    """Never persist an arbitrary request/ORM dictionary, even inside snapshots."""
    raw = supplied if isinstance(supplied, dict) else {}
    result = {}

    def take(key, converter):
        value = converter(raw.get(key))
        if value is not None:
            result[key] = value

    if event in {'LOGIN_SUCCEEDED', 'LOGIN_FAILED_GROUP'}:
        take('username', lambda value: text(value, 100))
        take('ip', lambda value: text(value, 64))
        if raw.get('operation') in {'LOGIN', 'PASSWORD_CHANGE'}:
            result['operation'] = raw['operation']
    elif event == 'ACCOUNT_CREATED':
        take('username', lambda value: text(value, 100))
        take('role_id', positive_id)
        take('access_granted', lambda value: value if type(value) is bool else None)
    elif event == 'ACCOUNT_USERNAME_CHANGED':
        for key in ('before', 'after'):
            take(key, lambda value: text(value, 100))
    elif event == 'ACCOUNT_ROLE_CHANGED':
        for key in ('before_role_id', 'after_role_id'):
            take(key, positive_id)
    elif event.startswith('ROLE_'):
        for key in ('role_id', 'source_role_id'):
            take(key, positive_id)
        take('name', lambda value: text(value, 200))
        if event == 'ROLE_CHANGED':
            for key in ('before', 'after'):
                snapshot = raw.get(key)
                if not isinstance(snapshot, dict):
                    continue
                safe = {}
                name = text(snapshot.get('name'), 200)
                if name is not None:
                    safe['name'] = name
                permissions = snapshot.get('permissions')
                if isinstance(permissions, list):
                    safe['permissions'] = sorted({code for code in permissions[:500]
                                                  if isinstance(code, str) and code in PERMISSIONS})
                result[key] = safe
            before, after = raw.get('before'), raw.get('after')
            if isinstance(before, dict) and isinstance(after, dict) and 'description' in before and 'description' in after:
                result['description_changed'] = before['description'] != after['description']
            elif type(raw.get('description_changed')) is bool:
                result['description_changed'] = raw['description_changed']
    elif event == 'RESPONSIBLE_AVAILABILITY_CHANGED':
        for key in ('before', 'after'):
            take(key, lambda value: value if type(value) is bool else None)
    elif event == 'AUDIT_RETENTION_CHANGED':
        for key in ('before_days', 'after_days'):
            take(key, lambda value: value if type(value) is int and 1 <= value <= 3650 else None)
    return result


def clean_source(value):
    # CLI sets its own UID; never serialize arbitrary legacy source text.
    return value if isinstance(value, str) and re.fullmatch(r'HTTP|CLI(?: uid=[\w-]{1,32})?', value) else 'OTHER'


def detail_rows(event, supplied):
    safe = clean_details(event, supplied)
    rows = []
    labels = {'username': 'Identificador registrado', 'ip': 'IP', 'role_id': 'Rol (id)',
              'source_role_id': 'Rol de origen (id)', 'before_role_id': 'Rol anterior (id)',
              'after_role_id': 'Rol nuevo (id)', 'access_granted': 'Acceso autorizado', 'name': 'Nombre del rol',
              'before': 'Anterior', 'after': 'Nuevo', 'description_changed': 'Descripción modificada',
              'before_days': 'Días anteriores', 'after_days': 'Días nuevos'}
    for key, value in safe.items():
        if key == 'operation':
            rows.append({'label': 'Operación', 'value': 'Cambio de contraseña' if value == 'PASSWORD_CHANGE' else 'Inicio de sesión'})
        elif isinstance(value, dict):
            prefix = 'Anterior' if key == 'before' else 'Nuevo'
            if 'name' in value:
                rows.append({'label': prefix + ' · nombre', 'value': value['name']})
            if 'permissions' in value:
                names = [PERMISSIONS[code].module + ' · ' + PERMISSIONS[code].label for code in value['permissions']]
                rows.append({'label': prefix + ' · permisos', 'value': ', '.join(names) or 'Sin permisos'})
        else:
            rows.append({'label': labels[key], 'value': ('Sí' if value else 'No') if type(value) is bool else str(value)})
    return rows


def audit_page(session, actor, filters):
    person, target = aliased(Responsible), aliased(Responsible)
    # Only known events may expose their explicit username metadata or details.
    recorded_identifier = SecurityAudit.details['username']
    identifier = case((and_(
        SecurityAudit.event.in_({'LOGIN_SUCCEEDED', 'LOGIN_FAILED_GROUP', 'ACCOUNT_CREATED'}),
        func.jsonb_typeof(recorded_identifier) == 'string'),
        func.left(recorded_identifier.astext, 100)), else_=None)
    query = select(SecurityAudit, person.id, person.name, person.username,
                   target.id, target.name, target.username, identifier).outerjoin(
        person, person.id == SecurityAudit.actor_id).outerjoin(target, target.id == SecurityAudit.target_id)
    role_history = 'roles.manage' in actor.permissions
    if not role_history:
        query = query.where(~SecurityAudit.event.startswith('ROLE_', autoescape=True))
    if filters.event:
        if filters.event.startswith('ROLE_') and not role_history:
            raise HTTPException(403, 'No tienes permiso para consultar el historial de definiciones de roles')
        query = query.where(SecurityAudit.event.not_in(EVENTS) if filters.event == 'LEGACY'
                            else SecurityAudit.event == filters.event)
    if filters.actor_id is not None:
        query = query.where(SecurityAudit.actor_id == filters.actor_id)
    if filters.username:
        values = (person.name, person.username, target.name, target.username, identifier)
        query = query.where(or_(*(func.lower(cast(value, String).collate('C.utf8')).contains(
            filters.username.lower(), autoescape=True) for value in values)))
    if filters.from_at is not None:
        query = query.where(SecurityAudit.occurred_at >= filters.from_at)
    if filters.to_at is not None:
        query = query.where(SecurityAudit.occurred_at < filters.to_at)
    if filters.result != 'ALL':
        query = query.where(SecurityAudit.success.is_(filters.result == 'SUCCESS'))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    records = session.execute(query.order_by(SecurityAudit.occurred_at.desc(), SecurityAudit.id.desc())
                              .limit(filters.limit).offset(filters.offset))
    items = []
    for row, person_id, name, username, target_id, target_name, target_username, _ in records:
        event = row.event if row.event in EVENTS else 'LEGACY'
        details = detail_rows(event, row.details)
        available = clean_details(event, row.details).get('username')
        legacy_group = event == 'LOGIN_FAILED_GROUP' and not available
        if event == 'LOGIN_FAILED_GROUP':
            details.append({'label': 'Información del grupo', 'value':
                'Registro histórico; cantidad de intentos no disponible.' if legacy_group
                else 'Fallos agrupados; cantidad exacta de intentos no registrada.'})
        source = 'Administración local' if clean_source(row.source).startswith('CLI') else 'Aplicación' if row.source == 'HTTP' else 'Origen histórico'
        items.append({'id': row.id, 'occurred_at': row.occurred_at.astimezone(timezone.utc),
                      'actor': {'id': person_id, 'name': name, 'username': username} if person_id is not None else None,
                      'target': {'id': target_id, 'name': target_name, 'username': target_username} if target_id is not None else None,
                      'identifier': available, 'event': event, 'event_label': EVENTS[event],
                      'source': source, 'success': row.success, 'details': details})
    return {'items': items, 'total': total, 'limit': filters.limit, 'offset': filters.offset,
            'events': [{'code': code, 'label': label} for code, label in EVENTS.items()
                       if role_history or not code.startswith('ROLE_')]}
