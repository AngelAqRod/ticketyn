from datetime import datetime
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from ticketyn.core.enums import TicketStatus
from ticketyn.schemas.common import NonEmptyString, PositiveId, AssignmentSummary


class TicketInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def validate_supplied_values(cls, value, info):
        if value is None and info.field_name not in {"end_at", "responsible_id"}:
            raise ValueError("El campo no admite null")
        if isinstance(value, str) and not value.strip():
            raise ValueError("El campo no puede estar vacío")
        return value


class TicketCreate(TicketInput):
    responsible_id: PositiveId | None = None
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
    responsible_id: PositiveId | None = None
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
    responsible_id: int | None
    responsible: AssignmentSummary | None
    node: AssignmentSummary | None
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


class CustomerSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_code: str
    name: str


class CircuitSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    circuit_code: str
    description: str


class CatalogSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class TicketListResponse(TicketResponse):
    customer: CustomerSummary
    circuit: CircuitSummary
    sector: CatalogSummary
    department: CatalogSummary
    incident_type: CatalogSummary


class TicketStats(BaseModel):
    total: int
    open: int
    closed: int


class TicketFilters(BaseModel):
    node_id: PositiveId | None = None
    responsible_id: PositiveId | None = None
    status: TicketStatus | None = None
    customer_id: PositiveId | None = None
    circuit_id: PositiveId | None = None
    sector_id: PositiveId | None = None
    department_id: PositiveId | None = None
    incident_type_id: PositiveId | None = None
    search: str | None = None
    from_at: AwareDatetime | None = Field(default=None, alias="from", description="Inicio inclusivo del rango sobre start_at; timestamp con timezone")
    to_at: AwareDatetime | None = Field(default=None, alias="to", description="Fin exclusivo del rango sobre start_at; timestamp con timezone")

    @model_validator(mode="after")
    def valid_range(self):
        if self.from_at is not None and self.to_at is not None and self.to_at <= self.from_at:
            raise ValueError("to debe ser posterior a from")
        return self

    limit: Annotated[int, Field(ge=1, le=200)] = 50
    offset: Annotated[int, Field(ge=0)] = 0
