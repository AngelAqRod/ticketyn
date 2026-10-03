from ticketyn.schemas.common import InputSchema, NonEmptyString, ResponseSchema


class NodeCreate(InputSchema):
    name: NonEmptyString
    active: bool = True


class NodeUpdate(InputSchema):
    name: NonEmptyString | None = None
    active: bool | None = None


class NodeResponse(ResponseSchema):
    name: str
