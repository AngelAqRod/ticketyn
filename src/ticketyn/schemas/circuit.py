from typing import ClassVar

from ticketyn.schemas.common import AssignmentSummary, InputSchema, NonEmptyString, PositiveId, ResponseSchema


class CircuitCreate(InputSchema):
    nullable_fields: ClassVar[set[str]] = {"node_id"}
    node_id: PositiveId | None = None
    customer_id: PositiveId
    circuit_code: NonEmptyString
    description: NonEmptyString
    active: bool = True


class CircuitUpdate(InputSchema):
    nullable_fields: ClassVar[set[str]] = {"node_id"}
    node_id: PositiveId | None = None
    customer_id: PositiveId | None = None
    circuit_code: NonEmptyString | None = None
    description: NonEmptyString | None = None
    active: bool | None = None


class CircuitResponse(ResponseSchema):
    node_id: int | None
    node: AssignmentSummary | None
    customer_id: int
    circuit_code: str
    description: str
