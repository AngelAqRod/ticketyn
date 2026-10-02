from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TicketNumberConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prefix: str | None = None
    separator: str | None = None
    next_number: Annotated[int, Field(gt=0, le=2147483647, strict=True)] | None = None
    padding: Annotated[int, Field(ge=0, le=20, strict=True)] | None = Field(
        default=None, examples=[3]
    )

    @field_validator("*", mode="before")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("El campo no admite null")
        return value


class TicketNumberConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    prefix: str
    separator: str
    next_number: int
    padding: int
