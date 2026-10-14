import re
from pydantic import Field, field_validator
from ticketyn.schemas.common import InputSchema, ResponseSchema


class CpeModelCreate(InputSchema):
    name: str = Field(min_length=1, max_length=255)
    active: bool = True

    @field_validator('name', mode='before')
    @classmethod
    def normalize(cls, value):
        return re.sub(r'\s+', ' ', value).strip() if isinstance(value, str) else value


class CpeModelUpdate(CpeModelCreate):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    active: bool | None = None


class CpeModelResponse(ResponseSchema):
    name: str
