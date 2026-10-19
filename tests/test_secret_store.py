"""Synthetic secrets and private files only; no root or database required."""
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

from ticketyn.core.config import DEFAULT_MAIL_KEYS_PATH, Settings, get_settings
from ticketyn.core.secret_store import (
    DecryptionError, EncryptionError, KeyFileError, SecretCipher,
    copy_key_file, create_key_file, get_secret_cipher, validate_key_file,
)

VALUE = 'synthetic-secret-NOT-a-credential-ñ\nsecond line'
CONTEXT = 'mail:transport:1:smtp-password'


@pytest.fixture
def key_file(tmp_path):
    directory = tmp_path / 'private'
    directory.mkdir(mode=0o700)
    path = directory / 'keys.json'
    create_key_file(path)
    return path


def write_doc(path, doc):
    path.write_text(json.dumps(doc))


@pytest.mark.parametrize('value', ['', VALUE, 'x' * 65536])
def test_roundtrip_and_versioned_authenticated_envelope(key_file, value):
    cipher = SecretCipher(key_file)
    encrypted = cipher.encrypt(value, context=CONTEXT)
    doc = json.loads(encrypted)
    assert doc.keys() == {'version', 'key_id', 'nonce', 'ciphertext'}
    assert doc['version'] == 1
    assert doc['key_id'] == validate_key_file(key_file)
    assert len(base64.urlsafe_b64decode(doc['nonce'])) == 12
    assert cipher.decrypt(encrypted, context=CONTEXT) == value
    assert VALUE not in encrypted


def test_fresh_nonces_and_independent_random_256_bit_keys(key_file):
    cipher = SecretCipher(key_file)
    nonces = {json.loads(cipher.encrypt(VALUE, context=CONTEXT))['nonce'] for _ in range(100)}
    assert len(nonces) == 100
    other = key_file.with_name('other.json')
    create_key_file(other)
    first, second = (json.loads(p.read_text()) for p in (key_file, other))
    first_key = next(iter(first['keys'].values()))
    assert len(base64.urlsafe_b64decode(first_key)) == 32
    assert first_key != next(iter(second['keys'].values()))


@pytest.mark.parametrize('field', ['ciphertext', 'nonce', 'key_id', 'version', 'context'])
def test_tampering_is_rejected(key_file, field):
    cipher = SecretCipher(key_file)
    doc = json.loads(cipher.encrypt(VALUE, context=CONTEXT))
    context = CONTEXT
    if field in ('ciphertext', 'nonce'):
        raw = bytearray(base64.urlsafe_b64decode(doc[field])); raw[0] ^= 1
        doc[field] = base64.urlsafe_b64encode(raw).decode()
    elif field == 'key_id':
        doc[field] = 'unknown-key'
    elif field == 'version':
        doc[field] = 2
    else:
        context = 'mail:transport:2:refresh-token'
    with pytest.raises(DecryptionError):
        cipher.decrypt(json.dumps(doc), context=context)


def test_same_identifier_with_wrong_key_fails(key_file):
    cipher = SecretCipher(key_file)
    encrypted = cipher.encrypt(VALUE, context=CONTEXT)
    original = json.loads(key_file.read_text())
    other = key_file.with_name('other.json'); create_key_file(other)
    original['keys'][original['active_key_id']] = next(iter(json.loads(other.read_text())['keys'].values()))
    write_doc(key_file, original)
    with pytest.raises(DecryptionError):
        cipher.decrypt(encrypted, context=CONTEXT)


def test_missing_file_never_creates_replacement(key_file):
    cipher = SecretCipher(key_file)
    encrypted = cipher.encrypt(VALUE, context=CONTEXT)
    key_file.unlink()
    for operation in (lambda: cipher.encrypt(VALUE, context=CONTEXT), lambda: cipher.decrypt(encrypted, context=CONTEXT)):
        with pytest.raises(KeyFileError):
            operation()
        assert not key_file.exists()


