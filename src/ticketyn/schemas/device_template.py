from typing import Annotated
from pydantic import BaseModel, Field
from ticketyn.schemas.common import InputSchema, ResponseSchema
from ticketyn.schemas.port_nomenclature import PortNumbering, Number


class TemplateGroup(PortNumbering):
    end: Number


class TemplateInput(InputSchema):
    nullable_fields = {'manufacturer', 'description', 'preview_token'}
    name: Annotated[str, Field(min_length=1, max_length=255)]
    manufacturer: Annotated[str, Field(max_length=255)] | None = None
    description: Annotated[str, Field(max_length=10000)] | None = None
    active: bool = True
    groups: list[TemplateGroup] = Field(min_length=1, max_length=16)
    preview_token: str | None = Field(default=None, max_length=64)


class TemplateGroupView(TemplateGroup):
    nullable_fields = {'warning'}
    nomenclature_name: str
    prefix: str
    names: list[str]
    warning: str | None = None


class TemplatePreview(BaseModel):
    groups: list[TemplateGroupView]
    total_ports: int
    usable: bool
    preview_token: str


class TemplateResponse(ResponseSchema, TemplatePreview):
    name: str
    manufacturer: str | None
    description: str | None
