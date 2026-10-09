from datetime import datetime, timezone

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from ticketyn.core.enums import TicketUpdateVisibility
from ticketyn.schemas.common import AssignmentSummary, InputSchema, NonEmptyString, PositiveId


class TicketUpdateCreate(InputSchema):
    nullable_fields = {"responsible_id", "escalation_id"}

    escalation_id: PositiveId | None = None
    content: NonEmptyString
    occurred_at: AwareDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    responsible_id: PositiveId | None = None
    visibility: TicketUpdateVisibility = TicketUpdateVisibility.INTERNAL

    @field_validator("occurred_at")
    @classmethod
    def utc_instant(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


class TicketUpdateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    escalation_id: int | None
    content: str
    occurred_at: datetime
    created_at: datetime
    responsible_id: int | None
    responsible: AssignmentSummary | None
    visibility: TicketUpdateVisibility


class TicketUpdatePage(BaseModel):
    items: list[TicketUpdateResponse]
    next_cursor: str | None
