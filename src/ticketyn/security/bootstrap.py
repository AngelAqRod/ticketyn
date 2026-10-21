"""Administrative bootstrap of the initial superadmin for Ticketyn v0.7.0.

This module provides inspection, transactional creation, and interactive bootstrap
of the initial Superadministrator account following technical updates or fresh installs.
Passwords are never passed via CLI arguments and never logged.
"""
from __future__ import annotations

import argparse
import getpass
import os
import stat
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Sequence

from argon2 import Type, extract_parameters
from argon2.exceptions import InvalidHashError
from fastapi import HTTPException
from sqlalchemy import create_engine, func, literal, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ticketyn.core.config import Settings
from ticketyn.models import Responsible
from ticketyn.models.security import SecurityConfig, SecurityRole
from ticketyn.security.passwords import PasswordBusy, hash_password, validate_password
from ticketyn.security.service import audit, lock_security, principal, seed_foundation


class SuperadminStatus(str, Enum):
    VALID_EXISTS = 'VALID_EXISTS'
    NONE_EXIST = 'NONE_EXIST'
    INCONSISTENT = 'INCONSISTENT'


@dataclass(frozen=True)
class SuperadminRecord:
    id: int
    username: str | None
    name: str
    active: bool
    access_granted: bool
    operational_selectable: bool
    has_password: bool
    can_authenticate: bool


@dataclass(frozen=True)
class StatusReport:
    status: SuperadminStatus
    message: str
    valid_superadmins: tuple[SuperadminRecord, ...] = ()
    inconsistent_records: tuple[SuperadminRecord, ...] = ()
    details: tuple[str, ...] = ()


class BootstrapError(Exception):
    """Base error for bootstrap operations."""


class InconsistentStateError(BootstrapError):
    """Raised when the database has an inconsistent administrative state."""


def inspect_superadmin_status(session: Session) -> StatusReport:
    """Inspects the current state of Superadministrators in PostgreSQL.

    Evaluates whether:
      - A valid, active, fully configured superadmin exists (VALID_EXISTS).
      - No superadmin account exists (NONE_EXIST).
      - Inconsistent or incomplete superadmin records exist (INCONSISTENT).
    """
    seed_foundation(session)

    config = session.get(SecurityConfig, 1)
    if config is None:
        return StatusReport(
            status=SuperadminStatus.INCONSISTENT,
            message='Configuración de seguridad no encontrada (SecurityConfig id=1 ausente).',
            details=('Falta la fila singleton en security_config. Ejecuta migraciones Alembic.',),
        )

    role = session.scalar(select(SecurityRole).where(SecurityRole.code == 'SUPERADMIN'))
    if role is None:
        return StatusReport(
            status=SuperadminStatus.INCONSISTENT,
            message='Rol SUPERADMIN no encontrado en la base de datos.',
            details=('El rol SUPERADMIN no existe en security_roles. Ejecuta migraciones Alembic.',),
        )

    records = session.scalars(
        select(Responsible).where(Responsible.security_role_id == role.id).order_by(Responsible.id)
    ).all()

    if not records:
        return StatusReport(
            status=SuperadminStatus.NONE_EXIST,
            message='No existe ningún superadministrador configurado en el sistema.',
        )

    valid_list: list[SuperadminRecord] = []
    inconsistent_list: list[SuperadminRecord] = []
    details_list: list[str] = []

    for r in records:
        has_pwd = bool(r.password_hash)
        has_usr = bool(r.username)
        p = principal(session, r.id)
        can_auth = p is not None

        rec = SuperadminRecord(
            id=r.id,
            username=r.username,
            name=r.name,
            active=bool(r.active),
            access_granted=bool(r.access_granted),
            operational_selectable=bool(r.operational_selectable),
            has_password=has_pwd,
            can_authenticate=can_auth,
        )

        # Check conditions for a valid, operative superadmin
        issues = []
        if not r.active:
            issues.append('cuenta inactiva')
        if not r.access_granted:
            issues.append('acceso deshabilitado (access_granted=False)')
        if not has_usr:
            issues.append('sin nombre de usuario asignado')
        if not has_pwd:
            issues.append('sin credenciales de contraseña')
        else:
            try:
                parameters = extract_parameters(r.password_hash)
                valid_format = parameters.type == Type.ID and parameters.salt_len > 0 and parameters.hash_len > 0
            except InvalidHashError:
                valid_format = False
            if not valid_format:
                issues.append('credenciales con formato Argon2id inválido')
        if not can_auth and not issues:
            issues.append('no cumple las condiciones requeridas para autenticarse')

        if not issues and can_auth:
            valid_list.append(rec)
        else:
            inconsistent_list.append(rec)
            details_list.append(
                f"Responsable ID={r.id} (nombre='{r.name}', usuario='{r.username or ''}'): "
                + ', '.join(issues)
            )

    if inconsistent_list:
        msg = (
            f"Se encontraron {len(inconsistent_list)} registro(s) administrativo(s) inconsistente(s). "
            'El sistema no puede determinar el estado de forma segura.'
        )
        return StatusReport(
            status=SuperadminStatus.INCONSISTENT,
            message=msg,
            valid_superadmins=tuple(valid_list),
            inconsistent_records=tuple(inconsistent_list),
            details=tuple(details_list),
        )

    return StatusReport(
        status=SuperadminStatus.VALID_EXISTS,
        message=f'Ya existe {len(valid_list)} superadministrador(es) válido(s) y operativo(s).',
        valid_superadmins=tuple(valid_list),
    )


