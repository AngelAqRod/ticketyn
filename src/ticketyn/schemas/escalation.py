from datetime import datetime
from typing import Annotated, Literal
from pydantic import Field, BaseModel, AwareDatetime
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
    nullable_fields = {"requester_id", "recipient_id"}
    requester_id: PositiveId | None = None
    recipient_id: PositiveId | None = None
    department_id: PositiveId | None = None
    started_at: AwareDatetime | None = None
    reason_id: PositiveId
    description: Annotated[str, Field(min_length=1, max_length=10000)]


class EscalationResponse(BaseModel):
    model_config = {'from_attributes': True}
    id: int
    ticket_id: int
    requester_id: int | None
    recipient_id: int | None
    department_id: int | None
    started_at: datetime
    updated_at: datetime
    recipient_level: str | None
    recipient_position_name: str | None
    recipient_department_name: str | None
    reason_id: int
    description: str
    status: Literal['ACTIVE', 'FINISHED']
    created_at: datetime
    finished_at: datetime | None
    requester: AssignmentSummary | None
    recipient: AssignmentSummary | None
    reason: ReasonResponse


class EscalationEdit(InputSchema):
    nullable_fields = {'recipient_id'}
    recipient_id: PositiveId | None = None
    department_id: PositiveId | None = None
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None


class EscalationFinish(InputSchema):
    finished_at: AwareDatetime | None = None


class EscalationAuditResponse(BaseModel):
    model_config = {'from_attributes': True}
    id: int
    escalation_id: int
    event: str
    actor: str | None
    created_at: datetime
    changes: dict