@pytest.mark.parametrize('content', [
    '', '{broken secret', '[]', 'null', '{"version":1,"version":1}',
    '{"version":1,"active_key_id":"k","keys":{"k":"bad key"}}',
    '{"version":true,"active_key_id":"k","keys":{"k":"bad"}}',
    'x' * 65537, '[' * 2000,
])
def test_corrupt_key_file_rejected_without_leaks(key_file, content, caplog):
    key_file.write_text(content)
    with pytest.raises(KeyFileError) as caught:
        SecretCipher(key_file).encrypt(VALUE, context=CONTEXT)
    if content:
        assert content not in str(caught.value)
    assert VALUE not in caplog.text + str(caught.value)


@pytest.mark.parametrize('mutation', ['version', 'missing-active', 'unknown-field', 'short-key', 'empty-keys', 'key-id', 'too-many-keys'])
def test_invalid_key_documents(key_file, mutation):
    doc = json.loads(key_file.read_text())
    if mutation == 'version': doc['version'] = 2
    elif mutation == 'missing-active': doc['active_key_id'] = 'missing'
    elif mutation == 'unknown-field': doc['secret'] = VALUE
    elif mutation == 'short-key': doc['keys'][doc['active_key_id']] = base64.urlsafe_b64encode(b'short').decode()
    elif mutation == 'empty-keys': doc['keys'] = {}
    elif mutation == 'key-id': doc['active_key_id'] = '../invalid'
    else: doc['keys'] = {str(i): next(iter(doc['keys'].values())) for i in range(33)}
    write_doc(key_file, doc)
    with pytest.raises(KeyFileError): validate_key_file(key_file)


@pytest.mark.parametrize('mode', [0o644, 0o666, 0o660, 0o700, 0o604, 0o6000])
def test_unsafe_key_permissions(key_file, mode):
    key_file.chmod(mode)
    with pytest.raises(KeyFileError): validate_key_file(key_file)


@pytest.mark.parametrize('mode', [0o755, 0o777, 0o770])
def test_unsafe_parent_permissions(key_file, mode):
    key_file.parent.chmod(mode)
    try:
        with pytest.raises(KeyFileError): validate_key_file(key_file)
    finally:
        key_file.parent.chmod(0o700)


def test_read_only_file_and_service_group_are_supported(key_file):
    key_file.chmod(0o400)
    assert validate_key_file(key_file)
    grouped = key_file.with_name('group.json')
    create_key_file(grouped, group_id=os.getegid())
    assert stat.S_IMODE(grouped.stat().st_mode) == 0o640
    assert grouped.stat().st_gid == os.getegid()
    grouped.parent.chmod(0o750)
    assert validate_key_file(grouped)


def test_symlinks_hardlinks_and_nonregular_files_are_rejected(key_file):
    link = key_file.with_name('link.json'); link.symlink_to(key_file)
    with pytest.raises(KeyFileError): validate_key_file(link)
    directory_link = key_file.parent.parent / 'directory-link'; directory_link.symlink_to(key_file.parent, target_is_directory=True)
    with pytest.raises(KeyFileError): validate_key_file(directory_link / key_file.name)
    link.unlink(); os.link(key_file, link)
    with pytest.raises(KeyFileError): validate_key_file(key_file)
    link.unlink()
    fifo = key_file.with_name('fifo'); os.mkfifo(fifo, mode=0o600)
    with pytest.raises(KeyFileError): validate_key_file(fifo)
    with pytest.raises(KeyFileError): validate_key_file(key_file.parent)


def test_provisioning_never_replaces_existing_file_or_symlink(key_file):
    original = key_file.read_bytes()
    with pytest.raises(KeyFileError): create_key_file(key_file)
    assert key_file.read_bytes() == original
    link = key_file.with_name('link.json'); link.symlink_to(key_file)
    with pytest.raises(KeyFileError): create_key_file(link)
    assert link.is_symlink() and key_file.read_bytes() == original
    assert not list(key_file.parent.glob('.keys-*'))


def test_concurrent_provisioning_only_one_winner(tmp_path):
    path = tmp_path / 'keys.json'
    def provision():
        try: return create_key_file(path)
        except KeyFileError: return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(lambda _: provision(), range(4)))
    assert sum(x is not None for x in outcomes) == 1
    assert validate_key_file(path) in outcomes
    assert not list(tmp_path.glob('.keys-*'))


