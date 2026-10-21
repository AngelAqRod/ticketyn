"""Security audit query and retention contracts; no deletion operations."""
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from ticketyn.security.audit import EVENTS


class AuditFilters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    from_at: AwareDatetime | None = None
    to_at: AwareDatetime | None = None
    actor_id: int | None = Field(default=None, gt=0)
    username: str | None = Field(default=None, max_length=100)
    event: str | None = Field(default=None, max_length=100)
    result: Literal['SUCCESS', 'FAILURE', 'ALL'] = 'ALL'
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=50, le=50)

    @field_validator('event')
    @classmethod
    def event_exists(cls, value):
        if value is not None and value not in EVENTS:
            raise ValueError('Tipo de evento no permitido')
        return value

    @model_validator(mode='after')
    def coherent_period(self):
        if self.from_at is not None and self.to_at is not None and self.from_at >= self.to_at:
            raise ValueError('El inicio del período debe ser anterior al final')
        return self


class AuditPerson(BaseModel):
    id: int
    name: str
    username: str | None


class AuditDetail(BaseModel):
    label: str
    value: str


class AuditEntry(BaseModel):
    id: int
    occurred_at: datetime
    actor: AuditPerson | None
    target: AuditPerson | None
    identifier: str | None
    event: str
    event_label: str
    source: str
    success: bool
    details: list[AuditDetail]


class AuditEventOption(BaseModel):
    code: str
    label: str


class AuditPage(BaseModel):
    items: list[AuditEntry]
    total: int
    limit: int
    offset: int
    events: list[AuditEventOption]


class AuditRetention(BaseModel):
    retention_days: int


class AuditRetentionUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    retention_days: int = Field(strict=True, ge=1, le=3650)
    expected_days: int = Field(strict=True, ge=1, le=3650)
    confirm_reduction: bool = Field(default=False, strict=True)
