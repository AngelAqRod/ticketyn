"""Bounded topology writes and module-only audit; callers never contact devices."""
from contextlib import contextmanager

from fastapi import HTTPException
from sqlalchemy import Text, case, cast, func, literal, select, text, type_coerce
from sqlalchemy.dialects.postgresql import ARRAY, aggregate_order_by
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ticketyn.api.crud import UNIQUE_ERRORS
from ticketyn.models import Circuit, DistributionAudit, DistributionDevice, DistributionPort, Node, PortNomenclature, DistributionDeviceTemplate

TOPOLOGY_LOCK = 7808001
ASSIGNMENT_FIELDS = ('node_id', 'distribution_device_id', 'distribution_port_id')


def port_name_order(name):
    parts = func.regexp_matches(name, '[0-9]+|[^0-9]+', 'g').table_valued(
        'parts', with_ordinality='position').render_derived()
    token = type_coerce(parts.c.parts, ARRAY(Text))[1]
    digits = func.ltrim(token, '0')
    # Compare integer runs by significant length and digits, without integer overflow.
    # Three length digits cover the port name's existing 255-character limit.
    key = case(
        (token.op('~')('^[0-9]+$'), literal('0') + func.lpad(cast(func.length(digits), Text), 3, '0') + digits),
        else_=literal('1') + func.lower(token.collate('C.utf8')),
    )
    return select(func.array_agg(aggregate_order_by(key.collate('C'), parts.c.position))).select_from(parts).scalar_subquery()


@contextmanager
def distribution_write(session):
    """Serialize short topology writes across processes, then commit audit + data.

    Acquire BEFORE the circuit/device/port row locks. Reads and SMTP do not use
    this lock. No transaction remains open beyond the request's SQL operations.
    FK constraints independently protect relationships even outside the API.
    """
    try:
        session.execute(text("SET LOCAL lock_timeout = '3s'"))
        session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': TOPOLOGY_LOCK})
        yield
        session.commit()
    except IntegrityError as error:
        session.rollback()
        constraint = getattr(getattr(error.orig, 'diag', None), 'constraint_name', '') or ''
        if constraint == 'uq_port_nomenclatures_prefix_ci':
            detail = 'Ya existe una nomenclatura con ese prefijo, incluso si está inactiva.'
        elif constraint == 'uq_distribution_device_templates_name':
            detail = 'Ya existe una plantilla con un nombre equivalente.'
        elif constraint in {'uq_distribution_devices_name_normalized', 'uq_distribution_ports_name_normalized'}:
            detail = 'Ya existe un nombre equivalente dentro del mismo nodo o equipo.'
        else:
            detail = UNIQUE_ERRORS.get(constraint, 'Las relaciones cambiaron o el registro conserva dependencias. Revisa los datos.')
        raise HTTPException(409, detail) from None
    except SQLAlchemyError as error:
        session.rollback()
        if getattr(getattr(error, 'orig', None), 'sqlstate', None) in {'55P03', '40P01', '40001'}:
            raise HTTPException(409, 'Hay una modificación concurrente. Actualiza los datos y reintenta.') from None
        raise HTTPException(503, 'No se pudo guardar la distribución. Reintenta la operación.') from None
    except Exception:
        session.rollback()
        raise


def locked(session, model, id, *, shared=False):
    item = session.scalar(select(model).where(model.id == id).with_for_update(read=shared, of=model)
                          .execution_options(populate_existing=True))
    if item is None:
        raise HTTPException(404, 'No se encontró el recurso de distribución o su Nodo.')
    return item


def active_node(session, id):
    node = locked(session, Node, id, shared=True)
    if not node.active:
        raise HTTPException(422, 'El Nodo está inactivo.')
    return node


def active_device(session, id):
    device = locked(session, DistributionDevice, id, shared=True)
    active_node(session, device.node_id)
    if not device.active:
        raise HTTPException(422, 'El equipo de distribución está inactivo.')
    return device


def validate_circuit_distribution(session, values, item=None):
    def value(key):
        return values.get(key, getattr(item, key, None))
    node_id, device_id, port_id = (value(key) for key in ASSIGNMENT_FIELDS)
    if port_id is not None and device_id is None:
        raise HTTPException(422, 'No se puede asignar un puerto sin equipo de distribución.')
    if device_id is None:
        return
    if node_id is None:
        raise HTTPException(422, 'Selecciona el Nodo del equipo de distribución.')
    # Existing inactive references may remain while editing unrelated data.
    changed = (item is None or node_id != item.node_id or device_id != item.distribution_device_id
               or (port_id is not None and port_id != item.distribution_port_id))
    device = locked(session, DistributionDevice, device_id, shared=True)
    if device.node_id != node_id:
        raise HTTPException(422, 'El equipo de distribución no pertenece al Nodo del circuito.')
    if changed:
        active_node(session, node_id)
        if not device.active:
            raise HTTPException(422, 'El equipo de distribución está inactivo.')
    if port_id is not None:
        port = locked(session, DistributionPort, port_id, shared=True)
        if port.distribution_device_id != device_id:
            raise HTTPException(422, 'El puerto no pertenece al equipo de distribución seleccionado.')
        if changed and not port.active:
            raise HTTPException(422, 'El puerto de distribución está inactivo.')


def snapshot(item):
    if isinstance(item, DistributionDeviceTemplate):
        return {**{key: getattr(item, key) for key in ('name', 'manufacturer', 'description', 'active')},
                'groups': [dict(nomenclature_id=g.nomenclature_id, **g.definition) for g in item.groups]}
    if isinstance(item, PortNomenclature):
        fields = ('name', 'prefix', 'formats', 'active')
    elif isinstance(item, DistributionDevice):
        fields = ('node_id', 'name', 'description', 'active')
    elif isinstance(item, DistributionPort):
        fields = ('distribution_device_id', 'name', 'description', 'active', 'nomenclature_id', 'numbering_format', 'number_components')
    elif isinstance(item, Circuit):
        fields = ASSIGNMENT_FIELDS
    else:
        raise ValueError('Recurso ajeno a la bitácora de distribución')
    return {key: getattr(item, key) for key in fields}


def record(session, actor_id, item, action, before=None, *, deleted=False, flush=True):
    resource_type = 'TEMPLATE' if isinstance(item, DistributionDeviceTemplate) else 'NOMENCL' if isinstance(item, PortNomenclature) else 'DEVICE' if isinstance(item, DistributionDevice) else 'PORT' if isinstance(item, DistributionPort) else 'CIRCUIT'
    after = None if deleted else snapshot(item)
    if before == after:
        return
    session.add(DistributionAudit(actor_id=actor_id, resource_type=resource_type,
                                 resource_id=item.id, action=action, before=before, after=after))
    if flush: session.flush()


def has_circuits(session, item):
    if isinstance(item, DistributionPort):
        condition = Circuit.distribution_port_id == item.id
    else:
        # Check both paths independently, including inactive circuits.
        ports = select(DistributionPort.id).where(DistributionPort.distribution_device_id == item.id)
        condition = (Circuit.distribution_device_id == item.id) | Circuit.distribution_port_id.in_(ports)
    return session.scalar(select(Circuit.id).where(condition).limit(1)) is not None


def ensure_unassigned(session, item):
    if has_circuits(session, item):
        raise HTTPException(409, 'El recurso tiene circuitos asociados, incluidos los inactivos.')
