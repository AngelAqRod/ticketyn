"""Durable human-reviewed intake; receiving never creates an order."""
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr
import hashlib
import logging
import unicodedata

from sqlalchemy import select, text

from ticketyn.incoming.config import IncomingSettings
from ticketyn.incoming.reader import ImapReader
from ticketyn.incoming.storage import save_document, storage_lock
from ticketyn.models.installation_orders import InstallationRequest, InstallationEvent, InstallationReceptionFilter

logger = logging.getLogger(__name__)


def reception_filters(session):
    row = session.get(InstallationReceptionFilter, 1)
    return {'senders': list(row.senders) if row else [], 'subjects': list(row.subjects) if row else []}


def plain(text):
    """Case- and accent-insensitive form used only for comparing subjects."""
    return ''.join(c for c in unicodedata.normalize('NFD', text.casefold()) if not unicodedata.combining(c))


def filter_reason(parsed, filters):
    """Why a message is not an installation request; None when it passes. Empty filters accept everything."""
    sender = parseaddr(str(parsed.get('From', '')))[1].lower()
    if filters['senders'] and not any(sender == rule or (rule.startswith('@') and sender.endswith(rule)) for rule in filters['senders']):
        return 'Filtrado: remitente no permitido'
    subject = plain(str(parsed.get('Subject', '')))
    if filters['subjects'] and not any(plain(word) in subject for word in filters['subjects']):
        return 'Filtrado: el asunto no contiene una palabra clave'
    return None


def ingest(session, message, settings):
    """Caller holds storage_lock through commit; the transaction deduplicates intake."""
    mailbox = f'{settings.username}@{settings.host}'
    key = f'{mailbox}\0{settings.folder}\0{message.uidvalidity}\0{message.uid}'
    lock_id = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big', signed=True)
    session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': lock_id})
    existing = session.scalar(select(InstallationRequest).where(
        InstallationRequest.mailbox == mailbox, InstallationRequest.folder == settings.folder,
        InstallationRequest.uidvalidity == message.uidvalidity, InstallationRequest.uid == message.uid))
    if existing:
        return existing, False
    if len(message.content) > settings.max_bytes:
        raise ValueError('Message exceeds configured size limit; retained remotely')
    parsed = BytesParser(policy=policy.default).parsebytes(message.content)
    reason = filter_reason(parsed, reception_filters(session))
    if reason:
        # Recorded as discarded so the message is not fetched again and cannot starve newer ones in the batch.
        request = InstallationRequest(mailbox=mailbox, folder=settings.folder,
            uidvalidity=message.uidvalidity, uid=message.uid, message_id=str(parsed.get('Message-ID', '')) or None,
            checksum=hashlib.sha256(message.content).hexdigest(), sender=str(parsed.get('From', '')),
            subject=str(parsed.get('Subject', '')), body='', received_at=message.received_at,
            state='DISCARDED', discard_reason=reason)
        session.add(request)
        session.flush()
        session.add(InstallationEvent(request_id=request.id, action='FILTERED', detail={'reason': reason}))
        session.flush()
        return request, True
    bodies = []
    attachments = []
    warnings = []
    for index, part in enumerate(parsed.walk()):
        if part.is_multipart():
            continue
        name = part.get_filename()
        if name or part.get_content_disposition() == 'attachment':
            attachments.append((name or f'attachment-{index}.bin', part.get_payload(decode=True) or b''))
        elif part.get_content_type() == 'text/plain':
            payload = part.get_payload(decode=True) or b''
            try:
                bodies.append(payload.decode(part.get_content_charset() or 'utf-8', errors='replace'))
            except LookupError:
                bodies.append(payload.decode('utf-8', errors='replace'))
    request = InstallationRequest(mailbox=mailbox, folder=settings.folder,
        uidvalidity=message.uidvalidity, uid=message.uid, message_id=str(parsed.get('Message-ID', '')) or None,
        checksum=hashlib.sha256(message.content).hexdigest(), sender=str(parsed.get('From', '')),
        subject=str(parsed.get('Subject', '')), body='\n\n'.join(bodies), received_at=message.received_at,
        state='PENDING')
    session.add(request)
    session.flush()
    save_document(session, content=message.content, name='original.eml', request_id=request.id, original=True)
    for name, content in attachments:
        try:
            save_document(session, content=content, name=name, request_id=request.id)
        except ValueError as error:
            # Original MIME retains unsupported attachments without serving active content.
            warnings.append({'name': str(name)[:255], 'reason': str(error)})
    session.add(InstallationEvent(request_id=request.id, action='RECEIVED', detail={'attachment_warnings': warnings}))
    if warnings:
        request.body += '\n\nAttachments requiring download of the original email: ' + ', '.join(w['name'] for w in warnings)
    session.flush()
    return request, True


def poll(session, reader=None):
    settings = IncomingSettings.from_env()
    result = {'received': 0, 'filtered': 0, 'duplicates': 0, 'errors': []}
    if not settings.enabled:
        return result
    mailbox = f'{settings.username}@{settings.host}'
    known = set(session.execute(select(InstallationRequest.uidvalidity, InstallationRequest.uid).where(
        InstallationRequest.mailbox == mailbox, InstallationRequest.folder == settings.folder)).all())
    session.rollback()
    reader = reader or ImapReader(settings)
    try:
        for message in reader.messages(known):
            try:
                with storage_lock():
                    request, created = ingest(session, message, settings)
                    kind = 'duplicates' if not created else 'filtered' if request.state == 'DISCARDED' else 'received'
                    session.commit()
                result[kind] += 1
            except Exception:
                session.rollback()
                logger.exception('Installation email intake failed; original remains on server')
                result['errors'].append({'uid': message.uid, 'error': 'Intake failed; retained remotely for retry'})
    except Exception:
        session.rollback()
        logger.exception('Installation IMAP reader failed')
        result['errors'].append({'error': 'IMAP read failed; inspect receiver logs; messages retained remotely'})
    result['errors'].extend(getattr(reader, 'errors', []))
    return result
