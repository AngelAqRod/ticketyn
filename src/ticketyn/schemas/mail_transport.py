"""Stage 5 input is configuration only, never arbitrary messages/token URLs."""
import re
from uuid import UUID
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from ticketyn.schemas.mail_notifications import Address, MailInput


class TestMailRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    recipient: Address


class TestMailResponse(BaseModel):
    status: str
    message: str


class OAuthUpdate(MailInput):
    client_id: Annotated[str, Field(min_length=1, max_length=254)] | None = None
    tenant_id: Annotated[str, Field(min_length=1, max_length=36)] | None = None
    client_secret: SecretStr | None = Field(default=None, repr=False)
    service_account: SecretStr | None = Field(default=None, repr=False)

    @field_validator('client_id')
    @classmethod
    def client_id_valid(cls, value):
        if not re.fullmatch(r'[A-Za-z0-9._-]+', value):
            raise ValueError('Identificador de aplicación inválido')
        return value

    @field_validator('tenant_id')
    @classmethod
    def tenant_valid(cls, value):
        try: return str(UUID(value))
        except ValueError:
            raise ValueError('Introduce el identificador UUID del tenant de Microsoft 365') from None

    @field_validator('client_secret', 'service_account')
    @classmethod
    def secret_valid(cls, value, info):
        limit = 20000 if info.field_name == 'service_account' else 4096
        if not 1 <= len(value.get_secret_value().encode()) <= limit:
            raise ValueError('La credencial está vacía o supera la longitud permitida')
        return value


class OAuthResponse(BaseModel):
    client_id: str = ''
    tenant_id: str = ''
    redirect_uri: str | None = None
    status: str = 'UNCONFIGURED'
    client_secret_configured: bool = False
    service_account_configured: bool = False
