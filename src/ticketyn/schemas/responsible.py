from ticketyn.schemas.common import InputSchema, NonEmptyString, PositiveId, ResponseSchema, AssignmentSummary


class ResponsibleCreate(InputSchema):
    nullable_fields = {'department_id', 'position_id'}
    department_id: PositiveId | None = None
    position_id: PositiveId | None = None
    name: NonEmptyString
    active: bool = True


class ResponsibleUpdate(InputSchema):
    nullable_fields = {'department_id', 'position_id'}
    department_id: PositiveId | None = None
    position_id: PositiveId | None = None
    name: NonEmptyString | None = None
    active: bool | None = None


class ResponsibleResponse(ResponseSchema):
    # Legacy free text remains readable, never rewritten or inferred into a position.
    attention_level: str | None
    department_id: int | None
    position_id: int | None
    department: AssignmentSummary | None
    position: AssignmentSummary | None
    name: str
