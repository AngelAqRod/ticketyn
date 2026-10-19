from urllib.parse import urlsplit
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

DEFAULT_MAIL_KEYS_PATH = Path('/etc/ticketyn/mail/keys.json')


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str
    mail_keys_path: Path = DEFAULT_MAIL_KEYS_PATH
    mail_oauth_redirect_uri: str | None = None

    @field_validator('mail_oauth_redirect_uri')
    @classmethod
    def valid_mail_callback(cls, value):
        if value is None: return value
        url = urlsplit(value)
        if (url.path != '/api/mail-notifications/oauth/callback' or url.query or url.fragment
                or url.username or url.password or not url.hostname
                or any(ord(c) < 33 or ord(c) > 126 for c in value)
                or url.scheme not in {'http', 'https'}
                or (url.scheme == 'http' and url.hostname not in {'localhost', '127.0.0.1', '::1'})):
            raise ValueError('MAIL_OAUTH_REDIRECT_URI debe ser una URL HTTPS de retorno exacta, o HTTP de loopback para desarrollo')
        try: url.port
        except ValueError:
            raise ValueError('Puerto de retorno OAuth2 inválido') from None
        return value

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: str) -> str:
        if make_url(value).drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL debe usar postgresql+psycopg")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
