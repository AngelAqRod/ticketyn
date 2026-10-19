"""Allowlisted, declarative fields. No rendering or message generation here."""
from dataclasses import dataclass

ACTIVATION_EVENT = 'fms.activation.created'
EVENTS = {ACTIVATION_EVENT: 'Registro de activación FMS'}


@dataclass(frozen=True)
class DynamicField:
    id: str
    group: str
    label: str
    format: str
    temporality: str
    source_paths: tuple[str, ...]
    resolver: str = 'attribute'


def field(id, group, label, format, temporality, *paths, resolver='attribute'):
    return DynamicField(id, group, label, format, temporality, paths, resolver)


ACTIVATION_FIELDS = (
    field('activation.reference', 'Activación FMS', 'Correlativo', 'text', 'HISTORICAL', 'Activation.reference'),
    field('activation.effective_at', 'Activación FMS', 'Fecha efectiva de activación', 'datetime_guatemala', 'HISTORICAL', 'Activation.effective_at'),
    field('activation.created_at', 'Activación FMS', 'Fecha de creación', 'datetime_guatemala', 'HISTORICAL', 'Activation.created_at'),
    field('activation.activation_notes', 'Activación FMS', 'Notas de activación', 'multiline', 'HISTORICAL', 'Activation.activation_notes'),
    field('activation.sector', 'Activación FMS', 'Sector', 'text', 'HISTORICAL_REFERENCE_CURRENT_NAME', 'Activation.sector.name'),
    field('activation.node', 'Activación FMS', 'Nodo', 'text', 'HISTORICAL_REFERENCE_CURRENT_NAME', 'Activation.node.name'),
    field('activation.responsible', 'Activación FMS', 'Responsable', 'text', 'HISTORICAL_REFERENCE_CURRENT_NAME', 'Activation.responsible.name'),
    field('activation.service_type', 'Activación FMS', 'Tipo de servicio', 'text', 'HISTORICAL', 'Activation.service_type_name'),
    field('activation.cpe', 'Activación FMS', 'CPE de activación', 'text', 'HISTORICAL', 'Activation.cpe_activation'),
    field('activation.initial_capacity', 'Activación FMS', 'Capacidad inicial', 'capacity', 'HISTORICAL', 'Activation.initial_capacity', 'Activation.initial_capacity_unit', resolver='capacity'),
    field('circuit.code', 'Circuito', 'Código de circuito', 'text', 'CURRENT', 'Activation.circuit.circuit_code'),
    field('circuit.description', 'Circuito', 'Descripción del circuito', 'multiline', 'CURRENT', 'Activation.circuit.description'),
    field('circuit.sector', 'Circuito', 'Sector', 'text', 'CURRENT', 'Activation.circuit.sector.name'),
    field('circuit.node', 'Circuito', 'Nodo', 'text', 'CURRENT', 'Activation.circuit.node.name'),
    field('circuit.service_type', 'Circuito', 'Tipo de servicio', 'text', 'CURRENT', 'Activation.circuit.service_type.name'),
    field('circuit.cpe_model', 'Circuito', 'Modelo de CPE actual', 'text', 'CURRENT', 'Activation.circuit.cpe_model.name'),
    field('circuit.initial_capacity', 'Circuito', 'Capacidad inicial', 'capacity', 'CURRENT', 'Activation.circuit.initial_capacity', 'Activation.circuit.initial_capacity_unit', resolver='capacity'),
    field('circuit.current_capacity', 'Circuito', 'Capacidad actual', 'capacity', 'CURRENT', 'Activation.circuit_id', 'CapacityChange.effective_at', 'CapacityChange.id', 'CapacityChange.new_capacity', 'CapacityChange.new_unit', 'Activation.circuit.initial_capacity', 'Activation.circuit.initial_capacity_unit', resolver='latest_capacity_effective_now_or_initial'),
    field('customer.name', 'Cliente', 'Cliente', 'text', 'CURRENT', 'Activation.circuit.customer.name'),
    field('customer.code', 'Cliente', 'Código de cliente', 'text', 'CURRENT', 'Activation.circuit.customer.customer_code'),
)
FIELD_REGISTRY = {ACTIVATION_EVENT: ACTIVATION_FIELDS}
