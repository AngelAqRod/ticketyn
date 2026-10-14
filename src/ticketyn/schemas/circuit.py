from typing import ClassVar, Literal
from decimal import Decimal
from pydantic import Field
from typing import Annotated

from ticketyn.schemas.common import AssignmentSummary, InputSchema, NonEmptyString, PositiveId, ResponseSchema


class CircuitCreate(InputSchema):
    sector_id: PositiveId
    nullable_fields: ClassVar[set[str]] = {"initial_capacity", "initial_capacity_unit", "service_type_id"}
    initial_capacity: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6, allow_inf_nan=False)] | None = None
    initial_capacity_unit: Literal['Mbps', 'Gbps'] | None = None
    service_type_id: PositiveId | None = None
    node_id: PositiveId
    customer_id: PositiveId
    circuit_code: NonEmptyString
    description: NonEmptyString
    active: bool = True


class CircuitUpdate(InputSchema):
    sector_id: PositiveId | None = None
    nullable_fields: ClassVar[set[str]] = {"initial_capacity", "initial_capacity_unit", "service_type_id"}
    initial_capacity: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6, allow_inf_nan=False)] | None = None
    initial_capacity_unit: Literal['Mbps', 'Gbps'] | None = None
    service_type_id: PositiveId | None = None
    node_id: PositiveId | None = None
    customer_id: PositiveId | None = None
    circuit_code: NonEmptyString | None = None
    description: NonEmptyString | None = None
    active: bool | None = None


class CircuitResponse(ResponseSchema):
    sector_id: int | None
    sector: AssignmentSummary | None
    service_type_id: int | None
    service_type: AssignmentSummary | None
    initial_capacity: Decimal | None
    initial_capacity_unit: str | None
    node_id: int | None
    node: AssignmentSummary | None
    customer_id: int
    circuit_code: str
    description: str
