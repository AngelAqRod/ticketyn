from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class IncomingSettings:
    storage_dir: Path
    host: str = ''
    username: str = ''
    password: str = ''
    port: int = 993
    folder: str = 'INBOX'
    max_bytes: int = 25 * 1024 * 1024
    interval: int = 60
    batch_size: int = 100

    @property
    def enabled(self):
        return bool(self.host and self.username and self.password)

    @classmethod
    def from_env(cls):
        return cls(
            storage_dir=Path(os.environ.get('INSTALLATION_STORAGE_DIR', './var/installation-originals')).absolute(),
            host=os.environ.get('INSTALLATION_IMAP_HOST', ''),
            username=os.environ.get('INSTALLATION_IMAP_USERNAME', ''),
            password=os.environ.get('INSTALLATION_IMAP_PASSWORD', ''),
            port=_positive('INSTALLATION_IMAP_PORT', 993),
            folder=os.environ.get('INSTALLATION_IMAP_FOLDER', 'INBOX'),
            max_bytes=_positive('INSTALLATION_MAX_BYTES', 25 * 1024 * 1024),
            interval=_positive('INSTALLATION_IMAP_INTERVAL', 60),
            batch_size=_positive('INSTALLATION_IMAP_BATCH_SIZE', 100),
        )


def _positive(name, default):
    value = int(os.environ.get(name, default))
    if value < 1:
        raise ValueError(f'{name} must be positive')
    return value
