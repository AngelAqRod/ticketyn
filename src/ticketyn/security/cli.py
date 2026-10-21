"""Server-local bootstrap/recovery. Passwords are prompted, never CLI arguments."""
import argparse
import getpass
import os
import stat
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
from ticketyn.core.config import Settings
from ticketyn.security.passwords import PasswordBusy
from ticketyn.security.service import bootstrap, recover_superadmin


def settings_from_file(path):
    if path is None:
        # Never silently rely on the administrative shell's working directory .env.
        return Settings(_env_file=None)
    target = Path(path)
    with os.fdopen(os.open(target, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid not in {os.getuid(), 0}:
            raise ValueError('El archivo de configuración debe ser privado y pertenecer al ejecutor o a root')
        # Read via the already checked descriptor; avoid a second path lookup.
        from dotenv import dotenv_values
        from io import StringIO
        values = dotenv_values(stream=StringIO(handle.read(65536).decode('utf-8')))
    return Settings(_env_file=None, **{key.lower(): value for key, value in values.items() if value is not None})


def main(argv=None):
    parser = argparse.ArgumentParser(description='Preparación y recuperación local de seguridad Ticketyn')
    parser.add_argument('--config', help='Archivo privado de entorno; si se omite, utiliza únicamente variables de entorno')
    commands = parser.add_subparsers(dest='command', required=True)
    initial = commands.add_parser('bootstrap', help='Habilitar el primer Superadministrador en un Responsable existente')
    target = initial.add_mutually_exclusive_group(required=True)
    target.add_argument('--responsible-id', type=int, help='Responsable existente (preferido)')
    target.add_argument('--responsible-name', help='Crear explícitamente un Responsable en el catálogo existente')
    initial.add_argument('--username', required=True)
    commands.add_parser('recover-superadmin', help='Restablecer la contraseña del único Superadministrador')
    args = parser.parse_args(argv)
    engine = None
    try:
        settings = settings_from_file(args.config)
        password = getpass.getpass('Contraseña temporal: ')
        if password != getpass.getpass('Confirmar contraseña temporal: '):
            raise ValueError('Las contraseñas no coinciden')
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with Session(engine) as session:
            source = f'CLI uid={os.getuid()}'
            if args.command == 'bootstrap':
                bootstrap(session, args.responsible_id, args.username, password, source, responsible_name=args.responsible_name)
            else:
                recover_superadmin(session, password, source)
            session.commit()
    except (ValueError, OSError, SQLAlchemyError, HTTPException, PasswordBusy):
        # SQL/validation exceptions may embed parameters. Never print their repr.
        parser.exit(1, 'No se pudo completar la operación. Verifica configuración, Responsable y requisitos de bootstrap/recuperación.\n')
    finally:
        if engine is not None:
            engine.dispose()
    print('Operación completada. Se requiere cambiar la contraseña en el próximo acceso.')

if __name__ == '__main__':
    main()
