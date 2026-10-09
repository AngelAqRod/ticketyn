from typing import Literal
from pydantic import AwareDatetime, BaseModel, Field, model_validator
from ticketyn.schemas.common import PositiveId
from ticketyn.schemas.report import ReportFilters, EscalationSummary


class EscalationFilters(BaseModel):
    from_at: AwareDatetime | None = Field(default=None, alias='from')
    to_at: AwareDatetime | None = Field(default=None, alias='to')
    timezone: str = Field(default='UTC', max_length=100)
    granularity: Literal['auto', 'hour', 'day', 'week', 'month'] = 'auto'
    sector_id: PositiveId | None = None
    node_id: PositiveId | None = None
    responsible_id: PositiveId | None = None  # Principal, never the recipient.
    recipient_id: PositiveId | None = None

    @model_validator(mode='after')
    def validate_period(self):
        ReportFilters.valid_timezone(self.timezone)
        if (self.from_at is None) != (self.to_at is None):
            raise ValueError('Completa ambos límites del período')
        if self.from_at is not None:
            ReportFilters.model_validate({'from': self.from_at, 'to': self.to_at, 'timezone': self.timezone, 'granularity': self.granularity})
        return self


class EscalationTicketFilters(EscalationFilters):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
