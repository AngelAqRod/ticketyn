from typing import Annotated
from pydantic import Field
from ticketyn.schemas.common import InputSchema, PositiveId, ResponseSchema, AssignmentSummary


class PositionCreate(InputSchema):
    nullable_fields = {'description'}
    department_id: PositiveId
    name: Annotated[str, Field(min_length=1, max_length=100)]
    description: Annotated[str, Field(min_length=1, max_length=10000)] | None = None
    active: bool = True


class PositionUpdate(InputSchema):
    nullable_fields = {'description'}
    department_id: PositiveId | None = None
    name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    description: Annotated[str, Field(min_length=1, max_length=10000)] | None = None
    active: bool | None = None


class PositionResponse(ResponseSchema):
    department_id: int
    name: str
    description: str | None
    department: AssignmentSummary
