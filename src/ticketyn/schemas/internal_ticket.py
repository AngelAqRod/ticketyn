from datetime import datetime
from typing import Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator
from ticketyn.schemas.common import InputSchema, NonEmptyString, PositiveId, AssignmentSummary, ResponseSchema
from ticketyn.schemas.ticket import OptionalTicketText
from ticketyn.schemas.ticket_update import TicketUpdateCreate
from ticketyn.core.enums import TicketStatus

class InternalTicketCreate(InputSchema):
    nullable_fields = {'node_id', 'responsible_id', 'provider_id', 'resolution', 'end_at'}
    title: NonEmptyString
    description: NonEmptyString
    sector_id: PositiveId
    node_id: PositiveId | None = None
    department_id: PositiveId
    incident_type_id: PositiveId
    responsible_id: PositiveId | None = None
    provider_id: PositiveId | None = None
    resolution: OptionalTicketText | None = None
    start_at: AwareDatetime
    end_at: AwareDatetime | None = None
    status: TicketStatus = TicketStatus.OPEN

class InternalTicketPatch(InputSchema):
    nullable_fields = InternalTicketCreate.nullable_fields
    title: NonEmptyString | None = None
    description: NonEmptyString | None = None
    sector_id: PositiveId | None = None
    node_id: PositiveId | None = None
    department_id: PositiveId | None = None
    incident_type_id: PositiveId | None = None
    responsible_id: PositiveId | None = None
    provider_id: PositiveId | None = None
    resolution: OptionalTicketText | None = None
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    status: TicketStatus | None = None

class InternalTicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ticket_number: int
    reference: str
    title: str
    description: str
    sector_id: int
    node_id: int | None
    department_id: int
    incident_type_id: int
    responsible_id: int | None
    provider_id: int | None
    resolution: str | None
    start_at: datetime
    end_at: datetime | None
    status: TicketStatus
    duration_seconds: float | None
    created_at: datetime
    updated_at: datetime
    sector: AssignmentSummary
    node: AssignmentSummary | None
    department: AssignmentSummary
    incident_type: AssignmentSummary
    provider: AssignmentSummary | None
    responsible: AssignmentSummary | None
    related_count: int

class InternalFilters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    search: str | None = Field(default=None, max_length=500)
    status: TicketStatus | None = None
    sector_id: PositiveId | None = None
    node_id: PositiveId | None = None
    department_id: PositiveId | None = None
    responsible_id: PositiveId | None = None
    incident_type_id: PositiveId | None = None
    provider_id: PositiveId | None = None
    without_provider: bool = False
    from_at: AwareDatetime | None = Field(default=None, alias='from')
    to_at: AwareDatetime | None = Field(default=None, alias='to')
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

class InternalUpdateCreate(TicketUpdateCreate):
    # A public visibility is rejected, not silently converted.
    visibility: Literal['INTERNAL'] = 'INTERNAL'

class ProviderCreate(InputSchema):
    nullable_fields = {'description'}
    name: NonEmptyString
    description: str | None = Field(default=None, max_length=10000)
    active: bool = True

class ProviderPatch(InputSchema):
    nullable_fields = {'description'}
    name: NonEmptyString | None = None
    description: str | None = Field(default=None, max_length=10000)
    active: bool | None = None

class ProviderResponse(ResponseSchema):
    name: str
    description: str | None


class InternalExportFilters(InternalFilters):
    timezone: str = Field(default='UTC', max_length=100)

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        from ticketyn.schemas.report import ReportFilters
        return ReportFilters.valid_timezone(value)
