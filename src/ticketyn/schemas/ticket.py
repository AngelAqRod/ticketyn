from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from ticketyn.core.enums import TicketStatus
from ticketyn.schemas.common import NonEmptyString, PositiveId, AssignmentSummary


OptionalTicketText = Annotated[str, Field(min_length=1, max_length=10000)]


class TicketInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def validate_supplied_values(cls, value, info):
        if value is None and info.field_name not in {"end_at", "responsible_id", "resolution", "customer_description", "customer_resolution", "internal_ticket_id"}:
            raise ValueError("El campo no admite null")
        if isinstance(value, str) and not value.strip():
            raise ValueError("El campo no puede estar vacío")
        return value


class TicketCreate(TicketInput):
    internal_ticket_id: PositiveId | None = None
    node_id: PositiveId | None = None
    resolution: OptionalTicketText | None = None
    customer_description: OptionalTicketText | None = None
    customer_resolution: OptionalTicketText | None = None
    responsible_id: PositiveId | None = None
    title: NonEmptyString
    description: NonEmptyString
    customer_id: PositiveId
    circuit_id: PositiveId
    sector_id: PositiveId | None = None
    department_id: PositiveId
    incident_type_id: PositiveId
    start_at: AwareDatetime
    end_at: AwareDatetime | None = None
    status: TicketStatus = TicketStatus.OPEN


class TicketUpdate(TicketInput):
    internal_ticket_id: PositiveId | None = None
    node_id: PositiveId | None = None
    resolution: OptionalTicketText | None = None
    customer_description: OptionalTicketText | None = None
    customer_resolution: OptionalTicketText | None = None
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
    internal_ticket_id: int | None = None
    node_id: int | None
    resolution: str | None
    customer_description: str | None
    customer_resolution: str | None
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


class OpenOverviewSector(BaseModel):
    id: int
    name: str
    count: int


class OpenOverview(BaseModel):
    """Abiertos por antigüedad (excluyentes), sin responsable (transversal) y por sector."""
    generated_at: AwareDatetime
    open: int
    buckets: dict[Literal["lt_1h", "1_to_4h", "4_to_24h", "gt_24h"], int]
    future_start: int
    unassigned: int
    sectors: list[OpenOverviewSector]


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
    age_bucket: Literal["lt_1h", "1_to_4h", "4_to_24h", "gt_24h"] | None = Field(default=None, description="Tramo de antigüedad de tickets abiertos (misma clasificación que el Dashboard)")
    unassigned: bool = Field(default=False, description="Solo tickets sin responsable")
    order: Literal["start_at_asc", "start_at_desc"] | None = Field(default=None, description="Orden por start_at; por omisión, más recientes primero")
    from_at: AwareDatetime | None = Field(default=None, alias="from", description="Inicio inclusivo del rango sobre start_at; timestamp con timezone")
    to_at: AwareDatetime | None = Field(default=None, alias="to", description="Fin exclusivo del rango sobre start_at; timestamp con timezone")

    @model_validator(mode="after")
    def valid_range(self):
        if self.from_at is not None and self.to_at is not None and self.to_at <= self.from_at:
            raise ValueError("to debe ser posterior a from")
        if self.unassigned and self.responsible_id is not None:
            raise ValueError("unassigned y responsible_id son excluyentes")
        return self

    limit: Annotated[int, Field(ge=1, le=200)] = 50
    offset: Annotated[int, Field(ge=0)] = 0
