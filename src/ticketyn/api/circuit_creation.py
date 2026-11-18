"""Shared circuit insertion; callers own the distribution transaction."""
from ticketyn.api.crud import get_or_404
from ticketyn.api.fms_data import validate_active, validate_initial_capacity
from ticketyn.api.circuit_sector import validate_sector, validate_node
from ticketyn.api.distribution_data import record, validate_circuit_distribution
from ticketyn.models import Circuit, Customer, ServiceType, CpeModel


def build_circuit(session, payload, actor):
    from ticketyn.security.mutations import contextual_creation
    contextual_creation(actor, 'circuits', payload.model_dump())
    validate_sector(session, payload.sector_id)
    validate_initial_capacity(payload.model_dump())
    get_or_404(session, Customer, payload.customer_id)
    validate_node(session, payload.node_id)
    if payload.service_type_id is not None:
        validate_active(session, ServiceType, payload.service_type_id)
    if payload.cpe_model_id is not None:
        validate_active(session, CpeModel, payload.cpe_model_id)
    validate_circuit_distribution(session, payload.model_dump())
    item = Circuit(**payload.model_dump())
    session.add(item); session.flush(); session.refresh(item)
    if item.distribution_device_id is not None:
        record(session, actor.id, item, 'ASSIGN')
    return item
