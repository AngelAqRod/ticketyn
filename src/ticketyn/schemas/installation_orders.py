"""Validated installation capture inputs; authors and references are server-owned."""
from datetime import datetime
import re
from typing import Annotated, Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]

NORMAL_FIELDS = ('circuit_id',)
EXTRAORDINARY_FIELDS = ('description', 'service_type_id', 'node_id', 'sector_id')
CATALOG_IDS = ('service_type_id', 'node_id', 'sector_id')


class OrderInput(BaseModel):
    """NORMAL needs an existing circuit; EXTRAORDINARY needs description plus service, node and sector catalogs."""
    model_config = ConfigDict(extra='forbid')
    order_type: Literal['NORMAL', 'EXTRAORDINARY']
    customer_id: int = Field(gt=0)
    requested_at: AwareDatetime
    external_reference: Text | None = None
    contact: Text | None = None
    phone: Text | None = None
    notes: Text | None = None
    circuit_id: int | None = Field(default=None, gt=0)
    description: Text | None = None
    service_type_id: int | None = Field(default=None, gt=0)
    node_id: int | None = Field(default=None, gt=0)
    sector_id: int | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def modality(self):
        required, forbidden = (NORMAL_FIELDS, EXTRAORDINARY_FIELDS) if self.order_type == 'NORMAL' else (EXTRAORDINARY_FIELDS, NORMAL_FIELDS)
        if any(getattr(self, key) is None for key in required):
            raise ValueError('Una orden normal requiere circuito.' if self.order_type == 'NORMAL' else 'Una orden extraordinaria requiere descripción, servicio, nodo y sector.')
        if any(getattr(self, key) is not None for key in forbidden):
            raise ValueError('Los campos enviados no corresponden al tipo de orden.')
        return self


class OrderPatch(BaseModel):
    """The type and the circuit are never editable."""
    model_config = ConfigDict(extra='forbid')
    customer_id: int | None = Field(default=None, gt=0)
    requested_at: AwareDatetime | None = None
    external_reference: Text | None = None
    contact: Text | None = None
    phone: Text | None = None
    notes: Text | None = None
    description: Text | None = None
    service_type_id: int | None = Field(default=None, gt=0)
    node_id: int | None = Field(default=None, gt=0)
    sector_id: int | None = Field(default=None, gt=0)

class ProcessInput(OrderInput):
    version: int = Field(default=0, ge=0)

class DraftInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=0)
    data: dict

class DiscardInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: Text

class CircuitLink(BaseModel):
    model_config = ConfigDict(extra='forbid')
    circuit_id: int = Field(gt=0)


class ReceptionFilterInput(BaseModel):
    """Empty lists accept everything. Senders are exact addresses or '@domain'."""
    model_config = ConfigDict(extra='forbid')
    senders: list[str] = Field(max_length=50)
    subjects: list[str] = Field(max_length=50)

    @field_validator('senders', 'subjects')
    @classmethod
    def clean(cls, values):
        cleaned = list(dict.fromkeys(v.strip().lower() for v in values if v.strip()))
        if any(len(v) > 255 for v in cleaned):
            raise ValueError('Cada entrada admite hasta 255 caracteres.')
        return cleaned

    @field_validator('senders')
    @classmethod
    def valid_senders(cls, values):
        for v in values:
            if not re.fullmatch(r'(@|[^@\s]+@)[^@\s]+\.[^@\s]+', v):
                raise ValueError(f'Remitente no válido: {v}. Usa un correo completo o un dominio como @empresa.com.')
        return values
