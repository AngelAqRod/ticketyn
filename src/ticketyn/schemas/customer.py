from ticketyn.schemas.common import InputSchema, NonEmptyString, ResponseSchema


class CustomerCreate(InputSchema):
    customer_code: NonEmptyString
    name: NonEmptyString
    active: bool = True


class CustomerUpdate(InputSchema):
    customer_code: NonEmptyString | None = None
    name: NonEmptyString | None = None
    active: bool | None = None


class CustomerResponse(ResponseSchema):
    customer_code: str
    name: str
