from typing import Literal
from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator
from ticketyn.schemas.common import PositiveId
from ticketyn.schemas.report import ReportFilters


class OperationExportFilters(BaseModel):
    customer_id: PositiveId | None = None
    circuit_id: PositiveId | None = None
    from_at: AwareDatetime | None = None
    to_at: AwareDatetime | None = None
    timezone: str = Field(default='America/Guatemala', max_length=100)

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        return ReportFilters.valid_timezone(value)

    @model_validator(mode='after')
    def valid_range(self):
        if self.from_at and self.to_at and self.from_at >= self.to_at:
            raise ValueError('El inicio del período debe ser anterior al final')
        return self


class CapacityExportFilters(OperationExportFilters):
    operation_type: Literal['INCREASE', 'DECREASE'] | None = None


class LifecycleExportFilters(OperationExportFilters):
    operation_type: Literal['DEACTIVATE', 'REACTIVATE'] | None = None
