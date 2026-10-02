from ticketyn.schemas.common import InputSchema, NonEmptyString, ResponseSchema


class DepartmentCreate(InputSchema):
    name: NonEmptyString
    active: bool = True


class DepartmentUpdate(InputSchema):
    name: NonEmptyString | None = None
    active: bool | None = None


class DepartmentResponse(ResponseSchema):
    name: str