def test_publication_is_complete_private_and_atomic(tmp_path, monkeypatch):
    from ticketyn.core import secret_store
    path = tmp_path / 'keys.json'
    real_link = os.link
    def inspect_before_publish(source, destination, **kwargs):
        assert not path.exists()
        with os.fdopen(os.open(source, os.O_RDONLY, dir_fd=kwargs['src_dir_fd']), 'rb') as stream:
            assert stat.S_IMODE(os.fstat(stream.fileno()).st_mode) == 0o600
            assert json.load(stream)['version'] == 1
        return real_link(source, destination, **kwargs)
    monkeypatch.setattr(secret_store.os, 'link', inspect_before_publish)
    create_key_file(path)
    assert validate_key_file(path)
    assert path.stat().st_nlink == 1


def test_write_failure_leaves_no_partial_destination(tmp_path, monkeypatch):
    from ticketyn.core import secret_store
    path = tmp_path / 'keys.json'
    def fail(*args, **kwargs): raise OSError('synthetic private OS diagnostic')
    monkeypatch.setattr(secret_store.os, 'fsync', fail)
    with pytest.raises(KeyFileError) as caught: create_key_file(path)
    assert 'private OS diagnostic' not in str(caught.value)
    assert not path.exists() and not list(tmp_path.glob('.keys-*'))


def test_backup_and_restore_preserve_keys_without_database(key_file, tmp_path):
    cipher = SecretCipher(key_file)
    encrypted = cipher.encrypt(VALUE, context=CONTEXT)
    backup_dir = tmp_path / 'separate-backup'; backup_dir.mkdir(mode=0o700)
    backup = backup_dir / 'keys.json'
    original_id = copy_key_file(key_file, backup)
    key_file.unlink()
    with pytest.raises(KeyFileError): cipher.decrypt(encrypted, context=CONTEXT)
    # A new unrelated file is not a replacement for the original keys.
    create_key_file(key_file)
    with pytest.raises(DecryptionError): cipher.decrypt(encrypted, context=CONTEXT)
    with pytest.raises(KeyFileError): copy_key_file(backup, key_file)
    key_file.unlink()
    assert copy_key_file(backup, key_file) == original_id
    assert cipher.decrypt(encrypted, context=CONTEXT) == VALUE
    assert validate_key_file(backup) == original_id


def test_decryption_uses_recorded_key_id_not_active_key(key_file):
    cipher = SecretCipher(key_file)
    old = cipher.encrypt(VALUE, context=CONTEXT)
    other = key_file.with_name('other.json'); create_key_file(other)
    doc = json.loads(key_file.read_text()); new = json.loads(other.read_text())
    doc['keys'].update(new['keys']); doc['active_key_id'] = new['active_key_id']
    write_doc(key_file, doc)
    assert cipher.decrypt(old, context=CONTEXT) == VALUE
    assert json.loads(cipher.encrypt(VALUE, context=CONTEXT))['key_id'] == doc['active_key_id']


def test_safe_errors_and_no_logging(key_file, caplog):
    cipher = SecretCipher(key_file)
    key = next(iter(json.loads(key_file.read_text())['keys'].values()))
    for action in [lambda: cipher.decrypt(VALUE, context=CONTEXT),
                   lambda: cipher.encrypt(VALUE, context=''),
                   lambda: cipher.encrypt('x' * 65537, context=CONTEXT)]:
        with pytest.raises((EncryptionError, DecryptionError)) as caught: action()
        assert VALUE not in str(caught.value) and key not in str(caught.value)
        assert caught.value.__suppress_context__
    assert VALUE not in caplog.text and key not in caplog.text


