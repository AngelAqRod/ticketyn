"""Strict, secret-safe input and public response contracts for mail settings."""
import ipaddress
import re
from typing import Annotated, Literal
from email_validator import EmailNotValidError, validate_email
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SecretStr, field_validator

Security = Literal['STARTTLS', 'IMPLICIT_TLS', 'NONE']
AuthMethod = Literal['NONE', 'PASSWORD', 'OAUTH2_DELEGATED', 'OAUTH2_APPLICATION']
Provider = Literal['GMAIL', 'GOOGLE_WORKSPACE', 'OUTLOOK_COM', 'MICROSOFT_365']
Mode = Literal['AUTOMATIC', 'MANUAL', 'DISABLED']


def email_address(value: str) -> str:
    if '\r' in value or '\n' in value:
        raise ValueError('Introduce una dirección de correo válida')
    try:
        return validate_email(value, check_deliverability=False, allow_smtputf8=False).normalized
    except EmailNotValidError:
        raise ValueError('Introduce una dirección de correo válida') from None


Address = Annotated[str, Field(strict=True, max_length=254), AfterValidator(email_address)]
Recipients = Annotated[list[Address], Field(max_length=100)]


class MailInput(BaseModel):
    model_config = ConfigDict(extra='forbid')

    @field_validator('*', mode='before')
    @classmethod
    def reject_null(cls, value, info):
        if value is None and info.field_name not in {'provider', 'username'}:
            raise ValueError('El campo no admite null')
        return value


class SmtpUpdate(MailInput):
    host: Annotated[str, Field(strict=True, min_length=1, max_length=253)] | None = None
    port: Annotated[int, Field(strict=True, ge=1, le=65535)] | None = None
    security: Security | None = None
    allow_unencrypted: Annotated[bool, Field(strict=True)] | None = None
    sender_email: Address | None = None
    sender_name: Annotated[str, Field(strict=True, max_length=200)] | None = None
    auth_method: AuthMethod | None = None
    provider: Provider | None = None
    username: Annotated[str, Field(strict=True, max_length=254)] | None = None
    smtp_password: SecretStr | None = Field(default=None, repr=False)
    clear_password: Annotated[bool, Field(strict=True)] = False

    @field_validator('host')
    @classmethod
    def valid_host(cls, value):
        try:
            ipaddress.ip_address(value)
            return value
        except ValueError:
            pass
        if any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label) for label in value.rstrip('.').split('.')):
            raise ValueError('Introduce un servidor SMTP válido, sin URL ni puerto')
        return value

    @field_validator('username', 'sender_name')
    @classmethod
    def no_header_breaks(cls, value):
        if value is not None and ('\n' in value or '\r' in value or '\x00' in value):
            raise ValueError('El campo no admite saltos de línea ni caracteres de control')
        return value.strip() if value else value

    @field_validator('smtp_password')
    @classmethod
    def password_length(cls, value):
        if not 1 <= len(value.get_secret_value().encode('utf-8')) <= 65536:
            raise ValueError('La contraseña debe contener entre 1 y 65536 bytes')
        return value


class SmtpResponse(BaseModel):
    host: str | None = None
    port: int = 587
    security: Security = 'STARTTLS'
    allow_unencrypted: bool = False
    sender_email: str | None = None
    sender_name: str = ''
    auth_method: AuthMethod = 'NONE'
    provider: Provider | None = None
    username: str | None = None
    password_configured: bool = False
    oauth_credentials_configured: bool = False
    configured: bool = False


class EventUpdate(MailInput):
    mode: Mode | None = None
    to: Recipients | None = None
    cc: Recipients | None = None
    bcc: Recipients | None = None

    @field_validator('to', 'cc', 'bcc')
    @classmethod
    def unique_addresses(cls, values):
        seen = set()
        result = []
        for value in values:
            if value.casefold() not in seen:
                result.append(value)
                seen.add(value.casefold())
        return result


class EventResponse(BaseModel):
    event_key: str
    label: str
    mode: Mode = 'DISABLED'
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)


class DynamicFieldResponse(BaseModel):
    id: str
    group: str
    label: str
    format: str
    temporality: str
    source_paths: list[str]
    resolver: str = 'attribute'
