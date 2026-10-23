from typing import Annotated

from fastapi import Request, APIRouter, HTTPException, Path, Query, Response

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ticketyn.api.crud import DBSession, delete_unreferenced, get_or_404, list_items, update_item
from ticketyn.models import Circuit, Customer, Ticket, ServiceType, CpeModel
from ticketyn.api.fms_data import validate_active, validate_initial_capacity
from ticketyn.models.fms import Activation, CapacityChange, CircuitLifecycleOperation
from ticketyn.schemas.circuit import CircuitCreate, CircuitResponse, CircuitUpdate, CpeConfigurationInput, CpeConfigurationResponse

from ticketyn.api.circuit_sector import locked_circuit, validate_sector, validate_node
from ticketyn.api.circuit_ticket_sectors import synchronize_recent_ticket_sectors
from ticketyn.api.distribution_data import distribution_write, record, snapshot, validate_circuit_distribution

router = APIRouter(prefix="/api/circuits", tags=["circuits"])


@router.post("", response_model=CircuitResponse, status_code=201)
def create_circuit(payload: CircuitCreate, session: DBSession, request: Request):
    with distribution_write(session):
        from ticketyn.security.mutations import contextual_creation
        contextual_creation(request.state.principal, 'circuits', payload.model_dump())
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
            record(session, request.state.principal.id, item, 'ASSIGN')
        result = CircuitResponse.model_validate(item)
    return result


@router.get("", response_model=list[CircuitResponse])
def list_circuits(
    session: DBSession,
    search: str | None = None,
    include_inactive: bool = False,
    active: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    node_id: Annotated[int | None, Query(gt=0)] = None,
    customer_id: Annotated[int | None, Query(gt=0)] = None,
    sector_id: Annotated[int | None, Query(gt=0)] = None,
):
    return list_items(
        session, Circuit, search=search, search_fields=('circuit_code', 'description'),
        order_field="circuit_code", include_inactive=include_inactive,
        limit=limit, offset=offset, customer_id=customer_id, active=active, node_id=node_id,
        sector_id=sector_id,
    )


@router.get("/{id}", response_model=CircuitResponse)
def get_circuit(id: Annotated[int, Path(gt=0)], session: DBSession):
    return get_or_404(session, Circuit, id)


@router.patch("/{id}", response_model=CircuitResponse)
def patch_circuit(id: Annotated[int, Path(gt=0)], payload: CircuitUpdate, session: DBSession, request: Request):
    with distribution_write(session):
        item = locked_circuit(session, id)
        before = snapshot(item)
        values = payload.model_dump(exclude_unset=True)
        from ticketyn.security.mutations import circuit_mutation
        circuit_mutation(request.state.principal, item, values)
        sector_id = values.get('sector_id', item.sector_id)
        if sector_id is None:
            raise HTTPException(422, 'Selecciona un Sector para el circuito antes de guardar.')
        sector_changed = sector_id != item.sector_id
        new_sector = validate_sector(session, sector_id) if sector_changed else None
        validate_initial_capacity({'initial_capacity': values.get('initial_capacity', item.initial_capacity), 'initial_capacity_unit': values.get('initial_capacity_unit', item.initial_capacity_unit)})
        if "customer_id" in values:
            get_or_404(session, Customer, values["customer_id"])
        node_id = values.get("node_id", item.node_id)
        if node_id is None:
            raise HTTPException(422, "Selecciona un Nodo para el circuito antes de guardar.")
        if node_id != item.node_id:
            validate_node(session, node_id)
        if values.get('service_type_id') is not None and values['service_type_id'] != item.service_type_id:
            validate_active(session, ServiceType, values['service_type_id'])
        if values.get('cpe_model_id') is not None and values['cpe_model_id'] != item.cpe_model_id:
            validate_active(session, CpeModel, values['cpe_model_id'])
        validate_circuit_distribution(session, values, item)
        if sector_changed:
            synchronize_recent_ticket_sectors(session, item.id, new_sector)
        for key, value in values.items():
            setattr(item, key, value)
        session.flush(); session.refresh(item)
        if before != snapshot(item) and (before['distribution_device_id'] is not None or item.distribution_device_id is not None):
            record(session, request.state.principal.id, item, 'ASSIGN', before)
        result = CircuitResponse.model_validate(item)
    return result


@router.delete("/{id}", status_code=204, response_class=Response)
def delete_circuit(id: Annotated[int, Path(gt=0)], session: DBSession):
    delete_unreferenced(session, Circuit, id, dependent_columns=(Ticket.circuit_id, Activation.circuit_id, CapacityChange.circuit_id, CircuitLifecycleOperation.circuit_id),
        conflict_detail="No se puede eliminar el circuito porque tiene tickets o historial operativo asociados. Puedes desactivarlo en lugar de eliminarlo.")
    return Response(status_code=204)


@router.get('/{id}/cpe-configuration', response_model=CpeConfigurationResponse)
def get_configuration(id: Annotated[int, Path(gt=0)], session: DBSession, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return {'configuration': get_or_404(session, Circuit, id).cpe_configuration}


@router.patch('/{id}/cpe-configuration', response_model=CpeConfigurationResponse)
def patch_configuration(id: Annotated[int, Path(gt=0)], payload: CpeConfigurationInput, session: DBSession, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    try:
        item = locked_circuit(session, id)
        # A dedicated response never serializes configuration through general Circuit DTOs.
        item = update_item(session, item, {'cpe_configuration': payload.configuration})
        return {'configuration': item.cpe_configuration}
    except SQLAlchemyError:
        try:
            session.rollback()
        except SQLAlchemyError:
            pass
        # DB exceptions may embed SQL parameters: never propagate configuration.
        raise HTTPException(503, 'No se pudo guardar la configuración del CPE. Reintenta la operación.') from None
