from typing import Annotated, ClassVar

from pydantic import BaseModel, Field, StrictBool

from ticketyn.schemas.common import InputSchema, PositiveId, ResponseSchema

Name = Annotated[str, Field(min_length=1, max_length=255)]
Description = Annotated[str, Field(max_length=10000)]


class DistributionEdit(InputSchema):
    nullable_fields: ClassVar[set[str]] = {'description'}
    name: Name | None = None
    description: Description | None = None


class DeviceCreate(InputSchema):
    nullable_fields: ClassVar[set[str]] = {'description'}
    node_id: PositiveId
    name: Name
    description: Description | None = None
    # Creation is always active; only the dedicated status action may change it.
    template_id: PositiveId | None = None
    template_token: Annotated[str, Field(min_length=64, max_length=64)] | None = None



class DeviceMove(InputSchema):
    node_id: PositiveId


class PortMove(InputSchema):
    distribution_device_id: PositiveId


class DistributionStatus(InputSchema):
    active: StrictBool


class DeviceResponse(ResponseSchema):
    node_id: int
    name: str
    description: str | None
    port_count: int
    unassigned_port_count: int
    circuit_count: int


class PortResponse(ResponseSchema):
    nomenclature_id: int | None
    numbering_format: str | None
    number_components: list[int] | None
    distribution_device_id: int
    name: str
    description: str | None
    circuit_count: int


class DistributionCircuitResponse(BaseModel):
    id: int
    circuit_code: str
    description: str
    active: bool
    customer_id: int
    customer_code: str
    customer_name: str
    service_type_id: int | None
    service_type_name: str | None
    distribution_port_id: int | None
    distribution_port_name: str | None
