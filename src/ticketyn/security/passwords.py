"""Bounded Argon2id operations, including constant-work unknown-account checks."""
import threading
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError, InvalidHashError

HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, type=Type.ID)
# At most 128 MiB of Argon2 working memory per HTTP process.
_SLOTS = threading.BoundedSemaphore(2)
_DUMMY = None
_DUMMY_LOCK = threading.Lock()

class PasswordBusy(Exception):
    pass

def validate_password(value):
    if not isinstance(value, str) or not value or len(value.encode('utf-8')) > 4096:
        raise ValueError('La contraseña debe contener entre 1 y 4096 bytes UTF-8')
    return value

def hash_password(value):
    validate_password(value)
    if not _SLOTS.acquire(blocking=False):
        raise PasswordBusy('Verificación de contraseñas ocupada')
    try:
        return HASHER.hash(value)
    finally:
        _SLOTS.release()

def dummy_hash():
    global _DUMMY
    with _DUMMY_LOCK:
        if _DUMMY is None:
            _DUMMY = hash_password('ticketyn-dummy-not-an-account')
        return _DUMMY

def verify_password(encoded, value):
    validate_password(value)
    encoded = encoded or dummy_hash()
    if not _SLOTS.acquire(blocking=False):
        raise PasswordBusy('Verificación de contraseñas ocupada')
    try:
        try:
            return HASHER.verify(encoded, value)
        except (VerificationError, InvalidHashError):
            return False
    finally:
        _SLOTS.release()
