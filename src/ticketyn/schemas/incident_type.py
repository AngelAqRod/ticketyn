from ticketyn.schemas.common import InputSchema, NonEmptyString, ResponseSchema


class IncidentTypeCreate(InputSchema):
    name: NonEmptyString
    active: bool = True


class IncidentTypeUpdate(InputSchema):
    name: NonEmptyString | None = None
    active: bool | None = None


class IncidentTypeResponse(ResponseSchema):
    name: str
