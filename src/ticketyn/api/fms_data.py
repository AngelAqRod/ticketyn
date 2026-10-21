"""Validación y consultas FMS; Sector del circuito se asigna transaccionalmente."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload
from ticketyn.api.crud import save_item
from ticketyn.api.circuit_sector import locked_circuit, resolve_sector, resolve_node
from ticketyn.api.ticket_numbers import format_reference
from ticketyn.models import Circuit, Responsible
from ticketyn.models.fms import Activation, ActivationNumberConfig, DeactivationReason
from ticketyn.notifications.fields import ACTIVATION_EVENT
from ticketyn.notifications.requests import request_notification


def locked_activation_config(session: Session):
    session.execute(insert(ActivationNumberConfig).values(id=1).on_conflict_do_nothing(index_elements=['id']))
    return session.scalars(select(ActivationNumberConfig).where(ActivationNumberConfig.id == 1).with_for_update().execution_options(populate_existing=True)).one()


def validate_active(session: Session, model, id: int):
    row = session.scalar(select(model).where(model.id == id).with_for_update(read=True, of=model))
    if row is None:
        raise HTTPException(404, 'El recurso relacionado no existe')
    if model is Responsible:
        from ticketyn.api.responsible_selection import selectable
        selectable(row)
    if not row.active:
        raise HTTPException(422, 'El recurso relacionado está inactivo')
    return row


def create_operation(session: Session, model, values: dict):
    values = dict(values)
    try:
        # Historial también permitido en circuitos administrativamente inactivos.
        circuit = locked_circuit(session, values['circuit_id'])
        values['node_id'] = resolve_node(session, circuit, values.get('node_id'))
        values['sector_id'] = resolve_sector(session, circuit, values.get('sector_id'))
        customer_id = values.pop('customer_id', None) if model is Activation else None
        if customer_id is not None and circuit.customer_id != customer_id:
            raise HTTPException(422, 'El circuito debe pertenecer al cliente seleccionado')
        validate_active(session, Responsible, values['responsible_id'])
        if values.get('reason_id') is not None:
            validate_active(session, DeactivationReason, values['reason_id'])
        if model is Activation:
            if circuit.service_type_id is not None:
                from ticketyn.models import ServiceType
                service = session.scalar(select(ServiceType).where(ServiceType.id == circuit.service_type_id).with_for_update(read=True, of=ServiceType).execution_options(populate_existing=True))
            else:
                service = None
            from ticketyn.models import CpeModel
            if circuit.cpe_model_id is not None:
                cpe = session.scalar(select(CpeModel).where(CpeModel.id == circuit.cpe_model_id)
                    .with_for_update(read=True, of=CpeModel).execution_options(populate_existing=True))
            else:
                cpe = None
            values.update(cpe_activation=cpe.name if cpe else None, service_type_name=service.name if service else None, initial_capacity=circuit.initial_capacity, initial_capacity_unit=circuit.initial_capacity_unit)
            config = locked_activation_config(session)
            if config.next_number > 2147483647:
                raise HTTPException(409, 'Se agotó el contador de activaciones')
            reference = format_reference(config.prefix, config.separator, config.next_number, config.padding)
            if session.scalar(select(Activation.id).where(Activation.reference == reference).limit(1)):
                raise HTTPException(409, 'La configuración produciría una referencia de activación existente')
            values = {**values, 'activation_number': config.next_number, 'reference': reference}
            # BigInteger permits storing the exhausted sentinel safely.
            config.next_number += 1
        operation = model(**values)
        if model is Activation:
            session.add(operation)
            try:
                # Obtain the ID without committing: the activation, numbering,
                # circuit assignments and automatic intent must succeed together.
                session.flush()
                request_notification(session, ACTIVATION_EVENT, operation.id, automatic=True)
            except IntegrityError:
                # Match save_item's existing handling of FMS integrity errors,
                # including those now detected by the pre-commit flush.
                raise HTTPException(409, 'Los datos incumplen una restricción de integridad') from None
            except SQLAlchemyError:
                raise HTTPException(503, 'No se pudo registrar la activación y su solicitud de notificación.') from None
        return save_item(session, operation)
    except Exception:
        session.rollback()
        raise


def operation_query(model, *, circuit_id=None, customer_id=None, from_at=None, to_at=None, operation_type=None):
    statement = select(model).join(Circuit, Circuit.id == model.circuit_id).options(joinedload(model.circuit).joinedload(Circuit.customer))
    if circuit_id is not None:
        statement = statement.where(model.circuit_id == circuit_id)
    if customer_id is not None:
        statement = statement.where(Circuit.customer_id == customer_id)
    if from_at is not None:
        statement = statement.where(model.effective_at >= from_at)
    if to_at is not None:
        statement = statement.where(model.effective_at < to_at)
    if operation_type is not None:
        statement = statement.where(model.operation_type == operation_type)
    return statement.order_by(model.effective_at.desc(), model.id.desc())


def validate_initial_capacity(values: dict):
    if (values.get('initial_capacity') is None) != (values.get('initial_capacity_unit') is None):
        raise HTTPException(422, 'La capacidad inicial y su unidad deben indicarse juntas')
