from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field
from ticketyn.schemas.common import InputSchema, PositiveId, ResponseSchema, AssignmentSummary


class PositionDestinationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_position_id: PositiveId
    time_minutes: Annotated[int, Field(ge=1, le=10080)] | None = None


class PositionDestinationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    target_position_id: int
    target_position_name: str
    target_department_name: str
    time_minutes: int | None
    order_index: int
    active: bool


class PositionCreate(InputSchema):
    nullable_fields = {'description', 'general_escalation_time_minutes', 'destinations'}
    department_id: PositiveId
    name: Annotated[str, Field(min_length=1, max_length=100)]
    description: Annotated[str, Field(min_length=1, max_length=10000)] | None = None
    active: bool = True
    escalation_mode: Literal['GENERAL', 'INDIVIDUAL'] = 'GENERAL'
    general_escalation_time_minutes: Annotated[int, Field(ge=1, le=10080)] | None = None
    destinations: list[PositionDestinationInput] | None = None


class PositionUpdate(InputSchema):
    nullable_fields = {'description', 'general_escalation_time_minutes', 'destinations'}
    department_id: PositiveId | None = None
    name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    description: Annotated[str, Field(min_length=1, max_length=10000)] | None = None
    active: bool | None = None
    escalation_mode: Literal['GENERAL', 'INDIVIDUAL'] | None = None
    general_escalation_time_minutes: Annotated[int, Field(ge=1, le=10080)] | None = None
    destinations: list[PositionDestinationInput] | None = None


class PositionResponse(ResponseSchema):
    department_id: int
    name: str
    description: str | None
    escalation_mode: str = 'GENERAL'
    general_escalation_time_minutes: int | None = None
    destinations: list[PositionDestinationResponse] = []
    department: AssignmentSummary
