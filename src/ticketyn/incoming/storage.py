"""Private, immutable document storage; callers own the database transaction."""
from contextlib import contextmanager
import fcntl
import hashlib
from io import BytesIO
import os
from pathlib import Path
import re
import time
from uuid import uuid4
from zipfile import ZipFile, BadZipFile

from sqlalchemy import select

from ticketyn.incoming.config import IncomingSettings
from ticketyn.models.installation_orders import InstallationDocument


def validate_document(content: bytes, name: str, *, original=False) -> str:
    if not name or len(name) > 255 or name in ('.', '..') or any(c in name for c in ('/', '\\')) or any(ord(c) < 32 for c in name):
        raise ValueError('Invalid document filename')
    if len(content) > IncomingSettings.from_env().max_bytes:
        raise ValueError('Document exceeds configured size limit')
    extension = Path(name).suffix.lower()
    if original:
        return 'message/rfc822'
    if extension == '.pdf' and content.startswith(b'%PDF-'):
        return 'application/pdf'
    if extension == '.png' and content.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if extension in ('.jpg', '.jpeg') and content.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    office = {'.docx': ('word/', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
              '.xlsx': ('xl/', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
              '.pptx': ('ppt/', 'application/vnd.openxmlformats-officedocument.presentationml.presentation')}
    if extension in office:
        try:
            with ZipFile(BytesIO(content)) as archive:
                names = archive.namelist()
                if '[Content_Types].xml' in names and any(n.startswith(office[extension][0]) for n in names):
                    return office[extension][1]
        except BadZipFile:
            pass
    if extension in ('.doc', '.xls', '.ppt') and content.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        return {'.doc': 'application/msword', '.xls': 'application/vnd.ms-excel', '.ppt': 'application/vnd.ms-powerpoint'}[extension]
    raise ValueError('Unsupported document type or content does not match filename')


def _root():
    root = IncomingSettings.from_env().storage_dir
    if root.is_symlink():
        raise ValueError('Storage directory must not be a symbolic link')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.resolve() != root:
        raise ValueError('Storage path must not contain symbolic links')
    return root


@contextmanager
def storage_lock():
    """Prevent cleanup from racing an uncommitted storage transaction."""
    path = _root() / '.lock'
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def save_document(session, *, content: bytes, name: str, order_id=None, request_id=None, original=False):
    if (order_id is None) == (request_id is None):
        raise ValueError('A document must have exactly one origin')
    media_type = validate_document(content, name, original=original)
    root = _root()
    key = uuid4().hex
    fd = os.open(root / key, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    document = InstallationDocument(order_id=order_id, request_id=request_id, original_name=name,
        media_type=media_type, size=len(content), checksum=hashlib.sha256(content).hexdigest(), storage_key=key)
    session.add(document)
    return document


def document_path(document):
    if not re.fullmatch(r'[0-9a-f]{32}', document.storage_key):
        raise ValueError('Invalid storage key')
    path = _root() / document.storage_key
    if path.is_symlink() or not path.is_file():
        raise ValueError('Original document is unavailable')
    return path


def recover_storage(session, *, grace_seconds=86400):
    """Report missing originals and remove old unreferenced immutable files."""
    with storage_lock():
        documents = list(session.scalars(select(InstallationDocument)))
        keys = {d.storage_key for d in documents}
        missing = [d.id for d in documents if not (_root() / d.storage_key).is_file() or (_root() / d.storage_key).is_symlink()]
        removed = 0
        for path in _root().iterdir():
            if re.fullmatch(r'[0-9a-f]{32}', path.name) and not path.is_symlink() and path.name not in keys and path.stat().st_mtime < time.time() - grace_seconds:
                path.unlink()
                removed += 1
        return {'missing_document_ids': missing, 'removed_orphans': removed}
