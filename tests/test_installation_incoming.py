from email.message import EmailMessage

import pytest

from ticketyn.incoming.config import IncomingSettings
from ticketyn.incoming.storage import validate_document


def test_manual_mode_without_imap(monkeypatch):
    for key in ('HOST', 'USERNAME', 'PASSWORD'):
        monkeypatch.delenv('INSTALLATION_IMAP_' + key, raising=False)
    assert not IncomingSettings.from_env().enabled


def test_document_validation():
    assert validate_document(b'%PDF-1.7\n', 'request.pdf') == 'application/pdf'
    with pytest.raises(ValueError):
        validate_document(b'<script>bad</script>', 'request.pdf')
    with pytest.raises(ValueError):
        validate_document(b'%PDF-1.7\n', '../request.pdf')


def message(content=None, uid=1):
    from datetime import datetime, timezone
    from ticketyn.incoming.reader import IncomingMessage
    email = EmailMessage()
    email['From'] = 'orders@example.test'
    email['Subject'] = 'Installation request'
    email['Message-ID'] = '<installation@example.test>'
    email.set_content('Please install an internet link.')
    email.add_attachment(b'%PDF-1.7\noriginal', maintype='application', subtype='pdf', filename='order.pdf')
    return IncomingMessage(123, uid, content or email.as_bytes(), datetime.now(timezone.utc))


@pytest.fixture
def storage_settings(tmp_path, monkeypatch):
    monkeypatch.setenv('INSTALLATION_STORAGE_DIR', str(tmp_path / 'originals'))
    monkeypatch.setenv('INSTALLATION_IMAP_HOST', 'imap.example.test')
    monkeypatch.setenv('INSTALLATION_IMAP_USERNAME', 'inbox')
    monkeypatch.setenv('INSTALLATION_IMAP_PASSWORD', 'test-secret')
    return IncomingSettings.from_env()


def test_ingest_idempotent_preserves_original_without_order(db_session, storage_settings):
    from sqlalchemy import select, func
    from ticketyn.incoming.receiver import ingest
    from ticketyn.incoming.storage import document_path, storage_lock
    from ticketyn.models.installation_orders import InstallationDocument, InstallationOrder
    original = message()
    with storage_lock():
        request, created = ingest(db_session, original, storage_settings)
        db_session.commit()
        duplicate, again = ingest(db_session, original, storage_settings)
        db_session.commit()
    assert created and not again and request.id == duplicate.id
    assert request.state == 'PENDING' and request.order_id is None
    assert db_session.scalar(select(func.count()).select_from(InstallationOrder)) == 0
    documents = list(db_session.scalars(select(InstallationDocument).where(InstallationDocument.request_id == request.id)))
    assert len(documents) == 2
    raw = next(d for d in documents if d.media_type == 'message/rfc822')
    assert document_path(raw).read_bytes() == original.content
    assert raw.request_id == request.id and raw.order_id is None


def test_partial_receive_retry_and_orphan_cleanup(db_session, storage_settings, monkeypatch):
    import os
    import time
    from sqlalchemy import select, func
    from ticketyn.incoming import receiver
    from ticketyn.incoming.storage import recover_storage
    from ticketyn.models.installation_orders import InstallationRequest
    class Reader:
        def messages(self, known):
            yield message()
    real_save = receiver.save_document
    def fail_attachment(*args, **kwargs):
        if not kwargs.get('original'):
            raise OSError('simulated full disk')
        return real_save(*args, **kwargs)
    monkeypatch.setattr(receiver, 'save_document', fail_attachment)
    failed = receiver.poll(db_session, Reader())
    assert failed['errors'] and failed['received'] == 0
    assert db_session.scalar(select(func.count()).select_from(InstallationRequest)) == 0
    orphan = next(p for p in storage_settings.storage_dir.iterdir() if p.name != '.lock')
    os.utime(orphan, (time.time() - 90000, time.time() - 90000))
    assert recover_storage(db_session)['removed_orphans'] == 1
    monkeypatch.setattr(receiver, 'save_document', real_save)
    assert receiver.poll(db_session, Reader())['received'] == 1
    assert not recover_storage(db_session)['missing_document_ids']


def test_unsupported_attachment_preserved_inside_original(db_session, storage_settings):
    from ticketyn.incoming.receiver import ingest
    from ticketyn.models.installation_orders import InstallationEvent
    from sqlalchemy import select
    email = EmailMessage()
    email.set_content('Request')
    email.add_attachment(b'<html>active</html>', maintype='text', subtype='html', filename='unsafe.html')
    request, _ = ingest(db_session, message(email.as_bytes()), storage_settings)
    event = db_session.scalar(select(InstallationEvent).where(InstallationEvent.request_id == request.id))
    assert event.detail['attachment_warnings'][0]['name'] == 'unsafe.html'


def test_storage_rejects_symlink_and_oversize(tmp_path, monkeypatch):
    from ticketyn.incoming.storage import document_path
    from types import SimpleNamespace
    monkeypatch.setenv('INSTALLATION_STORAGE_DIR', str(tmp_path))
    outside = tmp_path / 'outside'
    outside.write_bytes(b'secret')
    (tmp_path / ('a' * 32)).symlink_to(outside)
    with pytest.raises(ValueError):
        document_path(SimpleNamespace(storage_key='a' * 32))
    with pytest.raises(ValueError):
        document_path(SimpleNamespace(storage_key='../outside'))
    monkeypatch.setenv('INSTALLATION_MAX_BYTES', '2')
    with pytest.raises(ValueError):
        validate_document(b'%PDF-1.7\n', 'request.pdf')


