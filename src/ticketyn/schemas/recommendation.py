from datetime import datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field
from ticketyn.schemas.common import InputSchema, AssignmentSummary


class AckCreate(InputSchema):
    duration_type: Literal['1H', '4H', '8H', 'INDEFINITE'] = '1H'
    reason: Annotated[str, Field(min_length=1, max_length=10000)]


class AckRevoke(InputSchema):
    nullable_fields = {'reason'}
    reason: Annotated[str, Field(min_length=1, max_length=10000)] | None = None


class AckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ticket_id: int
    duration_type: str
    reason: str
    active: bool
    acknowledged_at: datetime
    expires_at: datetime | None
    acknowledged_by: AssignmentSummary
    acknowledged_by_position: AssignmentSummary | None = None
    revoked_by: AssignmentSummary | None = None
    revoked_at: datetime | None = None
    revoked_reason: str | None = None


class RecommendationItem(BaseModel):
    target_position_id: int
    target_position_name: str
    target_department_name: str
    threshold_minutes: int
    elapsed_minutes: int
    overdue_minutes: int


class TicketRecommendationsResponse(BaseModel):
    ticket_id: int
    ticket_status: str
    stage_name: str
    reference_position_id: int | None
    reference_position_name: str | None
    stage_started_at: datetime | None
    elapsed_minutes: int
    has_active_ack: bool
    active_ack: AckResponse | None = None
    can_acknowledge: bool = False
    recommendations: list[RecommendationItem] = []
