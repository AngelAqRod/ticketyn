"""Distribution catalog, structural actions and compact service projections."""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response
from sqlalchemy import func, select

from ticketyn.api.crud import DBSession, filtered_items, get_or_404
from ticketyn.api.distribution_data import (
    active_device, active_node, distribution_write, ensure_unassigned, locked, port_name_order, record, snapshot,
)
from ticketyn.models import Circuit, Customer, DistributionDevice, DistributionPort, ServiceType
from ticketyn.schemas.port_nomenclature import PortGeneration, PortEdit
from ticketyn.schemas.distribution import (
    DeviceCreate, DeviceMove, DeviceResponse, DistributionCircuitResponse, DistributionEdit, DistributionStatus,
    PortMove, PortResponse,
)

router = APIRouter(prefix='/api', tags=['distribution'])
Id = Annotated[int, Path(gt=0)]
FilterId = Annotated[int | None, Query(gt=0)]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]


def device_query():
    assigned = select(Circuit.id).where(Circuit.distribution_port_id == DistributionPort.id).exists()
    ports = select(
        DistributionPort.distribution_device_id.label('id'),
        func.count().label('count'),
        func.count().filter(~assigned).label('unassigned_count'),
    ).group_by(DistributionPort.distribution_device_id).subquery()
    circuits = select(Circuit.distribution_device_id.label('id'), func.count().label('count')).group_by(Circuit.distribution_device_id).subquery()
    return select(DistributionDevice, func.coalesce(ports.c.count, 0), func.coalesce(circuits.c.count, 0), func.coalesce(ports.c.unassigned_count, 0)).outerjoin(
        ports, ports.c.id == DistributionDevice.id).outerjoin(circuits, circuits.c.id == DistributionDevice.id)


def port_query():
    circuits = select(Circuit.distribution_port_id.label('id'), func.count().label('count')).group_by(Circuit.distribution_port_id).subquery()
    return select(DistributionPort, func.coalesce(circuits.c.count, 0)).outerjoin(circuits, circuits.c.id == DistributionPort.id)


def device_response(row):
    item, ports, circuits, unassigned = row
    return DeviceResponse(**{column: getattr(item, column) for column in ('id', 'node_id', 'name', 'description', 'active', 'created_at')}, port_count=ports, circuit_count=circuits, unassigned_port_count=unassigned)


def port_response(row):
    item, circuits = row
    return PortResponse(**{column: getattr(item, column) for column in ('id', 'distribution_device_id', 'name', 'description', 'active', 'created_at', 'nomenclature_id', 'numbering_format', 'number_components')}, circuit_count=circuits)


def device_view(session, id):
    row = session.execute(device_query().where(DistributionDevice.id == id)).one_or_none()
    if row is None:
        raise HTTPException(404, 'No se encontró el equipo de distribución.')
    return device_response(row)


def port_view(session, id):
    row = session.execute(port_query().where(DistributionPort.id == id)).one_or_none()
    if row is None:
        raise HTTPException(404, 'No se encontró el puerto de distribución.')
    return port_response(row)


@router.get('/distribution-devices', response_model=list[DeviceResponse])
def list_devices(session: DBSession, node_id: FilterId = None, search: str | None = None,
                 include_inactive: bool = False, active: bool | None = None, limit: Limit = 50, offset: Offset = 0):
    ids = filtered_items(DistributionDevice, search=search, search_fields=('name', 'description'),
                         order_field='name', include_inactive=include_inactive, active=active, node_id=node_id).with_only_columns(DistributionDevice.id)
    query = device_query().where(DistributionDevice.id.in_(ids)).order_by(DistributionDevice.name, DistributionDevice.id)
    return [device_response(row) for row in session.execute(query.limit(limit).offset(offset))]


@router.get('/distribution-devices/{id}', response_model=DeviceResponse)
def get_device(id: Id, session: DBSession):
    return device_view(session, id)


@router.post('/distribution-devices', response_model=DeviceResponse, status_code=201)
def create_device(payload: DeviceCreate, session: DBSession, request: Request):
    with distribution_write(session):
        active_node(session, payload.node_id)
        item = DistributionDevice(**payload.model_dump(), active=True)
        session.add(item); session.flush()
        record(session, request.state.principal.id, item, 'CREATE')
        result = device_view(session, item.id)
    return result


@router.get('/distribution-ports', response_model=list[PortResponse])
def list_ports(session: DBSession, distribution_device_id: FilterId = None, search: str | None = None,
               include_inactive: bool = False, active: bool | None = None, limit: Limit = 50, offset: Offset = 0):
    ids = filtered_items(DistributionPort, search=search, search_fields=('name', 'description'),
                         order_field='name', include_inactive=include_inactive, active=active).order_by(None)
    if distribution_device_id is not None:
        ids = ids.where(DistributionPort.distribution_device_id == distribution_device_id)
    query = port_query().where(DistributionPort.id.in_(ids.with_only_columns(DistributionPort.id))).order_by(
        port_name_order(DistributionPort.name), DistributionPort.name.collate('C'), DistributionPort.id)
    return [port_response(row) for row in session.execute(query.limit(limit).offset(offset))]


@router.get('/distribution-ports/{id}', response_model=PortResponse)
def get_port(id: Id, session: DBSession):
    return port_view(session, id)


@router.post('/distribution-ports', response_model=PortResponse, status_code=201)
def create_port(payload: PortGeneration, session: DBSession, request: Request):
    if payload.end is not None and payload.end != payload.start:
        raise HTTPException(422, 'Para crear un rango utiliza la creación masiva')
    from ticketyn.api.port_nomenclatures import create_ports
    result = create_ports(payload, session, request)
    if not result['created']:
        raise HTTPException(409, 'El puerto ya existe')
    return result['created'][0]


