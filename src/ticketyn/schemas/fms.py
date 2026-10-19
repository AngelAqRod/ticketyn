from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from ticketyn.schemas.common import AssignmentSummary, InputSchema, PositiveId
from ticketyn.schemas.circuit import CircuitResponse

Capacity = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6, allow_inf_nan=False)]
Unit = Literal['Mbps', 'Gbps']


class OperationCreate(InputSchema):
    node_id: PositiveId | None = None
    sector_id: PositiveId | None = None
    circuit_id: PositiveId
    responsible_id: PositiveId
    effective_at: AwareDatetime


class ActivationCreate(OperationCreate):
    nullable_fields = {'customer_id', 'activation_notes'}
    customer_id: PositiveId | None = None
    activation_notes: Annotated[str, Field(max_length=10000)] | None = None

    @model_validator(mode='before')
    @classmethod
    def normalize_notes(cls, values):
        if isinstance(values, dict):
            notes = values.get('activation_notes')
            # Normalize only this field before InputSchema rejects blank strings.
            # Oversized input must still fail validation, including whitespace.
            if isinstance(notes, str) and len(notes) <= 10000 and not notes.strip():
                return {**values, 'activation_notes': None}
        return values


class CapacityChangeCreate(OperationCreate):
    nullable_fields = {'previous_capacity', 'previous_unit', 'description'}
    operation_type: Literal['INCREASE', 'DECREASE']
    previous_capacity: Capacity | None = None
    previous_unit: Unit | None = None
    new_capacity: Capacity
    new_unit: Unit
    description: Annotated[str, Field(max_length=10000)] | None = None

    @model_validator(mode='after')
    def validate_direction(self):
        if (self.previous_capacity is None) != (self.previous_unit is None):
            raise ValueError('La capacidad anterior y su unidad deben indicarse juntas')
        if self.previous_capacity is None:
            if self.operation_type == 'DECREASE':
                raise ValueError('Un decremento requiere capacidad anterior conocida')
        else:
            old = self.previous_capacity * (1000 if self.previous_unit == 'Gbps' else 1)
            new = self.new_capacity * (1000 if self.new_unit == 'Gbps' else 1)
            if (self.operation_type == 'INCREASE' and new <= old) or (self.operation_type == 'DECREASE' and new >= old):
                raise ValueError('La nueva capacidad no corresponde al tipo de operación seleccionado')
        return self


class LifecycleCreate(OperationCreate):
    nullable_fields = {'reason_id', 'observations'}
    operation_type: Literal['DEACTIVATE', 'REACTIVATE']
    reason_id: PositiveId | None = None
    observations: Annotated[str, Field(max_length=10000)] | None = None

    @model_validator(mode='after')
    def valid_reason(self):
        if (self.operation_type == 'DEACTIVATE') != (self.reason_id is not None):
            raise ValueError('Solo una baja debe tener un motivo de baja')
        return self


class InterventionCreate(InputSchema):
    responsible_id: PositiveId
    occurred_at: AwareDatetime
    content: Annotated[str, Field(min_length=1, max_length=10000)]


class OperationResponse(BaseModel):
    node_id: int | None
    node: AssignmentSummary | None
    sector_id: int | None
    sector: AssignmentSummary | None
    model_config = ConfigDict(from_attributes=True)
    id: int
    circuit_id: int
    responsible_id: int
    effective_at: datetime
    created_at: datetime
    circuit: CircuitResponse
    responsible: AssignmentSummary


class ActivationResponse(OperationResponse):
    activation_notes: str | None
    cpe_activation: str | None
    service_type_name: str | None
    initial_capacity: Decimal | None
    initial_capacity_unit: str | None
    activation_number: int
    reference: str


class CapacityChangeResponse(OperationResponse):
    operation_type: str
    previous_capacity: Decimal | None
    previous_unit: str | None
    new_capacity: Decimal
    new_unit: str
    description: str | None


class LifecycleResponse(OperationResponse):
    operation_type: str
    reason_id: int | None
    reason: AssignmentSummary | None
    observations: str | None


class InterventionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    activation_id: int
    responsible_id: int
    responsible: AssignmentSummary
    occurred_at: datetime
    created_at: datetime
    content: str


class CircuitOperationalDetail(BaseModel):
    circuit: CircuitResponse
    customer: AssignmentSummary
    current_capacity: Decimal | None
    current_capacity_unit: str | None
    initial_activation: ActivationResponse | None
