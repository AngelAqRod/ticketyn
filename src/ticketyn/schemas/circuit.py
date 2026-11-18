from typing import ClassVar, Literal
from decimal import Decimal
from ipaddress import ip_address
from decimal import ROUND_HALF_UP
from pydantic import Field, BaseModel, ConfigDict, IPvAnyAddress, field_validator, model_validator
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


Coordinate = Annotated[Decimal, Field(allow_inf_nan=False)]
LOCATION_FIELDS = {'address', 'latitude', 'longitude', 'additional_notes'}


def gps_error(latitude, longitude):
    """Single rule shared by create, update (against the stored row) and the database checks."""
    if latitude is not None and not -90 <= latitude <= 90:
        return 'La latitud debe estar entre -90 y 90.'
    if longitude is not None and not -180 <= longitude <= 180:
        return 'La longitud debe estar entre -180 y 180.'
    if (latitude is None) != (longitude is None):
        return 'El Punto GPS debe incluir latitud y longitud.'


class CircuitSiteInput(CircuitAddressInput):
    """Optional site data. Null clears a field; omitting it leaves the stored value untouched."""
    address: Annotated[str, Field(max_length=500)] | None = None
    latitude: Coordinate | None = None
    longitude: Coordinate | None = None
    additional_notes: Annotated[str, Field(max_length=5000)] | None = None

    @field_validator('address', 'additional_notes')
    @classmethod
    def trim_text(cls, value):
        return value.strip() if value is not None else None

    @field_validator('latitude', 'longitude')
    @classmethod
    def six_decimals(cls, value):
        # Google Maps copies seven or more decimals; 1e-6 degrees is about 0.1 m.
        return value.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP) if value is not None else None

    pair_required: ClassVar[bool] = False  # create always checks the pair; update checks it against the stored row in the API

    @model_validator(mode='after')
    def valid_gps(self):
        both_sent = {'latitude', 'longitude'} <= self.model_fields_set
        error = gps_error(self.latitude, self.longitude)
        if error and ('entre' in error or self.pair_required or both_sent):
            raise ValueError(error)
        return self


class CircuitCreate(CircuitSiteInput):
    pair_required: ClassVar[bool] = True
    distribution_device_id: PositiveId | None = None
    distribution_port_id: PositiveId | None = None
    cpe_model_id: PositiveId | None = None
    sector_id: PositiveId
    nullable_fields: ClassVar[set[str]] = {"cpe_management_ip", "initial_capacity", "initial_capacity_unit", "service_type_id", "cpe_model_id", "distribution_device_id", "distribution_port_id", *LOCATION_FIELDS}
    initial_capacity: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6, allow_inf_nan=False)] | None = None
    initial_capacity_unit: Literal['Mbps', 'Gbps'] | None = None
    service_type_id: PositiveId | None = None
    node_id: PositiveId
    customer_id: PositiveId
    circuit_code: NonEmptyString
    description: NonEmptyString
    active: bool = True


class CircuitUpdate(CircuitSiteInput):
    distribution_device_id: PositiveId | None = None
    distribution_port_id: PositiveId | None = None
    cpe_model_id: PositiveId | None = None
    sector_id: PositiveId | None = None
    nullable_fields: ClassVar[set[str]] = {"cpe_management_ip", "initial_capacity", "initial_capacity_unit", "service_type_id", "cpe_model_id", "distribution_device_id", "distribution_port_id", *LOCATION_FIELDS}
    initial_capacity: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6, allow_inf_nan=False)] | None = None
    initial_capacity_unit: Literal['Mbps', 'Gbps'] | None = None
    service_type_id: PositiveId | None = None
    node_id: PositiveId | None = None
    customer_id: PositiveId | None = None
    circuit_code: NonEmptyString | None = None
    description: NonEmptyString | None = None
    active: bool | None = None


class CircuitResponse(ResponseSchema):
    address: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    additional_notes: str | None
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
