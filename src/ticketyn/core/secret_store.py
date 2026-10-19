"""Versioned local AES-256-GCM secrets; no database, HTTP or mail dependencies.

Key provisioning is explicit. Normal encryption/decryption never creates files.
Only the provisioning CLI writes keys; the service needs read access alone.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass, field
import grp
import json
import os
from pathlib import Path
import re
import secrets
import stat

from cryptography.exceptions import InvalidTag, UnsupportedAlgorithm
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ticketyn.core.config import DEFAULT_MAIL_KEYS_PATH, get_settings

MAX_SECRET_BYTES = 65536
MAX_KEY_FILE_BYTES = 65536
KEY_ID = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')


class SecretError(Exception):
    """Safe diagnostic only; never attach input, key material or raw exceptions."""


class KeyFileError(SecretError):
    pass


class EncryptionError(SecretError):
    pass


class DecryptionError(SecretError):
    pass


@dataclass(frozen=True)
class _KeyRing:
    active_key_id: str
    keys: dict[str, bytes] = field(repr=False)

    def document(self):
        return {'version': 1, 'active_key_id': self.active_key_id,
                'keys': {key_id: _encode(key) for key_id, key in self.keys.items()}}


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode('ascii')


def _decode(value) -> bytes:
    if not isinstance(value, str):
        raise ValueError
    decoded = base64.b64decode(value, altchars=b'-_', validate=True)
    if _encode(decoded) != value:
        raise ValueError
    return decoded


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _document(value, expected_keys):
    result = json.loads(value, object_pairs_hook=_unique_object)
    if not isinstance(result, dict) or result.keys() != expected_keys:
        raise ValueError
    if type(result['version']) is not int or result['version'] != 1:
        raise ValueError
    return result


def _private_directory(info):
    if info.st_uid not in {0, os.geteuid()} or stat.S_IMODE(info.st_mode) & 0o027:
        raise ValueError


def _reject_extended_acl(descriptor):
    # Mode bits alone do not rule out additional named readers through POSIX ACLs.
    if {'system.posix_acl_access', 'system.posix_acl_default'} & set(os.listxattr(descriptor)):
        raise ValueError


def _parent_fd(path: Path) -> int:
    """Anchor all traversal to directory descriptors; reject symlink components."""
    if not path.is_absolute() or '..' in path.parts or not path.name:
        raise ValueError
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in path.parts[1:-1]:
            next_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_fd
            info = os.fstat(descriptor)
            # Shared sticky ancestors such as /tmp are allowed, never the final parent.
            if info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX:
                raise ValueError
        _private_directory(os.fstat(descriptor))
        _reject_extended_acl(descriptor)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _read_key_ring(path: Path) -> _KeyRing:
    try:
        parent = _parent_fd(path)
        try:
            descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(descriptor, 'rb') as stream:
                info = os.fstat(stream.fileno())
                mode = stat.S_IMODE(info.st_mode)
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or info.st_uid not in {0, os.geteuid()}
                        or mode & ~0o640 or not mode & 0o400):
                    raise ValueError
                if mode & 0o040 and os.geteuid() != 0 and info.st_gid not in {os.getegid(), *os.getgroups()}:
                    raise ValueError
                _reject_extended_acl(stream.fileno())
                content = stream.read(MAX_KEY_FILE_BYTES + 1)
        finally:
            os.close(parent)
        if len(content) > MAX_KEY_FILE_BYTES:
            raise ValueError
        doc = _document(content, {'version', 'active_key_id', 'keys'})
        active = doc['active_key_id']
        if not isinstance(active, str) or not KEY_ID.fullmatch(active):
            raise ValueError
        if not isinstance(doc['keys'], dict) or not 1 <= len(doc['keys']) <= 32:
            raise ValueError
        keys = {}
        for key_id, encoded in doc['keys'].items():
            if not KEY_ID.fullmatch(key_id):
                raise ValueError
            key = _decode(encoded)
            if len(key) != 32:
                raise ValueError
            keys[key_id] = key
        if active not in keys:
            raise ValueError
        return _KeyRing(active, keys)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        raise KeyFileError('El archivo de claves no está disponible o no es válido y seguro.') from None


def _write_new(path: Path, ring: _KeyRing, group_id: int | None):
    """Publish a complete file atomically, without ever replacing an existing path."""
    parent = None
    temporary = '.keys-' + secrets.token_hex(16) + '.tmp'
    created = False
    try:
        if group_id is not None and (type(group_id) is not int or group_id < 0):
            raise ValueError
        parent = _parent_fd(path)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=parent)
        created = True
        with os.fdopen(descriptor, 'wb') as stream:
            if group_id is not None:
                os.fchown(stream.fileno(), -1, group_id)
            os.fchmod(stream.fileno(), 0o640 if group_id is not None else 0o600)
            stream.write((json.dumps(ring.document(), separators=(',', ':')) + '\n').encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        # Unlike replace(), link() fails if the destination exists, even as a symlink.
        os.link(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        os.unlink(temporary, dir_fd=parent)
        created = False
        os.fsync(parent)
    except (OSError, ValueError, TypeError):
        raise KeyFileError('No se pudo publicar el archivo de claves de forma segura; no se sobrescriben destinos existentes.') from None
    finally:
        if parent is not None:
            try:
                if created:
                    os.unlink(temporary, dir_fd=parent)
            except OSError:
                raise KeyFileError('No se pudo limpiar un archivo temporal privado; requiere revisión administrativa.') from None
            finally:
                os.close(parent)


def create_key_file(path: Path | str, *, group_id: int | None = None) -> str:
    """Explicit initial provisioning only, not recovery or rotation."""
    key_id = secrets.token_hex(16)
    ring = _KeyRing(key_id, {key_id: AESGCM.generate_key(bit_length=256)})
    _write_new(Path(path), ring, group_id)
    return key_id


def copy_key_file(source: Path | str, destination: Path | str, *, group_id: int | None = None) -> str:
    """Validate and atomically back up/restore the same keys, without replacement."""
    ring = _read_key_ring(Path(source))
    _write_new(Path(destination), ring, group_id)
    return ring.active_key_id


def validate_key_file(path: Path | str) -> str:
    """Return the non-secret active identifier, never keys."""
    return _read_key_ring(Path(path)).active_key_id


def _associated_data(key_id: str, context: str) -> bytes:
    if not isinstance(context, str) or not context or len(context.encode('utf-8')) > 512:
        raise ValueError
    return json.dumps(['ticketyn-secret', 1, key_id, context], separators=(',', ':')).encode('utf-8')


class SecretCipher:
    def __init__(self, key_file: Path | str):
        self.key_file = Path(key_file)

    def encrypt(self, value: str, *, context: str) -> str:
        ring = _read_key_ring(self.key_file)
        try:
            if not isinstance(value, str):
                raise ValueError
            plaintext = value.encode('utf-8')
            if len(plaintext) > MAX_SECRET_BYTES:
                raise ValueError
            nonce = os.urandom(12)
            ciphertext = AESGCM(ring.keys[ring.active_key_id]).encrypt(
                nonce, plaintext, _associated_data(ring.active_key_id, context))
            return json.dumps({'version': 1, 'key_id': ring.active_key_id,
                               'nonce': _encode(nonce), 'ciphertext': _encode(ciphertext)}, separators=(',', ':'))
        except (OSError, ValueError, TypeError, UnicodeError, UnsupportedAlgorithm):
            raise EncryptionError('No se pudo cifrar el secreto.') from None

    def decrypt(self, value: str, *, context: str) -> str:
        ring = _read_key_ring(self.key_file)
        try:
            if not isinstance(value, str) or len(value) > 100000:
                raise ValueError
            doc = _document(value, {'version', 'key_id', 'nonce', 'ciphertext'})
            key_id = doc['key_id']
            if not isinstance(key_id, str) or key_id not in ring.keys:
                raise ValueError
            nonce, ciphertext = _decode(doc['nonce']), _decode(doc['ciphertext'])
            if len(nonce) != 12 or not 16 <= len(ciphertext) <= MAX_SECRET_BYTES + 16:
                raise ValueError
            return AESGCM(ring.keys[key_id]).decrypt(nonce, ciphertext, _associated_data(key_id, context)).decode('utf-8')
        except (InvalidTag, ValueError, TypeError, UnicodeError, RecursionError, UnsupportedAlgorithm):
            raise DecryptionError('No se pudo autenticar o descifrar el secreto.') from None


def get_secret_cipher() -> SecretCipher:
    """Lazy access: application startup does not require a key file."""
    return SecretCipher(get_settings().mail_keys_path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Aprovisionamiento y copia independiente de claves Ticketyn; nunca muestra claves.')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'check'):
        command = commands.add_parser(name)
        command.add_argument('--path', type=Path, default=DEFAULT_MAIL_KEYS_PATH)
        if name == 'init':
            command.add_argument('--group')
    command = commands.add_parser('copy')
    command.add_argument('--source', type=Path, required=True)
    command.add_argument('--destination', type=Path, required=True)
    command.add_argument('--group')
    args = parser.parse_args(argv)
    try:
        group = grp.getgrnam(args.group).gr_gid if getattr(args, 'group', None) else None
        if args.command == 'init':
            create_key_file(args.path, group_id=group)
        elif args.command == 'copy':
            copy_key_file(args.source, args.destination, group_id=group)
        else:
            validate_key_file(args.path)
    except (SecretError, KeyError):
        print('No se completó la operación: revisa existencia, formato, propietario, grupo y permisos de los archivos.')
        return 1
    print('Operación de claves completada; no se muestra material secreto.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
