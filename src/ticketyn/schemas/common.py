from datetime import datetime
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

NonEmptyString = Annotated[str, Field(min_length=1)]
PositiveId = Annotated[int, Field(gt=0)]


class InputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nullable_fields: ClassVar[set[str]] = set()

    @field_validator("*", mode="before")
    @classmethod
    def validate_supplied_values(cls, value, info):
        if value is None and info.field_name not in cls.nullable_fields:
            raise ValueError("El campo no admite null")
        if isinstance(value, str) and not value.strip():
            raise ValueError("El campo no puede estar vacío")
        return value


class ResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    active: bool
    created_at: datetime


class AssignmentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    active: bool