def create_superadmin(
    session: Session,
    username: str,
    password: str,
    *,
    responsible_name: str | None = None,
    responsible_id: int | None = None,
    source: str = 'CLI',
) -> tuple[Responsible, bool]:
    """Creates or configures the initial superadministrator under transactional lock.

    Guarantees concurrency safety and idempotency:
      - Locks the singleton security_config row.
      - Re-evaluates inspect_superadmin_status within the transaction.
      - If a valid superadmin was created concurrently, returns (admin, False) without error.
      - If state is inconsistent, raises InconsistentStateError without altering DB.
      - If none exists, creates the superadmin and returns (admin, True).
    """
    if not isinstance(username, str) or not username or len(username) > 100 or any(ord(char) < 32 or ord(char) == 127 for char in username):
        raise ValueError('El usuario debe contener entre 1 y 100 caracteres sin caracteres de control')
    validate_password(password)

    seed_foundation(session)
    lock_security(session)

    # Re-evaluate status inside the exclusive lock
    report = inspect_superadmin_status(session)
    if report.status == SuperadminStatus.VALID_EXISTS:
        # Already satisfied (idempotent / concurrent win)
        admin = session.get(Responsible, report.valid_superadmins[0].id)
        return admin, False

    if report.status == SuperadminStatus.INCONSISTENT:
        raise InconsistentStateError(
            report.message + '\nDetalles:\n  - ' + '\n  - '.join(report.details)
        )

    # Validate username uniqueness (case-insensitive UTF-8 collation)
    existing_user_id = session.scalar(
        select(Responsible.id).where(
            func.lower(Responsible.username.collate('C.utf8')) == func.lower(literal(username).collate('C.utf8'))
        )
    )
    if existing_user_id:
        raise ValueError(f"El nombre de usuario '{username}' ya está reservado o en uso por otro responsable")

    encoded_hash = hash_password(password)
    role = session.scalar(select(SecurityRole).where(SecurityRole.code == 'SUPERADMIN'))

    if responsible_id is None:
        if not responsible_name or not responsible_name.strip():
            raise ValueError('Debe especificar un nombre para el responsable en el catálogo')
        from ticketyn.schemas.responsible import ResponsibleCreate
        from ticketyn.api.crud import validate_catalog_name

        values = ResponsibleCreate(name=responsible_name.strip()).model_dump()
        item = Responsible(**values)
        validate_catalog_name(session, item)
        session.add(item)
        session.flush()
    else:
        item = session.scalar(
            select(Responsible).where(Responsible.id == responsible_id).with_for_update(of=Responsible)
        )
        if item is None:
            raise ValueError(f'No se encontró el responsable con ID {responsible_id}')
        if not item.active:
            raise ValueError('El responsable seleccionado no está activo')
        if item.username:
            raise ValueError('El responsable seleccionado ya tiene una cuenta asignada')

    item.username = username
    item.password_hash = encoded_hash
    item.security_role_id = role.id
    item.access_granted = True
    item.password_change_required = True
    item.access_revision += 1
    item.active = True
    item.operational_selectable = False

    audit(session, 'BOOTSTRAP_SUPERADMIN', item.id, source=source)
    session.flush()

    # Confirm that user is ready and capable of authentication
    p = principal(session, item.id)
    if p is None:
        raise RuntimeError('El superadministrador creado no cumple los requisitos de autenticación')

    return item, True