def test_configuration_is_lazy_and_supports_private_user_path(key_file, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://test:test@127.0.0.1:1/test')
    monkeypatch.setenv('MAIL_KEYS_PATH', str(key_file))
    get_settings.cache_clear()
    try:
        cipher = get_secret_cipher()
        assert cipher.decrypt(cipher.encrypt(VALUE, context=CONTEXT), context=CONTEXT) == VALUE
        key_file.unlink()
        # Configuration and application startup do not provision or require keys.
        assert get_settings().mail_keys_path == key_file
        from fastapi.testclient import TestClient
        from ticketyn.main import create_app
        with TestClient(create_app(start_notifications=False)) as client:
            assert client.get('/health').status_code == 200
        with pytest.raises(KeyFileError): cipher.encrypt(VALUE, context=CONTEXT)
        assert not key_file.exists()
    finally:
        get_settings.cache_clear()
    monkeypatch.delenv('MAIL_KEYS_PATH')
    assert Settings(_env_file=None, database_url='postgresql+psycopg://test:test@localhost/test').mail_keys_path == DEFAULT_MAIL_KEYS_PATH


def test_cli_without_root_and_without_database_url(tmp_path):
    path = tmp_path / 'keys.json'
    environment = {k: v for k, v in os.environ.items() if k not in {'DATABASE_URL', 'MAIL_KEYS_PATH'}}
    root = Path(__file__).resolve().parents[1]
    def cli(*args):
        return subprocess.run([sys.executable, '-B', '-m', 'ticketyn.core.secret_store', *args],
                              env=environment, cwd=root, capture_output=True, text=True, timeout=10)
    assert cli('init', '--path', str(path)).returncode == 0
    content = path.read_text()
    checked = cli('check', '--path', str(path))
    assert checked.returncode == 0
    assert content not in checked.stdout + checked.stderr
    failed = cli('init', '--path', str(path))
    assert failed.returncode == 1 and 'Traceback' not in failed.stderr
    assert path.read_text() == content
    copied = tmp_path / 'backup.json'
    assert cli('copy', '--source', str(path), '--destination', str(copied)).returncode == 0
    assert json.loads(copied.read_text()) == json.loads(content)


@pytest.mark.parametrize('value', ['[]', 'null', '[[]]', '{"version":1,"version":1}', '[' * 2000, '', 'x' * 100001])
def test_invalid_envelopes_have_safe_errors(key_file, value):
    with pytest.raises(DecryptionError): SecretCipher(key_file).decrypt(value, context=CONTEXT)


def test_file_permissions_are_rechecked_after_cipher_creation(key_file):
    cipher = SecretCipher(key_file)
    encrypted = cipher.encrypt(VALUE, context=CONTEXT)
    key_file.chmod(0o644)
    with pytest.raises(KeyFileError): cipher.decrypt(encrypted, context=CONTEXT)
    with pytest.raises(KeyFileError): cipher.encrypt(VALUE, context=CONTEXT)


def test_relative_paths_are_rejected_without_creating_files():
    with pytest.raises(KeyFileError): create_key_file(Path('keys.json'))
    with pytest.raises(KeyFileError): validate_key_file(Path('keys.json'))


@pytest.mark.parametrize('target', ['file', 'directory'])
def test_extended_acl_is_rejected(key_file, monkeypatch, target):
    from ticketyn.core import secret_store
    real_list = os.listxattr
    def acl(descriptor):
        info = os.fstat(descriptor)
        matches = stat.S_ISREG(info.st_mode) if target == 'file' else stat.S_ISDIR(info.st_mode)
        return ['system.posix_acl_access'] if matches else real_list(descriptor)
    monkeypatch.setattr(secret_store.os, 'listxattr', acl)
    with pytest.raises(KeyFileError): validate_key_file(key_file)


def test_untrusted_key_owner_is_rejected(key_file, monkeypatch):
    from ticketyn.core import secret_store
    real_stat = os.fstat
    def wrong_owner(descriptor):
        info = real_stat(descriptor)
        if stat.S_ISREG(info.st_mode):
            fields = list(info); fields[4] = 999999
            return os.stat_result(fields)
        return info
    monkeypatch.setattr(secret_store.os, 'fstat', wrong_owner)
    with pytest.raises(KeyFileError): validate_key_file(key_file)
