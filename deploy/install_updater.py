"""Publish the complete administrative updater, independently of app/current.

No application/DB/service mutations. CLI is root-only; tests use isolated paths.
"""
import importlib.util
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile

_spec = importlib.util.spec_from_file_location('updater_release_identity', Path(__file__).with_name('release_identity.py'))
ri = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ri)

FILES = ('update.sh', 'backup.sh', 'deploy/update_support.py',
         'deploy/restore_support.py', 'deploy/release_identity.py')
FORMAT = 'ticketyn-admin-updater-v1'


def secure(path, directory=False):
    path = Path(path)
    ri.secure_ancestors(path)
    info = path.lstat()
    if (not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            or info.st_uid != os.geteuid() or info.st_gid != os.getegid()
            or info.st_mode & 0o022 or (not directory and info.st_nlink != 1)):
        raise ValueError('Tipo, propietario o permisos inseguros: '+str(path))
    return info


def mkdir(path):
    path = Path(path)
    if not path.exists() and not path.is_symlink():
        secure(path.parent, directory=True)
        path.mkdir(mode=0o755)
        sync_directory(path)
        sync_directory(path.parent)
    secure(path, directory=True)


def snapshot(source):
    values = {}
    for name in FILES:
        path = Path(source)/name
        if any(parent.is_symlink() for parent in path.parents):
            raise ValueError('Symlink en fuente del updater: '+str(path))
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('Archivo fuente inesperado: '+str(path))
            values[name] = stream.read()
    return values


def identity(values):
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in values.items()}
    key = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return key, {'format': FORMAT, 'files': hashes}


def validate_bundle(bundle):
    secure(bundle, directory=True)
    secure(bundle/'deploy', directory=True)
    secure(bundle/'manifest.json')
    for name in FILES:
        secure(bundle/name)
    expected = set(FILES) | {'deploy', 'manifest.json'}
    if {str(p.relative_to(bundle)) for p in bundle.rglob('*')} != expected:
        raise ValueError('Contenido inesperado en bundle del updater.')
    key, manifest = identity(snapshot(bundle))
    if bundle.name != key or json.loads((bundle/'manifest.json').read_text()) != manifest:
        raise ValueError('Bundle del updater modificado o identidad inválida.')
    return key


def launcher(bundle):
    # Paths are canonical, root-controlled and shell-quoted by JSON restrictions
    # below (production paths contain no quote/expansion characters).
    path = str(bundle/'update.sh')
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+', path):
        raise ValueError('Ruta no admitida para el lanzador del updater.')
    return f'#!/bin/sh\n# {FORMAT}\nexec /bin/bash "{path}" "$@"\n'.encode()


def sync_directory(path):
    before = secure(path, directory=True)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        actual = os.fstat(fd)
        if (actual.st_dev, actual.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError('Directorio sustituido durante fsync.')
        os.fsync(fd)
    finally:
        os.close(fd)


def rename_exclusive(source, target):
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(target))


def write(path, data, mode):
    with open(path, 'xb') as stream:
        stream.write(data)
        stream.flush()
        os.fchmod(stream.fileno(), mode)
        os.fsync(stream.fileno())


def install(source, base=Path('/opt/ticketyn'), command=Path('/usr/local/sbin/ticketyn-update')):
    base, command = Path(base), Path(command)
    secure(base, directory=True)
    secure(command.parent, directory=True)
    mkdir(base/'admin')
    mkdir(base/'admin/updater')
    bundles = base/'admin/updater'
    lock = bundles/'.install.lock'
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'r+') as stream:
        secure(lock)
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return publish(source, bundles, command)


def publish(source, bundles, command):
    values = snapshot(source)
    key, manifest = identity(values)
    bundle = bundles/key
    previous = None
    if command.exists() or command.is_symlink():
        previous = secure(command)
        data = command.read_bytes()
        match = re.fullmatch(rb'#!/bin/sh\n# ticketyn-admin-updater-v1\nexec /bin/bash "([^"\n]+)" "\$@"\n', data)
        if not match:
            raise ValueError('El comando administrativo existente es ajeno; no se reemplaza.')
        old = Path(os.fsdecode(match[1])).parent
        if old.parent != bundles or validate_bundle(old) != old.name or data != launcher(old):
            raise ValueError('Identidad del comando administrativo existente inválida.')
    if bundle.exists() or bundle.is_symlink():
        validate_bundle(bundle)
    else:
        staging = Path(tempfile.mkdtemp(prefix='.prepare-', dir=bundles))
        try:
            (staging/'deploy').mkdir(mode=0o755)
            for name, data in values.items():
                write(staging/name, data, 0o755 if name.endswith('.sh') else 0o644)
            write(staging/'manifest.json', json.dumps(manifest, sort_keys=True).encode()+b'\n', 0o644)
            sync_directory(staging/'deploy'); sync_directory(staging)
            staging.chmod(0o755)
            sync_directory(staging)
            rename_exclusive(staging, bundle)
            sync_directory(bundles)
        finally:
            if staging.exists():
                shutil.rmtree(staging)  # Only this mkdtemp-owned unpublished directory.
        validate_bundle(bundle)
    expected = launcher(bundle)
    if previous is not None and command.read_bytes() == expected:
        validate_publication(base=bundles.parent.parent, command=command, bundle=bundle)
        return bundle
    fd, name = tempfile.mkstemp(prefix='.ticketyn-update-', dir=command.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(expected); stream.flush()
            os.fchmod(stream.fileno(), 0o755); os.fsync(stream.fileno())
        if previous is None:
            rename_exclusive(temporary, command)
        else:
            now = secure(command)
            if (now.st_dev, now.st_ino, now.st_mtime_ns, now.st_size) != (previous.st_dev, previous.st_ino, previous.st_mtime_ns, previous.st_size):
                raise ValueError('El comando cambió concurrentemente; no se reemplaza.')
            os.replace(temporary, command)
        sync_directory(command.parent)
    finally:
        temporary.unlink(missing_ok=True)
    validate_publication(base=bundles.parent.parent, command=command, bundle=bundle)
    return bundle


def validate_publication(base, command, bundle):
    validate_bundle(bundle)
    secure(command)
    if ri.read_regular(command) != launcher(bundle) or stat.S_IMODE(command.stat().st_mode) != 0o755:
        raise ValueError('Lanzador administrativo inválido.')
    for path in [command, bundle/'manifest.json', *(bundle/name for name in FILES)]:
        info = secure(path)
        expected = 0o755 if path == command or path.suffix == '.sh' else 0o644
        if stat.S_IMODE(info.st_mode) != expected:
            raise ValueError('Permisos del bundle inesperados.')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            if (os.fstat(fd).st_dev, os.fstat(fd).st_ino) != (info.st_dev, info.st_ino):
                raise ValueError('Bundle sustituido durante verificación.')
            os.fsync(fd)
        finally: os.close(fd)
    for path in (bundle/'deploy', bundle, bundle.parent, base/'admin', base, command.parent):
        secure(path, directory=True)
        sync_directory(path)


if __name__ == '__main__':
    try:
        if os.geteuid() != 0 or os.getegid() != 0 or len(sys.argv) != 2:
            raise ValueError('Ejecuta como root: python3 -I deploy/install_updater.py /ruta/release')
        bundle = install(Path(sys.argv[1]))
        print('✓ ticketyn-update instalado con bundle verificado: '+str(bundle))
    except Exception as error:
        print('Error: '+(str(error) if isinstance(error, ValueError) else 'No se pudo publicar el updater; se conserva el comando existente.'), file=sys.stderr)
        sys.exit(1)
