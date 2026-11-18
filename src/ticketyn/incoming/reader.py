"""Read-only TLS IMAP adapter. No remote flags or messages are mutated."""
from dataclasses import dataclass
from datetime import datetime, timezone
import imaplib
import re
import ssl
from typing import Protocol, Iterable

from ticketyn.incoming.config import IncomingSettings


@dataclass(frozen=True)
class IncomingMessage:
    uidvalidity: int
    uid: int
    content: bytes
    received_at: datetime


class MailReader(Protocol):
    def messages(self, known: set[tuple[int, int]]) -> Iterable[IncomingMessage]: ...


class ImapReader:
    def __init__(self, settings: IncomingSettings):
        self.settings = settings
        self.errors = []

    def messages(self, known):
        settings = self.settings
        self.errors = []
        with imaplib.IMAP4_SSL(settings.host, settings.port, ssl_context=ssl.create_default_context(), timeout=30) as connection:
            connection.login(settings.username, settings.password)
            status, _ = connection.select(settings.folder, readonly=True)
            if status != 'OK':
                raise ValueError('Cannot open configured IMAP folder')
            _, values = connection.response('UIDVALIDITY')
            if not values or not values[0]:
                raise ValueError('IMAP did not provide UIDVALIDITY')
            validity = int(values[0])
            status, rows = connection.uid('search', None, 'ALL')
            if status != 'OK':
                raise ValueError('IMAP search failed')
            pending = [uid for uid in rows[0].split() if (validity, int(uid)) not in known]
            fetched = 0
            for uid in pending:
                if fetched >= settings.batch_size:
                    break
                status, sizes = connection.uid('fetch', uid, '(RFC822.SIZE INTERNALDATE)')
                if status != 'OK':
                    self.errors.append({'uid': int(uid), 'error': 'Size fetch failed; retained remotely'})
                    continue
                metadata = b' '.join(row for row in sizes if isinstance(row, bytes))
                match = re.search(rb'RFC822.SIZE (\d+)', metadata)
                if not match or int(match[1]) > settings.max_bytes:
                    self.errors.append({'uid': int(uid), 'error': 'Message exceeds size limit or has no size; retained remotely for recovery'})
                    continue
                internal = imaplib.Internaldate2tuple(metadata)
                if internal is None:
                    self.errors.append({'uid': int(uid), 'error': 'Invalid INTERNALDATE; retained remotely'})
                    continue
                import time
                received_at = datetime.fromtimestamp(time.mktime(internal), timezone.utc)
                status, rows = connection.uid('fetch', uid, '(BODY.PEEK[])')
                raw = next((row[1] for row in rows if isinstance(row, tuple)), None)
                if status != 'OK' or raw is None or len(raw) > settings.max_bytes:
                    self.errors.append({'uid': int(uid), 'error': 'Content fetch failed; retained remotely'})
                    continue
                fetched += 1
                yield IncomingMessage(validity, int(uid), raw, received_at)
