from datetime import date
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from ticketyn.schemas.common import InputSchema, NonEmptyString, PositiveId, ResponseSchema


Status = Literal['REGISTERED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED']
PERIOD_ERROR = 'El fin del período no puede ser anterior a su inicio'


class AdminRequestTypeCreate(InputSchema):
    nullable_fields = {'description'}
    name: NonEmptyString
    description: str | None = None
    active: bool = True


class AdminRequestTypePatch(InputSchema):
    nullable_fields = {'description'}
    name: NonEmptyString | None = None
    description: str | None = None
    active: bool | None = None


class AdminRequestTypeResponse(ResponseSchema):
    name: str
    description: str | None


class AdminRequestCreate(InputSchema):
    nullable_fields = {'customer_id', 'circuit_id', 'notes', 'application_start', 'application_end'}
    request_date: date
    requester_id: PositiveId
    customer_id: PositiveId | None = None
    circuit_id: PositiveId | None = None
    type_id: PositiveId
    description: str = Field(max_length=50000)
    notes: str | None = Field(default=None, max_length=50000)
    application_start: date | None = None
    application_end: date | None = None

    @model_validator(mode='after')
    def period(self):
        if self.application_start and self.application_end and self.application_end < self.application_start:
            raise ValueError(PERIOD_ERROR)
        return self


class AdminRequestPatch(InputSchema):
    nullable_fields = {'customer_id', 'circuit_id', 'notes', 'application_start', 'application_end'}
    request_date: date | None = None
    requester_id: PositiveId | None = None
    customer_id: PositiveId | None = None
    circuit_id: PositiveId | None = None
    type_id: PositiveId | None = None
    description: str | None = Field(default=None, max_length=50000)
    notes: str | None = Field(default=None, max_length=50000)
    application_start: date | None = None
    application_end: date | None = None


class AdminRequestStatusChange(InputSchema):
    status: Status


class AdminRequestFilters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    date_from: date | None = None
    date_to: date | None = None
    requester_id: PositiveId | None = None
    type_id: PositiveId | None = None
    customer_id: PositiveId | None = None
    circuit_id: PositiveId | None = None
    status: Status | None = None
    search: str | None = None
    limit: Annotated[int, Field(ge=1, le=200)] = 50
    offset: Annotated[int, Field(ge=0)] = 0


class AdminRequestLinkCreate(InputSchema):
    kind: Literal['ticket', 'internal_ticket', 'change']
    target_id: PositiveId
