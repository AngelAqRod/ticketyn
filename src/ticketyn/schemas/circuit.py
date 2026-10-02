from ticketyn.schemas.common import InputSchema, NonEmptyString, PositiveId, ResponseSchema


class CircuitCreate(InputSchema):
    customer_id: PositiveId
    circuit_code: NonEmptyString
    description: NonEmptyString
    active: bool = True


class CircuitUpdate(InputSchema):
    customer_id: PositiveId | None = None
    circuit_code: NonEmptyString | None = None
    description: NonEmptyString | None = None
    active: bool | None = None


class CircuitResponse(ResponseSchema):
    customer_id: int
    circuit_code: str
    description: str