def edit_resource(session, request, model, id, payload, view):
    with distribution_write(session):
        item = locked(session, model, id); before = snapshot(item)
        values = payload.model_dump(exclude_unset=True)
        if model is DistributionPort:
            from ticketyn.api.port_nomenclatures import validate_port_edit
            validate_port_edit(session, item, values)
        for key, value in values.items():
            setattr(item, key, value)
        session.flush()
        record(session, request.state.principal.id, item, 'EDIT', before)
        result = view(session, id)
    return result


@router.patch('/distribution-devices/{id}', response_model=DeviceResponse)
def edit_device(id: Id, payload: DistributionEdit, session: DBSession, request: Request):
    return edit_resource(session, request, DistributionDevice, id, payload, device_view)


@router.patch('/distribution-ports/{id}', response_model=PortResponse)
def edit_port(id: Id, payload: PortEdit, session: DBSession, request: Request):
    return edit_resource(session, request, DistributionPort, id, payload, port_view)


@router.post('/distribution-devices/{id}/move', response_model=DeviceResponse)
def move_device(id: Id, payload: DeviceMove, session: DBSession, request: Request):
    with distribution_write(session):
        item = locked(session, DistributionDevice, id); before = snapshot(item)
        if item.node_id != payload.node_id:
            ensure_unassigned(session, item)
            active_node(session, payload.node_id)
            item.node_id = payload.node_id
        session.flush(); record(session, request.state.principal.id, item, 'MOVE', before)
        result = device_view(session, id)
    return result


@router.post('/distribution-ports/{id}/move', response_model=PortResponse)
def move_port(id: Id, payload: PortMove, session: DBSession, request: Request):
    with distribution_write(session):
        item = locked(session, DistributionPort, id); before = snapshot(item)
        if item.distribution_device_id != payload.distribution_device_id:
            ensure_unassigned(session, item)
            active_device(session, payload.distribution_device_id)
            item.distribution_device_id = payload.distribution_device_id
        session.flush(); record(session, request.state.principal.id, item, 'MOVE', before)
        result = port_view(session, id)
    return result


def change_status(session, request, model, id, payload, view):
    with distribution_write(session):
        item = locked(session, model, id); before = snapshot(item)
        if item.active != payload.active:
            # Ports with associations cannot be deactivated. Device state never
            # cascades into ports/circuits; existing links remain readable.
            if model is DistributionPort and not payload.active:
                ensure_unassigned(session, item)
            if payload.active:
                active_node(session, item.node_id) if model is DistributionDevice else active_device(session, item.distribution_device_id)
            item.active = payload.active
        session.flush(); record(session, request.state.principal.id, item, 'SET_ACTIVE', before)
        result = view(session, id)
    return result


@router.patch('/distribution-devices/{id}/status', response_model=DeviceResponse)
def device_status(id: Id, payload: DistributionStatus, session: DBSession, request: Request):
    return change_status(session, request, DistributionDevice, id, payload, device_view)


@router.patch('/distribution-ports/{id}/status', response_model=PortResponse)
def port_status(id: Id, payload: DistributionStatus, session: DBSession, request: Request):
    return change_status(session, request, DistributionPort, id, payload, port_view)


def delete_resource(session, request, model, id):
    with distribution_write(session):
        item = locked(session, model, id)
        ensure_unassigned(session, item)
        if model is DistributionDevice and session.scalar(select(DistributionPort.id).where(DistributionPort.distribution_device_id == id).limit(1)) is not None:
            raise HTTPException(409, 'El equipo conserva puertos registrados. No se eliminan automáticamente.')
        record(session, request.state.principal.id, item, 'DELETE', snapshot(item), deleted=True)
        session.delete(item); session.flush()
    return Response(status_code=204)


@router.delete('/distribution-devices/{id}', status_code=204, response_class=Response)
def delete_device(id: Id, session: DBSession, request: Request):
    return delete_resource(session, request, DistributionDevice, id)


@router.delete('/distribution-ports/{id}', status_code=204, response_class=Response)
def delete_port(id: Id, session: DBSession, request: Request):
    return delete_resource(session, request, DistributionPort, id)


@router.get('/distribution-devices/{id}/circuits', response_model=list[DistributionCircuitResponse])
def device_circuits(id: Id, session: DBSession, port_id: FilterId = None, without_port: bool = False,
                    limit: Limit = 50, offset: Offset = 0):
    get_or_404(session, DistributionDevice, id)
    if port_id is not None:
        if without_port:
            raise HTTPException(422, 'No combines puerto y circuitos sin puerto.')
        port = get_or_404(session, DistributionPort, port_id)
        if port.distribution_device_id != id:
            raise HTTPException(422, 'El puerto no pertenece al equipo consultado.')
    # Explicit columns: never load CPE configuration, credentials or FMS snapshots.
    query = select(Circuit.id, Circuit.circuit_code, Circuit.description, Circuit.active,
                   Customer.id.label('customer_id'), Customer.customer_code, Customer.name.label('customer_name'),
                   ServiceType.id.label('service_type_id'), ServiceType.name.label('service_type_name'),
                   Circuit.distribution_port_id, DistributionPort.name.label('distribution_port_name')).join(
        Customer, Circuit.customer_id == Customer.id).outerjoin(ServiceType, Circuit.service_type_id == ServiceType.id).outerjoin(
        DistributionPort, Circuit.distribution_port_id == DistributionPort.id).where(Circuit.distribution_device_id == id)
    if port_id is not None:
        query = query.where(Circuit.distribution_port_id == port_id)
    if without_port:
        query = query.where(Circuit.distribution_port_id.is_(None))
    return [dict(row) for row in session.execute(query.order_by(Circuit.circuit_code, Circuit.id).limit(limit).offset(offset)).mappings()]
