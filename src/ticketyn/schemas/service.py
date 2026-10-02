from ticketyn.schemas.common import InputSchema, NonEmptyString, ResponseSchema


class ServiceCreate(InputSchema):
    name: NonEmptyString


class ServiceUpdate(InputSchema):
    name: NonEmptyString | None = None
    active: bool | None = None


class ServiceResponse(ResponseSchema):
    name: str
