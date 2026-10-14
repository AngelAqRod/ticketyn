from ticketyn.schemas.common import InputSchema, NonEmptyString, ResponseSchema


class ServiceTypeCreate(InputSchema):
    name: NonEmptyString
    active: bool = True


class ServiceTypeUpdate(InputSchema):
    name: NonEmptyString | None = None
    active: bool | None = None


class ServiceTypeResponse(ResponseSchema):
    name: str
