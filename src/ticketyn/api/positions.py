from collections import defaultdict
from typing import Annotated
from fastapi import APIRouter, Path, Query, HTTPException
from sqlalchemy import select, delete
from ticketyn.api.crud import DBSession, get_or_404, list_items, save_item, update_item
from ticketyn.models import Position, Department, PositionEscalationDestination
from ticketyn.schemas.position import PositionCreate, PositionUpdate, PositionResponse

router = APIRouter(prefix='/api/positions', tags=['positions'])


def validate_department(session, id):
    item = session.scalar(select(Department).where(Department.id == id).with_for_update(read=True))
    if item is None:
        raise HTTPException(404, 'Departamento no encontrado')
    if not item.active:
        raise HTTPException(422, 'El departamento está inactivo')


def validate_and_apply_destinations(session, item: Position, escalation_mode: str, general_time: int | None, destinations_data: list | None):
    if destinations_data is None:
        # Check if mode or general time changed with existing destinations
        existing = item.escalation_destinations
        if existing:
            if escalation_mode == 'GENERAL' and (general_time is None or general_time <= 0):
                raise HTTPException(422, 'El tiempo general de escalamiento es obligatorio y debe ser mayor a 0 minutos')
            if escalation_mode == 'INDIVIDUAL':
                for d in existing:
                    if d.time_minutes is None or d.time_minutes <= 0:
                        raise HTTPException(422, 'Cada destino debe tener un tiempo configurado en modalidad individual')
        return

    # Check for duplicate targets
    target_ids = [d.get('target_position_id') if isinstance(d, dict) else d.target_position_id for d in destinations_data]
    if len(target_ids) != len(set(target_ids)):
        raise HTTPException(422, 'Destinos de escalamiento duplicados en la configuración')

    # Check self-escalation
    if item.id and item.id in target_ids:
        raise HTTPException(422, 'Un puesto no puede escalarse a sí mismo')

    # Existing targets for this position (to allow preserved historical inactive ones)
    existing_target_ids = {d.target_position_id for d in item.escalation_destinations} if item.id else set()

    for d in destinations_data:
        target_id = d.get('target_position_id') if isinstance(d, dict) else d.target_position_id
        time_minutes = d.get('time_minutes') if isinstance(d, dict) else getattr(d, 'time_minutes', None)

        target_pos = session.get(Position, target_id)
        if target_pos is None:
            raise HTTPException(404, f'Puesto destino con ID {target_id} no encontrado')

        if not target_pos.active and target_id not in existing_target_ids:
            raise HTTPException(422, f"No se puede configurar el puesto destino inactivo '{target_pos.name}'")

        if escalation_mode == 'INDIVIDUAL' and (time_minutes is None or time_minutes <= 0):
            raise HTTPException(422, f"El tiempo para el puesto destino '{target_pos.name}' es obligatorio en modalidad individual")

    if escalation_mode == 'GENERAL' and target_ids and (general_time is None or general_time <= 0):
        raise HTTPException(422, 'El tiempo general de escalamiento es obligatorio y debe ser mayor a 0 minutos')

    # Cycle detection across position_escalation_destinations
    if item.id and target_ids:
        existing_edges = session.execute(
            select(PositionEscalationDestination.position_id, PositionEscalationDestination.target_position_id)
        ).all()
        graph = defaultdict(set)
        for p, t in existing_edges:
            if p != item.id:
                graph[p].add(t)
        for t in target_ids:
            graph[item.id].add(t)

        # Check if item.id can be reached from any of target_ids
        for start_node in target_ids:
            visited = set()
            queue = [start_node]
            while queue:
                curr = queue.pop(0)
                if curr == item.id:
                    raise HTTPException(422, 'Configuración circular no permitida: el puesto destino tiene una ruta de retorno hacia este puesto')
                if curr not in visited:
                    visited.add(curr)
                    queue.extend(graph.get(curr, ()))

    # Apply destinations using ORM collection with cascade delete-orphan
    item.escalation_destinations.clear()
    session.flush()
    for idx, d in enumerate(destinations_data):
        target_id = d.get('target_position_id') if isinstance(d, dict) else d.target_position_id
        time_minutes = d.get('time_minutes') if isinstance(d, dict) else getattr(d, 'time_minutes', None)
        new_dest = PositionEscalationDestination(
            position_id=item.id,
            target_position_id=target_id,
            time_minutes=time_minutes if escalation_mode == 'INDIVIDUAL' else None,
            order_index=idx,
        )
        item.escalation_destinations.append(new_dest)


@router.post('', response_model=PositionResponse, status_code=201)
def create_position(payload: PositionCreate, session: DBSession):
    validate_department(session, payload.department_id)
    values = payload.model_dump(exclude={'destinations'})
    destinations_data = payload.destinations

    escalation_mode = values.get('escalation_mode', 'GENERAL')
    general_time = values.get('general_escalation_time_minutes')

    # Initial self check
    if destinations_data:
        target_ids = [d.target_position_id for d in destinations_data]
        if len(target_ids) != len(set(target_ids)):
            raise HTTPException(422, 'Destinos de escalamiento duplicados en la configuración')

    item = Position(**values)
    session.add(item)
    session.flush()

    if destinations_data is not None:
        validate_and_apply_destinations(session, item, escalation_mode, general_time, destinations_data)

    item = save_item(session, item)
    session.refresh(item)
    return item


@router.get('', response_model=list[PositionResponse])
def positions(session: DBSession, search: str | None = None, include_inactive: bool = False,
              department_id: Annotated[int | None, Query(gt=0)] = None,
              limit: Annotated[int, Query(ge=1, le=200)] = 50, offset: Annotated[int, Query(ge=0)] = 0):
    return list_items(session, Position, search=search, search_fields=('name',), order_field='name',
                      include_inactive=include_inactive, limit=limit, offset=offset, department_id=department_id)


@router.get('/{id}', response_model=PositionResponse)
def position(id: Annotated[int, Path(gt=0)], session: DBSession):
    return get_or_404(session, Position, id)


@router.patch('/{id}', response_model=PositionResponse)
def patch_position(id: Annotated[int, Path(gt=0)], payload: PositionUpdate, session: DBSession):
    item = session.scalar(select(Position).where(Position.id == id).with_for_update(of=Position))
    if item is None:
        raise HTTPException(404, 'Puesto no encontrado')
    values = payload.model_dump(exclude_unset=True)

    destinations_data = values.pop('destinations', None)
    if 'department_id' in values and values['department_id'] != item.department_id:
        validate_department(session, values['department_id'])

    escalation_mode = values.get('escalation_mode', item.escalation_mode)
    general_time = values.get('general_escalation_time_minutes', item.general_escalation_time_minutes)

    for field, val in values.items():
        setattr(item, field, val)

    validate_and_apply_destinations(session, item, escalation_mode, general_time, destinations_data)

    item = save_item(session, item)
    session.refresh(item)
    return item