def settings_from_file(path: str | None) -> Settings:
    """Securely loads Settings from an explicitly specified private environment file."""
    if path is None:
        return Settings(_env_file=None)
    target = Path(path)
    with os.fdopen(os.open(target, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid not in {os.getuid(), 0}:
            raise ValueError('El archivo de configuración debe ser privado (0600) y pertenecer al ejecutor o a root')
        from dotenv import dotenv_values
        from io import StringIO
        values = dotenv_values(stream=StringIO(handle.read(65536).decode('utf-8')))
    return Settings(_env_file=None, **{key.lower(): value for key, value in values.items() if value is not None})


def read_password(prompt: str) -> str:
    """Reads password without terminal echo when interactive, or reads line from stdin if piped."""
    try:
        if not sys.stdin.isatty():
            line = sys.stdin.readline()
            if line:
                return line.rstrip('\r\n')
    except (OSError, ValueError):
        pass
    return getpass.getpass(prompt)


def interactive_bootstrap(
    session: Session,
    source: str = 'CLI',
    *,
    pre_username: str | None = None,
    pre_name: str | None = None,
    pre_responsible_id: int | None = None,
) -> int:
    """Executes the interactive bootstrap procedure according to specification."""
    # First inspect status outside lock for immediate diagnostic feedback
    report = inspect_superadmin_status(session)

    if report.status == SuperadminStatus.VALID_EXISTS:
        admin = report.valid_superadmins[0]
        print('======================================================================')
        print('INICIALIZACIÓN ADMINISTRATIVA: Ya satisfecha')
        print('======================================================================')
        print('Ya existe un Superadministrador válido, activo y configurado en el sistema.')
        print(f'  ID:                 {admin.id}')
        print(f'  Nombre:             {admin.name}')
        print(f'  Usuario:            {admin.username}')
        print(f'  Estado:             Activo (access_granted=True)')
        print(f'  Disponibilidad:     operational_selectable={admin.operational_selectable}')
        print('----------------------------------------------------------------------')
        print('No se realizaron cambios ni se crearon usuarios duplicados.')
        print('Para acceder, utilice las credenciales de este superadministrador.')
        print('======================================================================')
        return 0

    if report.status == SuperadminStatus.INCONSISTENT:
        print('======================================================================', file=sys.stderr)
        print('ERROR: ESTADO ADMINISTRATIVO INCONSISTENTE DETECTADO', file=sys.stderr)
        print('======================================================================', file=sys.stderr)
        print(report.message, file=sys.stderr)
        print('\nDetalles:', file=sys.stderr)
        for d in report.details:
            print(f'  - {d}', file=sys.stderr)
        print('\nPor razones de seguridad:', file=sys.stderr)
        print('  - No se aplicaron modificaciones automáticas a la base de datos.', file=sys.stderr)
        print('  - No se elevaron privilegios ni se sobrescribieron contraseñas.', file=sys.stderr)
        print('  - Realice una revisión manual de los registros administrativos.', file=sys.stderr)
        print('======================================================================', file=sys.stderr)
        return 1

    # Status is NONE_EXIST (Caso B)
    print('======================================================================')
    print('TICKETYN v0.7.0 — INICIALIZACIÓN DEL SUPERADMINISTRADOR INICIAL')
    print('======================================================================')
    print('No se encontró ningún superadministrador en el sistema.')
    print('Se procederá a crear la cuenta del primer superadministrador.\n')

    # Username
    username = (pre_username or '').strip()
    while not username:
        username = input('Nombre de usuario (login): ').strip()
        if not username:
            print('El nombre de usuario no puede estar vacío.')

    if len(username) > 100 or any(ord(c) < 32 or ord(c) == 127 for c in username):
        print('Error: El nombre de usuario debe tener entre 1 y 100 caracteres sin caracteres de control.', file=sys.stderr)
        return 1

    # Responsible Name / Existing Responsible ID
    responsible_name = (pre_name or '').strip() if pre_name else None
    responsible_id = pre_responsible_id

    if responsible_id is None and not responsible_name:
        default_name = f'Superadministrador ({username})'
        entered_name = input(f'Nombre completo para el catálogo de responsables [{default_name}]: ').strip()
        responsible_name = entered_name if entered_name else default_name

    # Passwords (prompt without echo)
    try:
        pwd1 = read_password('Contraseña del superadministrador: ')
        pwd2 = read_password('Confirmar contraseña: ')
    except (KeyboardInterrupt, EOFError):
        print('\nOperación cancelada por el usuario.', file=sys.stderr)
        return 1

    if pwd1 != pwd2:
        print('Error: Las contraseñas no coinciden.', file=sys.stderr)
        return 1

    try:
        validate_password(pwd1)
    except ValueError as val_err:
        print(f'Error en contraseña: {val_err}', file=sys.stderr)
        return 1

    # Transactional execution
    try:
        admin, created = create_superadmin(
            session,
            username=username,
            password=pwd1,
            responsible_name=responsible_name,
            responsible_id=responsible_id,
            source=source,
        )
        session.commit()
    except (ValueError, InconsistentStateError, RuntimeError) as err:
        session.rollback()
        print(f'Error durante la inicialización: {err}', file=sys.stderr)
        return 1
    except SQLAlchemyError:
        session.rollback()
        print('Error de base de datos durante la inicialización. No se realizaron cambios parciales.', file=sys.stderr)
        return 1
    except PasswordBusy:
        session.rollback()
        print('Error: El subsistema criptográfico está ocupado. Intente de nuevo más tarde.', file=sys.stderr)
        return 1

    print('\n======================================================================')
    if created:
        print('SUPERADMINISTRADOR INICIAL CREADO EXITOSAMENTE')
        print('======================================================================')
        print(f'  ID Responsable:     {admin.id}')
        print(f'  Nombre en catálogo: {admin.name}')
        print(f'  Usuario (login):    {admin.username}')
        print(f'  Rol asignado:       Superadministrador')
        print(f'  Estado:             Activo (access_granted=True)')
        print(f'  Disp. Operativa:    operational_selectable=False')
        print('----------------------------------------------------------------------')
        print('NOTA: Por seguridad, se requerirá cambiar la contraseña temporal')
        print('      en el primer inicio de sesión.')
    else:
        print('INICIALIZACIÓN YA COMPLETADA (PROCESO CONCURRENTE)')
        print('======================================================================')
        print('Otro proceso completó la inicialización concurrentemente.')
        print(f'  ID:      {admin.id}')
        print(f'  Usuario: {admin.username}')
    print('======================================================================')
    return 0


def check_status_cli(session: Session) -> int:
    """Non-interactive check of superadmin status."""
    report = inspect_superadmin_status(session)
    if report.status == SuperadminStatus.VALID_EXISTS:
        admin = report.valid_superadmins[0]
        print(f"OK: Superadministrador válido y operativo presente (ID={admin.id}, usuario='{admin.username}').")
        return 0
    elif report.status == SuperadminStatus.NONE_EXIST:
        print('INFO: No existe un superadministrador configurado en el sistema.')
        return 3
    else:
        print(f'ERROR: {report.message}', file=sys.stderr)
        for d in report.details:
            print(f'  - {d}', file=sys.stderr)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Ticketyn v0.7.0 — Bootstrap seguro del superadministrador inicial',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--config',
        help='Ruta al archivo privado de variables de entorno (.env o ticketyn.env). Permisos requeridos: 0600.',
    )
    parser.add_argument(
        '--check',
        action='store_true',
        help='Comprobar el estado del superadministrador sin solicitar datos ni realizar modificaciones.',
    )
    parser.add_argument(
        '--username',
        help='Nombre de usuario para el superadministrador inicial.',
    )
    parser.add_argument(
        '--name',
        help='Nombre completo para el registro en el catálogo de responsables.',
    )
    parser.add_argument(
        '--responsible-id',
        type=int,
        help='ID de un responsable existente activo sin cuenta para asignarle el rol de superadministrador.',
    )

    args = parser.parse_args(argv)

    engine = None
    try:
        settings = settings_from_file(args.config)
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        source = f'CLI uid={os.getuid()}'

        with Session(engine) as session:
            if args.check:
                return check_status_cli(session)
            return interactive_bootstrap(
                session,
                source=source,
                pre_username=args.username,
                pre_name=args.name,
                pre_responsible_id=args.responsible_id,
            )
    except (ValueError, OSError):
        # Validation exceptions can include DATABASE_URL and its password.
        print('Error de configuración: revise el archivo privado, sus permisos y el formato de las variables. No se muestran sus valores.', file=sys.stderr)
        return 2
    except SQLAlchemyError:
        print('Error de conexión con PostgreSQL. Verifique que el servicio esté activo y DATABASE_URL sea correcta.', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('\nOperación interrumpida por el usuario.', file=sys.stderr)
        return 130
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    sys.exit(main())
