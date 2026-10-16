from typing import Literal
from pydantic import AwareDatetime, Field, model_validator
from ticketyn.schemas.common import InputSchema, NonEmptyString, PositiveId, ResponseSchema
from ticketyn.schemas.report import ReportFilters

ChangeStatus = Literal['SCHEDULED', 'EXECUTING', 'FINISHED']

class CompletionCreate(InputSchema):
    nullable_fields = {'description'}
    name: NonEmptyString
    description: str | None = None
    active: bool = True
    applies_efficiency: bool = False

class CompletionPatch(InputSchema):
    nullable_fields = {'description'}
    name: NonEmptyString | None = None
    description: str | None = None
    active: bool | None = None
    applies_efficiency: bool | None = None

class CompletionResponse(ResponseSchema):
    name: str
    description: str | None
    applies_efficiency: bool

class ChangeTypeCreate(InputSchema):
    nullable_fields = {'description'}
    name: NonEmptyString
    description: str | None = None
    active: bool = True

class ChangeTypePatch(InputSchema):
    nullable_fields = {'description'}
    name: NonEmptyString | None = None
    description: str | None = None
    active: bool | None = None

class ChangeTypeResponse(ResponseSchema):
    name: str
    description: str | None

class ChangeCreate(InputSchema):
    nullable_fields = {'node_id','actual_start','actual_end','completion_type_id','final_notes'}
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=50000)
    change_type_id: PositiveId
    sector_id: PositiveId
    node_id: PositiveId | None = None
    manager_id: PositiveId
    support_ids: list[PositiveId] = Field(default_factory=list, max_length=200)
    internal_ticket_ids: list[PositiveId] = Field(default_factory=list, max_length=500)
    status: ChangeStatus = 'SCHEDULED'
    proposed_start: AwareDatetime
    proposed_end: AwareDatetime
    actual_start: AwareDatetime | None = None
    actual_end: AwareDatetime | None = None
    completion_type_id: PositiveId | None = None
    final_notes: str | None = Field(default=None, max_length=50000)

class ChangePatch(ChangeCreate):
    change_type_id: PositiveId | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, min_length=1, max_length=50000)
    sector_id: PositiveId | None = None
    manager_id: PositiveId | None = None
    proposed_start: AwareDatetime | None = None
    proposed_end: AwareDatetime | None = None

class ChangeFilters(ReportFilters):
    change_type_id: PositiveId | None = None
    search: str | None = Field(default=None, max_length=500)
    status: ChangeStatus | None = None
    manager_id: PositiveId | None = None
    support_id: PositiveId | None = None
    involved_id: PositiveId | None = None
    department_id: PositiveId | None = None
    completion_type_id: PositiveId | None = None
    internal_ticket_id: PositiveId | None = None
    sort: Literal['proposed_start','reference','created_at','status','title'] = 'proposed_start'
    direction: Literal['asc','desc'] = 'desc'
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)

class ChangeUpdateCreate(InputSchema):
    responsible_id: PositiveId
    occurred_at: AwareDatetime
    content: str = Field(min_length=1, max_length=50000)