def test_disabled_poll_does_not_call_reader(db_session, monkeypatch):
    from ticketyn.incoming.receiver import poll
    monkeypatch.delenv('INSTALLATION_IMAP_HOST', raising=False)
    class Reader:
        def messages(self, known):
            raise AssertionError('must not connect')
    assert poll(db_session, Reader()) == {'received': 0, 'filtered': 0, 'duplicates': 0, 'errors': []}


def test_imap_readonly_identity_limits_and_peek(monkeypatch, storage_settings):
    from ticketyn.incoming import reader
    calls = []
    raw = message().content
    class Connection:
        def __init__(self, *args, **kwargs):
            assert kwargs['ssl_context'].check_hostname
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def login(self, username, password):
            calls.append('login')
        def select(self, folder, readonly):
            assert readonly and folder == 'INBOX'
            return 'OK', []
        def response(self, name):
            assert name == 'UIDVALIDITY'
            return name, [b'123']
        def uid(self, action, *args):
            calls.append((action, args))
            if action == 'search': return 'OK', [b'1 2 3']
            uid, fields = args
            if fields == '(RFC822.SIZE INTERNALDATE)':
                size = storage_settings.max_bytes + 1 if uid == b'2' else len(raw)
                return 'OK', [f'1 (UID {uid.decode()} RFC822.SIZE {size} INTERNALDATE "01-Jan-2026 12:00:00 +0000")'.encode()]
            assert fields == '(BODY.PEEK[])'
            return 'OK', [(b'metadata', raw), b')']
    monkeypatch.setattr(reader.imaplib, 'IMAP4_SSL', Connection)
    adapter = reader.ImapReader(storage_settings)
    messages = list(adapter.messages({(123, 1)}))
    assert [m.uid for m in messages] == [3]
    assert messages[0].uidvalidity == 123 and messages[0].content == raw
    assert adapter.errors[0]['uid'] == 2
    assert not any(isinstance(c, tuple) and c[0] in ('store', 'expunge') for c in calls)


def test_poll_progresses_beyond_known_batch_and_failed_first(db_session, storage_settings, monkeypatch):
    from ticketyn.incoming.receiver import poll
    from ticketyn.incoming.reader import ImapReader
    monkeypatch.setenv('INSTALLATION_IMAP_BATCH_SIZE', '1')
    settings = IncomingSettings.from_env()
    raw = message().content
    from ticketyn.incoming import reader
    class Connection:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def login(self, *args): pass
        def select(self, *args, **kwargs): return 'OK', []
        def response(self, *args): return 'UIDVALIDITY', [b'123']
        def uid(self, action, *args):
            if action == 'search': return 'OK', [b'1 2 3']
            uid, fields = args
            if fields == '(RFC822.SIZE INTERNALDATE)':
                size = settings.max_bytes + 1 if uid == b'1' else len(raw)
                return 'OK', [f'1 (RFC822.SIZE {size} INTERNALDATE "01-Jan-2026 12:00:00 +0000")'.encode()]
            return 'OK', [(b'metadata', raw)]
    monkeypatch.setattr(reader.imaplib, 'IMAP4_SSL', Connection)
    first = poll(db_session, ImapReader(settings))
    second = poll(db_session, ImapReader(settings))
    third = poll(db_session, ImapReader(settings))
    assert first['received'] == second['received'] == 1
    assert third['received'] == 0
    assert all(result['errors'][0]['uid'] == 1 for result in (first, second, third))


def test_reception_filters_by_sender_and_subject(db_session, storage_settings):
    from ticketyn.incoming.receiver import ingest
    from ticketyn.incoming.storage import storage_lock
    from ticketyn.models.installation_orders import InstallationReceptionFilter
    db_session.add(InstallationReceptionFilter(id=1, senders=['@example.test'], subjects=['instalación']))
    db_session.commit()
    settings = storage_settings

    def build(sender, subject, uid):
        email = EmailMessage()
        email['From'] = f'Someone <{sender}>'
        email['Subject'] = subject
        email.set_content('body')
        return message(email.as_bytes(), uid)
    with storage_lock():
        ok, _ = ingest(db_session, build('Orders@Example.test', 'Nueva INSTALACION', 1), settings)
        other_sender, _ = ingest(db_session, build('spam@other.test', 'instalación', 2), settings)
        other_subject, _ = ingest(db_session, build('orders@example.test', 'Invoice', 3), settings)
        db_session.commit()
    assert ok.state == 'PENDING'
    assert other_sender.state == 'DISCARDED' and 'remitente' in other_sender.discard_reason
    assert other_subject.state == 'DISCARDED' and 'asunto' in other_subject.discard_reason


def test_reception_filters_api_validates_and_persists(api_client):
    assert api_client.get('/api/incoming-mail/filters').json() == {'senders': [], 'subjects': []}
    saved = api_client.patch('/api/incoming-mail/filters', json={'senders': [' Ventas@Cliente.com ', '@empresa.com', '@empresa.com'], 'subjects': ['Instalación', '']})
    assert saved.status_code == 200 and saved.json() == {'senders': ['ventas@cliente.com', '@empresa.com'], 'subjects': ['instalación']}
    assert api_client.get('/api/incoming-mail/filters').json() == saved.json()
    assert api_client.patch('/api/incoming-mail/filters', json={'senders': ['no-es-correo'], 'subjects': []}).status_code == 422
