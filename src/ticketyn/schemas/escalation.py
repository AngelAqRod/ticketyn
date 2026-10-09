from datetime import datetime
from typing import Annotated, Literal
from pydantic import Field, BaseModel
from ticketyn.schemas.common import InputSchema, NonEmptyString, PositiveId, ResponseSchema, AssignmentSummary


class ReasonCreate(InputSchema):
    nullable_fields = {'description'}
    name: NonEmptyString
    description: Annotated[str, Field(min_length=1, max_length=10000)] | None = None
    active: bool = True


class ReasonUpdate(InputSchema):
    nullable_fields = {'description'}
    name: NonEmptyString | None = None
    description: Annotated[str, Field(min_length=1, max_length=10000)] | None = None
    active: bool | None = None


class ReasonResponse(ResponseSchema):
    name: str
    description: str | None


class EscalationCreate(InputSchema):
    nullable_fields = {"requester_id"}
    requester_id: PositiveId | None = None
    recipient_id: PositiveId
    reason_id: PositiveId
    description: Annotated[str, Field(min_length=1, max_length=10000)]


class EscalationResponse(BaseModel):
    model_config = {'from_attributes': True}
    id: int
    ticket_id: int
    requester_id: int | None
    recipient_id: int
    recipient_level: str | None
    recipient_position_name: str | None
    recipient_department_name: str | None
    reason_id: int
    description: str
    status: Literal['ACTIVE', 'FINISHED']
    created_at: datetime
    finished_at: datetime | None
    requester: AssignmentSummary | None
    recipient: AssignmentSummary
    reason: ReasonResponse
