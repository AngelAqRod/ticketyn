from datetime import datetime
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from ticketyn.core.enums import TicketStatus
from ticketyn.schemas.common import NonEmptyString, PositiveId


class TicketInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def validate_supplied_values(cls, value, info):
        if value is None and info.field_name != "end_at":
            raise ValueError("El campo no admite null")
        if isinstance(value, str) and not value.strip():
            raise ValueError("El campo no puede estar vacío")
        return value


class TicketCreate(TicketInput):
    title: NonEmptyString
    description: NonEmptyString
    customer_id: PositiveId
    circuit_id: PositiveId
    sector_id: PositiveId
    department_id: PositiveId
    incident_type_id: PositiveId
    start_at: AwareDatetime
    end_at: AwareDatetime | None = None
    status: TicketStatus = TicketStatus.OPEN


class TicketUpdate(TicketInput):
    title: NonEmptyString | None = None
    description: NonEmptyString | None = None
    customer_id: PositiveId | None = None
    circuit_id: PositiveId | None = None
    sector_id: PositiveId | None = None
    department_id: PositiveId | None = None
    incident_type_id: PositiveId | None = None
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    status: TicketStatus | None = None


class TicketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_number: int
    reference: str
    title: str
    description: str
    customer_id: int
    circuit_id: int
    sector_id: int
    department_id: int
    incident_type_id: int
    start_at: datetime
    end_at: datetime | None
    status: TicketStatus
    duration_seconds: float | None
    created_at: datetime
    updated_at: datetime


class TicketFilters(BaseModel):
    status: TicketStatus | None = None
    customer_id: PositiveId | None = None
    circuit_id: PositiveId | None = None
    sector_id: PositiveId | None = None
    department_id: PositiveId | None = None
    incident_type_id: PositiveId | None = None
    search: str | None = None
    limit: Annotated[int, Field(ge=1, le=200)] = 50
    offset: Annotated[int, Field(ge=0)] = 0
