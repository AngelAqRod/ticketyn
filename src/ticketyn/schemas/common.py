from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

NonEmptyString = Annotated[str, Field(min_length=1)]
PositiveId = Annotated[int, Field(gt=0)]


class InputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("*", mode="before")
    @classmethod
    def validate_supplied_values(cls, value):
        if value is None:
            raise ValueError("El campo no admite null")
        if isinstance(value, str) and not value.strip():
            raise ValueError("El campo no puede estar vacío")
        return value


class ResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    active: bool
    created_at: datetime
