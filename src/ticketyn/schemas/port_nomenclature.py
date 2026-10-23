from typing import Annotated, Literal
from pydantic import Field, StrictInt, model_validator, field_validator
from ticketyn.schemas.common import InputSchema, PositiveId, ResponseSchema

NumberFormat = Literal['N', 'X/Y', 'X/Y/Z', 'W/X/Y/Z']
Number = Annotated[StrictInt, Field(ge=0)]


class NomenclatureInput(InputSchema):
    name: Annotated[str, Field(min_length=1, max_length=255)]
    prefix: Annotated[str, Field(min_length=1, max_length=200)]
    formats: list[NumberFormat] = Field(max_length=4)
    active: bool = True

    @field_validator('prefix')
    @classmethod
    def printable_prefix(cls, value):
        if not value.strip() or not value.isprintable():
            raise ValueError('El prefijo debe contener caracteres imprimibles y no puede estar vacío')
        return value

    @model_validator(mode='after')
    def valid_formats(self):
        if len(set(self.formats)) != len(self.formats) or (self.active and not self.formats):
            raise ValueError('Selecciona formatos distintos y al menos uno para nomenclaturas activas')
        return self


class NomenclatureResponse(ResponseSchema):
    name: str
    prefix: str
    formats: list[NumberFormat]


class PortGeneration(InputSchema):
    nullable_fields = {'description', 'preview_token'}
    distribution_device_id: PositiveId
    nomenclature_id: PositiveId
    numbering_format: NumberFormat
    positions: list[Number] = Field(default_factory=list, max_length=3)
    start: Number
    end: Number | None = None
    mode: Literal['complete', 'missing'] = 'complete'
    description: Annotated[str, Field(max_length=10000)] | None = None
    preview_token: str | None = Field(default=None, max_length=64)

    @model_validator(mode='after')
    def valid_range(self):
        end = self.start if self.end is None else self.end
        if end < self.start or end - self.start + 1 > 256:
            raise ValueError('El rango debe estar ordenado y solicitar entre 1 y 256 nombres')
        if len(self.positions) != self.numbering_format.count('/'):
            raise ValueError('Las posiciones no corresponden al formato numérico')
        return self


from pydantic import BaseModel
from ticketyn.schemas.distribution import PortResponse, DistributionEdit


class PreviewName(BaseModel):
    name: str
    existing: bool


class PortPreview(BaseModel):
    names: list[PreviewName]
    total: int
    existing_count: int
    create_count: int
    preview_token: str
    blocked: bool


class PortBatchResponse(BaseModel):
    created: list[PortResponse]
    existing_count: int
    total: int


class PortEdit(DistributionEdit):
    nullable_fields = {'description', 'nomenclature_id', 'numbering_format', 'number_components'}
    nomenclature_id: PositiveId | None = None
    numbering_format: NumberFormat | None = None
    number_components: list[Number] | None = Field(default=None, min_length=1, max_length=4)
