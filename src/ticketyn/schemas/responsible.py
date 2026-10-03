from ticketyn.schemas.common import InputSchema, NonEmptyString, ResponseSchema


class ResponsibleCreate(InputSchema):
    name: NonEmptyString
    active: bool = True


class ResponsibleUpdate(InputSchema):
    name: NonEmptyString | None = None
    active: bool | None = None


class ResponsibleResponse(ResponseSchema):
    name: str
