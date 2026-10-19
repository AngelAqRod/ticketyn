"""Structured plain-text templates, never executable expressions."""
import re
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictBlock(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class SubjectText(StrictBlock):
    type: Literal['text']
    text: str = Field(max_length=998)

    @field_validator('text')
    @classmethod
    def single_line(cls, value):
        if re.search(r'[\x00-\x1f\x7f\u2028\u2029]', value):
            raise ValueError('El asunto no admite saltos de línea ni caracteres de control.')
        return value


class FieldBlock(StrictBlock):
    type: Literal['field']
    field_id: str = Field(min_length=1, max_length=100)


class BodyText(StrictBlock):
    type: Literal['introduction', 'signature']
    text: str = Field(max_length=10000)


class BodyField(FieldBlock):
    label_mode: Literal['DEFAULT', 'CUSTOM'] = 'DEFAULT'
    custom_label: str | None = Field(default=None, max_length=100)

    @model_validator(mode='after')
    def label_valid(self):
        if self.label_mode == 'CUSTOM':
            if not self.custom_label or not self.custom_label.strip() or re.search(r'[\x00-\x1f\x7f\u2028\u2029]', self.custom_label):
                raise ValueError('Introduce una etiqueta personalizada de una sola línea.')
        elif self.custom_label is not None:
            raise ValueError('Por defecto utiliza exclusivamente la etiqueta del campo.')
        return self


class MailTemplate(StrictBlock):
    version: Literal[1] = 1
    subject: list[Annotated[SubjectText | FieldBlock, Field(discriminator='type')]] = Field(default_factory=list, max_length=50)
    body: list[Annotated[BodyText | BodyField, Field(discriminator='type')]] = Field(default_factory=list, max_length=50)


class PreviewRequest(StrictBlock):
    activation_id: int = Field(gt=0)
    template: MailTemplate


class PreviewResponse(StrictBlock):
    subject: str
    body: str
