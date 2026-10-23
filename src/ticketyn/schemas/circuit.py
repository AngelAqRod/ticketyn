from typing import ClassVar, Literal
from decimal import Decimal
from ipaddress import ip_address
from pydantic import Field, BaseModel, ConfigDict, IPvAnyAddress, field_validator
from typing import Annotated

from ticketyn.schemas.common import AssignmentSummary, InputSchema, NonEmptyString, PositiveId, ResponseSchema


class CircuitAddressInput(InputSchema):
    cpe_management_ip: str | None = None

    @field_validator('cpe_management_ip', mode='before')
    @classmethod
    def normalize_management_ip(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if not isinstance(value, str) or '/' in value or '%' in value:
            raise ValueError('Introduce una dirección IPv4 o IPv6 individual, sin CIDR ni nombres DNS')
        try:
            return str(ip_address(value.strip()))
        except ValueError:
            raise ValueError('Introduce una dirección IPv4 o IPv6 válida') from None


class CircuitCreate(CircuitAddressInput):
    distribution_device_id: PositiveId | None = None
    distribution_port_id: PositiveId | None = None
    cpe_model_id: PositiveId | None = None
    sector_id: PositiveId
    nullable_fields: ClassVar[set[str]] = {"cpe_management_ip", "initial_capacity", "initial_capacity_unit", "service_type_id", "cpe_model_id", "distribution_device_id", "distribution_port_id"}
    initial_capacity: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6, allow_inf_nan=False)] | None = None
    initial_capacity_unit: Literal['Mbps', 'Gbps'] | None = None
    service_type_id: PositiveId | None = None
    node_id: PositiveId
    customer_id: PositiveId
    circuit_code: NonEmptyString
    description: NonEmptyString
    active: bool = True


class CircuitUpdate(CircuitAddressInput):
    distribution_device_id: PositiveId | None = None
    distribution_port_id: PositiveId | None = None
    cpe_model_id: PositiveId | None = None
    sector_id: PositiveId | None = None
    nullable_fields: ClassVar[set[str]] = {"cpe_management_ip", "initial_capacity", "initial_capacity_unit", "service_type_id", "cpe_model_id", "distribution_device_id", "distribution_port_id"}
    initial_capacity: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6, allow_inf_nan=False)] | None = None
    initial_capacity_unit: Literal['Mbps', 'Gbps'] | None = None
    service_type_id: PositiveId | None = None
    node_id: PositiveId | None = None
    customer_id: PositiveId | None = None
    circuit_code: NonEmptyString | None = None
    description: NonEmptyString | None = None
    active: bool | None = None


class CircuitResponse(ResponseSchema):
    cpe_management_ip: IPvAnyAddress | None
    distribution_device_id: int | None
    distribution_port_id: int | None
    distribution_device: AssignmentSummary | None
    distribution_port: AssignmentSummary | None
    cpe_model_id: int | None
    cpe_model: AssignmentSummary | None
    sector_id: int | None
    sector: AssignmentSummary | None
    service_type_id: int | None
    service_type: AssignmentSummary | None
    initial_capacity: Decimal | None
    initial_capacity_unit: str | None
    node_id: int | None
    node: AssignmentSummary | None
    customer_id: int
    circuit_code: str
    description: str


class CpeConfigurationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    configuration: str | None = Field(max_length=500000, repr=False)


class CpeConfigurationResponse(BaseModel):
    configuration: str | None
