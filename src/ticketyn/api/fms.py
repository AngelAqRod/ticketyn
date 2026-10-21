from ticketyn.api.activation_reports import ActivationReportOptions, activation_report_response
from ticketyn.api.fms_exports import stream_export
from ticketyn.schemas.fms_export import OperationExportFilters, CapacityExportFilters, LifecycleExportFilters
from typing import Annotated, Literal
from pydantic import AwareDatetime
from fastapi import Request, APIRouter, HTTPException, Path, Query
from sqlalchemy import func, select
from ticketyn.api.crud import DBSession, get_or_404, list_items, save_item, update_item
from ticketyn.api.fms_data import create_operation, locked_activation_config, operation_query, validate_active
from ticketyn.api.ticket_numbers import format_reference
from ticketyn.models import Circuit, Responsible
from ticketyn.models.fms import Activation, ActivationIntervention, CapacityChange, CircuitLifecycleOperation, DeactivationReason
from ticketyn.schemas.fms import ActivationCreate, ActivationResponse, CapacityChangeCreate, CapacityChangeResponse, LifecycleCreate, LifecycleResponse, InterventionCreate, InterventionResponse, CircuitOperationalDetail
from ticketyn.schemas.escalation import ReasonCreate, ReasonUpdate, ReasonResponse
from ticketyn.schemas.ticket_number_config import TicketNumberConfigResponse, TicketNumberConfigUpdate

router = APIRouter(prefix='/api', tags=['fms'])
Id = Annotated[int, Path(gt=0)]
FilterId = Annotated[int | None, Query(gt=0)]
Limit = Annotated[int, Query(ge=1, le=200)]
Offset = Annotated[int, Query(ge=0)]


def list_operations(session, model, circuit_id, customer_id, from_at, to_at, operation_type, limit, offset):
    if from_at and to_at and from_at >= to_at:
        raise HTTPException(422, 'El inicio del período debe ser anterior al final')
    return list(session.scalars(operation_query(model, circuit_id=circuit_id, customer_id=customer_id, from_at=from_at, to_at=to_at, operation_type=operation_type).limit(limit).offset(offset)))


@router.post('/activations', response_model=ActivationResponse, status_code=201)
def create_activation(payload: ActivationCreate, session: DBSession):
    return create_operation(session, Activation, payload.model_dump())


@router.get('/activations', response_model=list[ActivationResponse])
def activations(session: DBSession, circuit_id: FilterId = None, customer_id: FilterId = None, from_at: AwareDatetime | None = None, to_at: AwareDatetime | None = None, limit: Limit = 50, offset: Offset = 0):
    return list_operations(session, Activation, circuit_id, customer_id, from_at, to_at, None, limit, offset)


@router.get('/activations/export/{format}')
def export_activations(session: DBSession, format: Literal['pdf', 'xlsx'], filters: Annotated[OperationExportFilters, Query()]):
    return stream_export(session, Activation, 'activations', format, filters)


@router.get('/capacity-changes/export/{format}')
def export_capacity(session: DBSession, format: Literal['pdf', 'xlsx'], filters: Annotated[CapacityExportFilters, Query()]):
    return stream_export(session, CapacityChange, 'capacity-changes', format, filters)


@router.get('/circuit-lifecycle/export/{format}')
def export_lifecycle(session: DBSession, format: Literal['pdf', 'xlsx'], filters: Annotated[LifecycleExportFilters, Query()]):
    return stream_export(session, CircuitLifecycleOperation, 'circuit-lifecycle', format, filters)


@router.get('/activations/{id}', response_model=ActivationResponse)
def activation(id: Id, session: DBSession):
    return get_or_404(session, Activation, id)


@router.get('/activations/{id}/reports/pdf')
def activation_report(id: Id, session: DBSession, options: Annotated[ActivationReportOptions, Query()]):
    return activation_report_response(session, id, options)


@router.get('/activations/{id}/interventions', response_model=list[InterventionResponse])
def interventions(id: Id, session: DBSession, limit: Limit = 50, offset: Offset = 0):
    get_or_404(session, Activation, id)
    return list(session.scalars(select(ActivationIntervention).where(ActivationIntervention.activation_id == id).order_by(ActivationIntervention.occurred_at, ActivationIntervention.id).limit(limit).offset(offset)))


@router.post('/activations/{id}/interventions', response_model=InterventionResponse, status_code=201)
def create_intervention(id: Id, payload: InterventionCreate, session: DBSession):
    try:
        if session.scalar(select(Activation.id).where(Activation.id == id).with_for_update(read=True)) is None:
            raise HTTPException(404, 'La activación indicada no existe')
        validate_active(session, Responsible, payload.responsible_id)
        return save_item(session, ActivationIntervention(activation_id=id, **payload.model_dump()))
    except Exception:
        session.rollback()
        raise


