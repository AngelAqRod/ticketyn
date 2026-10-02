from ticketyn.schemas.common import InputSchema, NonEmptyString, ResponseSchema


class SectorCreate(InputSchema):
    name: NonEmptyString


class SectorUpdate(InputSchema):
    name: NonEmptyString | None = None
    active: bool | None = None


class SectorResponse(ResponseSchema):
    name: str