@router.post('/capacity-changes', response_model=CapacityChangeResponse, status_code=201)
def create_capacity_change(payload: CapacityChangeCreate, session: DBSession):
    return create_operation(session, CapacityChange, payload.model_dump())


@router.get('/capacity-changes', response_model=list[CapacityChangeResponse])
def capacity_changes(session: DBSession, circuit_id: FilterId = None, customer_id: FilterId = None, from_at: AwareDatetime | None = None, to_at: AwareDatetime | None = None, operation_type: Literal['INCREASE', 'DECREASE'] | None = None, limit: Limit = 50, offset: Offset = 0):
    return list_operations(session, CapacityChange, circuit_id, customer_id, from_at, to_at, operation_type, limit, offset)


@router.post('/circuit-lifecycle', response_model=LifecycleResponse, status_code=201)
def create_lifecycle(payload: LifecycleCreate, session: DBSession, request: Request):
    from ticketyn.security.roles import require
    require(request.state.principal, 'lifecycle.deactivate' if payload.operation_type == 'DEACTIVATE' else 'lifecycle.reactivate')
    return create_operation(session, CircuitLifecycleOperation, payload.model_dump())


@router.get('/circuit-lifecycle', response_model=list[LifecycleResponse])
def lifecycle(session: DBSession, circuit_id: FilterId = None, customer_id: FilterId = None, from_at: AwareDatetime | None = None, to_at: AwareDatetime | None = None, operation_type: Literal['DEACTIVATE', 'REACTIVATE'] | None = None, limit: Limit = 50, offset: Offset = 0):
    return list_operations(session, CircuitLifecycleOperation, circuit_id, customer_id, from_at, to_at, operation_type, limit, offset)


@router.get('/circuits/{id}/operational-detail', response_model=CircuitOperationalDetail)
def circuit_detail(id: Id, session: DBSession, request: Request):
    circuit = get_or_404(session, Circuit, id)
    last = session.scalar(select(CapacityChange).where(CapacityChange.circuit_id == id, CapacityChange.effective_at <= func.now()).order_by(CapacityChange.effective_at.desc(), CapacityChange.id.desc()).limit(1))
    first = session.scalar(select(Activation).where(Activation.circuit_id == id).order_by(Activation.effective_at, Activation.id).limit(1))
    return {'circuit': circuit, 'customer': circuit.customer, 'current_capacity': last.new_capacity if last else circuit.initial_capacity, 'current_capacity_unit': last.new_unit if last else circuit.initial_capacity_unit, 'initial_activation': first if 'activations.view' in request.state.principal.permissions else None}


@router.get('/settings/activation-number', response_model=TicketNumberConfigResponse)
def activation_config(session: DBSession):
    return save_item(session, locked_activation_config(session))


@router.patch('/settings/activation-number', response_model=TicketNumberConfigResponse)
def update_activation_config(payload: TicketNumberConfigUpdate, session: DBSession):
    config = locked_activation_config(session)
    values = payload.model_dump(exclude_unset=True)
    try:
        number = values.get('next_number', config.next_number)
        highest = session.scalar(select(func.max(Activation.activation_number)))
        reference = format_reference(values.get('prefix', config.prefix), values.get('separator', config.separator), number, values.get('padding', config.padding))
        if (highest is not None and number <= highest) or session.scalar(select(Activation.id).where(Activation.reference == reference).limit(1)):
            raise HTTPException(409, 'La configuración produciría un número o referencia ya asignado')
        return update_item(session, config, values)
    except Exception:
        session.rollback()
        raise


@router.get('/deactivation-reasons', response_model=list[ReasonResponse])
def reasons(session: DBSession, search: str | None = None, include_inactive: bool = False, limit: Limit = 50, offset: Offset = 0):
    return list_items(session, DeactivationReason, search=search, search_fields=('name',), order_field='name', include_inactive=include_inactive, limit=limit, offset=offset)


@router.post('/deactivation-reasons', response_model=ReasonResponse, status_code=201)
def create_reason(payload: ReasonCreate, session: DBSession):
    return save_item(session, DeactivationReason(**payload.model_dump()))


@router.patch('/deactivation-reasons/{id}', response_model=ReasonResponse)
def edit_reason(id: Id, payload: ReasonUpdate, session: DBSession):
    return update_item(session, get_or_404(session, DeactivationReason, id), payload.model_dump(exclude_unset=True))
