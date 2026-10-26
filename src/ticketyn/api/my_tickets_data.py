from datetime import datetime, timezone
from typing import Literal
from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ticketyn.api.recommendation_data import get_ticket_stage
from ticketyn.models import (
    Circuit,
    Customer,
    Department,
    IncidentType,
    InternalEscalation,
    InternalTicket,
    InternalTicketUpdate,
    Node,
    Position,
    Responsible,
    Sector,
    Ticket,
    TicketEscalation,
    TicketUpdate,
)
from ticketyn.models.ack import InternalTicketEscalationAck, TicketEscalationAck
from ticketyn.models.position import PositionEscalationDestination
from ticketyn.schemas.my_tickets import (
    MyTicketItem,
    MyTicketsListResponse,
    MyTicketsSummaryResponse,
)


def _check_permissions(actor) -> tuple[bool, bool]:
    is_admin = actor.role in ('SUPERADMIN', 'ADMIN')
    can_customer = is_admin or 'tickets.view' in actor.permissions
    can_internal = is_admin or 'internal_tickets.view' in actor.permissions
    return can_customer, can_internal


def _customer_row_to_item(
    row,
    escalation: TicketEscalation | None = None,
    recommendation: dict | None = None,
) -> MyTicketItem:
    if isinstance(row, Ticket):
        ticket = row
        customer = getattr(ticket, 'customer', None)
        circuit = getattr(ticket, 'circuit', None)
        sector = getattr(ticket, 'sector', None)
        department = getattr(ticket, 'department', None)
        incident_type = getattr(ticket, 'incident_type', None)
    elif hasattr(row, '__getitem__'):
        if len(row) > 0 and isinstance(row[0], TicketEscalation):
            escalation = row[0]
            ticket = row[1]
            customer = row[2] if len(row) > 2 else None
            circuit = row[3] if len(row) > 3 else None
            sector = row[4] if len(row) > 4 else None
            department = row[5] if len(row) > 5 else None
            incident_type = row[6] if len(row) > 6 else None
        else:
            ticket = row[0]
            customer = row[1] if len(row) > 1 else None
            circuit = row[2] if len(row) > 2 else None
            sector = row[3] if len(row) > 3 else None
            department = row[4] if len(row) > 4 else None
            incident_type = row[5] if len(row) > 5 else None
    else:
        ticket = row
        customer = getattr(ticket, 'customer', None)
        circuit = getattr(ticket, 'circuit', None)
        sector = getattr(ticket, 'sector', None)
        department = getattr(ticket, 'department', None)
        incident_type = getattr(ticket, 'incident_type', None)

    item = MyTicketItem(
        id=ticket.id,
        ticket_type='CUSTOMER',
        reference=ticket.reference,
        title=ticket.title,
        description=ticket.description,
        status=ticket.status,
        created_at=ticket.created_at,
        start_at=ticket.start_at,
        end_at=ticket.end_at,
        responsible_id=ticket.responsible_id,
        responsible_name=ticket.responsible.name if ticket.responsible else None,
        sector_name=sector.name if sector else (circuit.sector.name if circuit and circuit.sector else None),
        node_name=ticket.node.name if ticket.node else (circuit.node.name if circuit and circuit.node else None),
        department_name=department.name if department else None,
        incident_type_name=incident_type.name if incident_type else None,
        customer_name=customer.name if customer else None,
        customer_code=customer.customer_code if customer else None,
        circuit_code=circuit.circuit_code if circuit else None,
        provider_name=None,
    )

    if escalation:
        item.escalation_id = escalation.id
        item.escalation_status = escalation.status
        item.escalation_reason = escalation.reason.name if escalation.reason else None
        item.escalation_started_at = escalation.started_at
        item.escalation_finished_at = escalation.finished_at
        item.escalation_description = escalation.description
        item.escalation_requester_name = escalation.requester.name if escalation.requester else None
        item.escalation_recipient_name = escalation.recipient.name if escalation.recipient else None
        item.escalation_position_name = escalation.position.name if escalation.position else None

    if recommendation:
        item.has_recommendation = True
        item.recommendation_stage = recommendation.get('stage_name')
        item.recommendation_elapsed_minutes = recommendation.get('elapsed_minutes')
        item.recommendation_threshold_minutes = recommendation.get('threshold_minutes')
        item.recommendation_overdue_minutes = recommendation.get('overdue_minutes')
        item.recommendation_target_position_name = recommendation.get('target_position_name')
        item.recommendation_reference_position_name = recommendation.get('reference_position_name')

    return item


def _internal_row_to_item(
    row,
    escalation: InternalEscalation | None = None,
    recommendation: dict | None = None,
) -> MyTicketItem:
    if isinstance(row, InternalTicket):
        internal_ticket = row
    elif hasattr(row, '__getitem__'):
        if len(row) > 0 and isinstance(row[0], InternalEscalation):
            escalation = row[0]
            internal_ticket = row[1]
        else:
            internal_ticket = row[0]
    else:
        internal_ticket = row

    item = MyTicketItem(
        id=internal_ticket.id,
        ticket_type='INTERNAL',
        reference=internal_ticket.reference,
        title=internal_ticket.title,
        description=internal_ticket.description,
        status=internal_ticket.status,
        created_at=internal_ticket.created_at,
        start_at=internal_ticket.start_at,
        end_at=internal_ticket.end_at,
        responsible_id=internal_ticket.responsible_id,
        responsible_name=internal_ticket.responsible.name if internal_ticket.responsible else None,
        sector_name=internal_ticket.sector.name if internal_ticket.sector else None,
        node_name=internal_ticket.node.name if internal_ticket.node else None,
        department_name=internal_ticket.department.name if internal_ticket.department else None,
        incident_type_name=internal_ticket.incident_type.name if internal_ticket.incident_type else None,
        customer_name=None,
        customer_code=None,
        circuit_code=None,
        provider_name=internal_ticket.provider.name if internal_ticket.provider else None,
    )

    if escalation:
        item.escalation_id = escalation.id
        item.escalation_status = escalation.status
        item.escalation_reason = escalation.reason.name if escalation.reason else None
        item.escalation_started_at = escalation.started_at
        item.escalation_finished_at = escalation.finished_at
        item.escalation_description = escalation.description
        item.escalation_requester_name = escalation.requester.name if escalation.requester else None
        item.escalation_recipient_name = escalation.recipient.name if escalation.recipient else None
        item.escalation_position_name = escalation.position.name if escalation.position else None

    if recommendation:
        item.has_recommendation = True
        item.recommendation_stage = recommendation.get('stage_name')
        item.recommendation_elapsed_minutes = recommendation.get('elapsed_minutes')
        item.recommendation_threshold_minutes = recommendation.get('threshold_minutes')
        item.recommendation_overdue_minutes = recommendation.get('overdue_minutes')
        item.recommendation_target_position_name = recommendation.get('target_position_name')
        item.recommendation_reference_position_name = recommendation.get('reference_position_name')

    return item


# --- 1. ASIGNADOS A MÍ ---
def get_assigned_tickets(
    session: Session,
    actor,
    scope: Literal['ALL', 'CUSTOMER', 'INTERNAL'] = 'ALL',
    status: Literal['ALL', 'OPEN', 'CLOSED'] = 'OPEN',
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> MyTicketsListResponse:
    can_cust, can_int = _check_permissions(actor)
    include_cust = can_cust and scope in ('ALL', 'CUSTOMER')
    include_int = can_int and scope in ('ALL', 'INTERNAL')

    if not include_cust and not include_int:
        if (scope == 'CUSTOMER' and not can_cust) or (scope == 'INTERNAL' and not can_int):
            raise HTTPException(403, 'No autorizado para consultar este tipo de tickets')
        return MyTicketsListResponse(items=[], total=0, limit=limit, offset=offset)

    items: list[MyTicketItem] = []

    if include_cust:
        stmt = (
            select(Ticket, Customer, Circuit, Sector, Department, IncidentType)
            .join(Customer, Ticket.customer_id == Customer.id)
            .join(Circuit, Ticket.circuit_id == Circuit.id)
            .join(Sector, Ticket.sector_id == Sector.id)
            .join(Department, Ticket.department_id == Department.id)
            .join(IncidentType, Ticket.incident_type_id == IncidentType.id)
            .outerjoin(Node, Ticket.node_id == Node.id)
            .outerjoin(Responsible, Ticket.responsible_id == Responsible.id)
            .where(Ticket.responsible_id == actor.id)
        )
        if status in ('OPEN', 'CLOSED'):
            stmt = stmt.where(Ticket.status == status)
        if search and search.strip():
            pat = f'%{search.strip()}%'
            stmt = stmt.where(
                or_(
                    Ticket.reference.ilike(pat),
                    Ticket.title.ilike(pat),
                    Ticket.description.ilike(pat),
                    Customer.name.ilike(pat),
                    Customer.customer_code.ilike(pat),
                    Circuit.circuit_code.ilike(pat),
                )
            )
        cust_rows = session.execute(stmt).all()
        for r in cust_rows:
            items.append(_customer_row_to_item(r))

    if include_int:
        stmt_int = select(InternalTicket).where(InternalTicket.responsible_id == actor.id)
        if status in ('OPEN', 'CLOSED'):
            stmt_int = stmt_int.where(InternalTicket.status == status)
        if search and search.strip():
            pat = f'%{search.strip()}%'
            stmt_int = stmt_int.where(
                or_(
                    InternalTicket.reference.ilike(pat),
                    InternalTicket.title.ilike(pat),
                    InternalTicket.description.ilike(pat),
                )
            )
        int_rows = session.scalars(stmt_int).all()
        for it in int_rows:
            items.append(_internal_row_to_item(it))

    # Deterministic sorting: Open tickets first, then created_at desc, then id desc
    items.sort(key=lambda x: (0 if x.status == 'OPEN' else 1, -(x.created_at.timestamp() if x.created_at else 0), -x.id))
    total = len(items)
    paginated = items[offset : offset + limit]

    # Quick check for recommendations on open tickets in current page
    for itm in paginated:
        if itm.status == 'OPEN':
            from ticketyn.api.recommendation_data import calculate_ticket_recommendations
            if itm.ticket_type == 'CUSTOMER':
                tk = session.get(Ticket, itm.id)
                rec = calculate_ticket_recommendations(session, tk, TicketEscalation, TicketEscalationAck, actor)
            else:
                tk = session.get(InternalTicket, itm.id)
                rec = calculate_ticket_recommendations(session, tk, InternalEscalation, InternalTicketEscalationAck, actor)
            if rec.recommendations:
                itm.has_recommendation = True
                itm.recommendations_count = len(rec.recommendations)

    return MyTicketsListResponse(items=paginated, total=total, limit=limit, offset=offset)


# --- 2. HE PARTICIPADO ---
def get_participated_tickets(
    session: Session,
    actor,
    scope: Literal['ALL', 'CUSTOMER', 'INTERNAL'] = 'ALL',
    status: Literal['ALL', 'OPEN', 'CLOSED'] = 'OPEN',
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> MyTicketsListResponse:
    can_cust, can_int = _check_permissions(actor)
    include_cust = can_cust and scope in ('ALL', 'CUSTOMER')
    include_int = can_int and scope in ('ALL', 'INTERNAL')

    if not include_cust and not include_int:
        if (scope == 'CUSTOMER' and not can_cust) or (scope == 'INTERNAL' and not can_int):
            raise HTTPException(403, 'No autorizado para consultar este tipo de tickets')
        return MyTicketsListResponse(items=[], total=0, limit=limit, offset=offset)

    items: list[MyTicketItem] = []

    if include_cust:
        has_update = select(1).where(TicketUpdate.ticket_id == Ticket.id, TicketUpdate.responsible_id == actor.id)
        has_esc = select(1).where(
            TicketEscalation.ticket_id == Ticket.id,
            or_(TicketEscalation.requester_id == actor.id, TicketEscalation.recipient_id == actor.id),
        )
        stmt = (
            select(Ticket, Customer, Circuit, Sector, Department, IncidentType)
            .join(Customer, Ticket.customer_id == Customer.id)
            .join(Circuit, Ticket.circuit_id == Circuit.id)
            .join(Sector, Ticket.sector_id == Sector.id)
            .join(Department, Ticket.department_id == Department.id)
            .join(IncidentType, Ticket.incident_type_id == IncidentType.id)
            .outerjoin(Node, Ticket.node_id == Node.id)
            .outerjoin(Responsible, Ticket.responsible_id == Responsible.id)
            .where(or_(has_update.exists(), has_esc.exists()))
        )
        if status in ('OPEN', 'CLOSED'):
            stmt = stmt.where(Ticket.status == status)
        if search and search.strip():
            pat = f'%{search.strip()}%'
            stmt = stmt.where(
                or_(
                    Ticket.reference.ilike(pat),
                    Ticket.title.ilike(pat),
                    Ticket.description.ilike(pat),
                    Customer.name.ilike(pat),
                    Customer.customer_code.ilike(pat),
                    Circuit.circuit_code.ilike(pat),
                )
            )
        cust_rows = session.execute(stmt).all()
        for r in cust_rows:
            items.append(_customer_row_to_item(r))

    if include_int:
        has_int_update = select(1).where(
            InternalTicketUpdate.ticket_id == InternalTicket.id, InternalTicketUpdate.responsible_id == actor.id
        )
        has_int_esc = select(1).where(
            InternalEscalation.ticket_id == InternalTicket.id,
            or_(InternalEscalation.requester_id == actor.id, InternalEscalation.recipient_id == actor.id),
        )
        stmt_int = select(InternalTicket).where(or_(has_int_update.exists(), has_int_esc.exists()))
        if status in ('OPEN', 'CLOSED'):
            stmt_int = stmt_int.where(InternalTicket.status == status)
        if search and search.strip():
            pat = f'%{search.strip()}%'
            stmt_int = stmt_int.where(
                or_(
                    InternalTicket.reference.ilike(pat),
                    InternalTicket.title.ilike(pat),
                    InternalTicket.description.ilike(pat),
                )
            )
        int_rows = session.scalars(stmt_int).all()
        for it in int_rows:
            items.append(_internal_row_to_item(it))

    # Sort open first, then created_at desc
    items.sort(key=lambda x: (0 if x.status == 'OPEN' else 1, -(x.created_at.timestamp() if x.created_at else 0), -x.id))
    total = len(items)
    paginated = items[offset : offset + limit]
    return MyTicketsListResponse(items=paginated, total=total, limit=limit, offset=offset)


# --- 3. MIS ESCALAMIENTOS ---
def get_my_escalations(
    session: Session,
    actor,
    scope: Literal['ALL', 'CUSTOMER', 'INTERNAL'] = 'ALL',
    escalation_status: Literal['ALL', 'ACTIVE', 'FINISHED'] = 'ACTIVE',
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> MyTicketsListResponse:
    user = session.get(Responsible, actor.id)
    if not user:
        return MyTicketsListResponse(items=[], total=0, limit=limit, offset=offset)

    can_cust, can_int = _check_permissions(actor)
    include_cust = can_cust and scope in ('ALL', 'CUSTOMER')
    include_int = can_int and scope in ('ALL', 'INTERNAL')

    if not include_cust and not include_int:
        if (scope == 'CUSTOMER' and not can_cust) or (scope == 'INTERNAL' and not can_int):
            raise HTTPException(403, 'No autorizado para consultar este tipo de tickets')
        return MyTicketsListResponse(items=[], total=0, limit=limit, offset=offset)

    items: list[MyTicketItem] = []

    if include_cust:
        stmt = (
            select(TicketEscalation, Ticket, Customer, Circuit, Sector, Department, IncidentType)
            .join(Ticket, TicketEscalation.ticket_id == Ticket.id)
            .join(Customer, Ticket.customer_id == Customer.id)
            .join(Circuit, Ticket.circuit_id == Circuit.id)
            .join(Sector, Ticket.sector_id == Sector.id)
            .join(Department, Ticket.department_id == Department.id)
            .join(IncidentType, Ticket.incident_type_id == IncidentType.id)
            .outerjoin(Node, Ticket.node_id == Node.id)
            .outerjoin(Responsible, Ticket.responsible_id == Responsible.id)
            .where(TicketEscalation.recipient_id == actor.id)
        )
        if escalation_status in ('ACTIVE', 'FINISHED'):
            stmt = stmt.where(TicketEscalation.status == escalation_status)
        if search and search.strip():
            pat = f'%{search.strip()}%'
            stmt = stmt.where(
                or_(
                    Ticket.reference.ilike(pat),
                    Ticket.title.ilike(pat),
                    Ticket.description.ilike(pat),
                    Customer.name.ilike(pat),
                    Customer.customer_code.ilike(pat),
                    Circuit.circuit_code.ilike(pat),
                )
            )
        # Order active first, then newest started_at
        stmt = stmt.order_by(
            TicketEscalation.status.asc(),  # 'ACTIVE' < 'FINISHED'
            TicketEscalation.started_at.desc(),
            TicketEscalation.id.desc(),
        )
        rows = session.execute(stmt).all()
        for r in rows:
            esc = r[0]
            items.append(_customer_row_to_item(r, escalation=esc))

    if include_int:
        stmt_int = (
            select(InternalEscalation, InternalTicket)
            .join(InternalTicket, InternalEscalation.ticket_id == InternalTicket.id)
            .where(InternalEscalation.recipient_id == actor.id)
        )
        if escalation_status in ('ACTIVE', 'FINISHED'):
            stmt_int = stmt_int.where(InternalEscalation.status == escalation_status)
        if search and search.strip():
            pat = f'%{search.strip()}%'
            stmt_int = stmt_int.where(
                or_(
                    InternalTicket.reference.ilike(pat),
                    InternalTicket.title.ilike(pat),
                    InternalTicket.description.ilike(pat),
                )
            )
        stmt_int = stmt_int.order_by(
            InternalEscalation.status.asc(),
            InternalEscalation.started_at.desc(),
            InternalEscalation.id.desc(),
        )
        rows_int = session.execute(stmt_int).all()
        for r in rows_int:
            esc = r[0]
            items.append(_internal_row_to_item(r, escalation=esc))

    # Sort active first, then newest started_at
    items.sort(
        key=lambda x: (
            0 if x.escalation_status == 'ACTIVE' else 1,
            -(x.escalation_started_at.timestamp() if x.escalation_started_at else 0),
            -(x.escalation_id or 0),
        )
    )
    total = len(items)
    paginated = items[offset : offset + limit]
    return MyTicketsListResponse(items=paginated, total=total, limit=limit, offset=offset)


# --- 4. POR VERIFICAR ---
def get_to_verify_tickets(
    session: Session,
    actor,
    scope: Literal['ALL', 'CUSTOMER', 'INTERNAL'] = 'ALL',
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> MyTicketsListResponse:
    user = session.get(Responsible, actor.id)
    if not user or not user.position_id:
        return MyTicketsListResponse(items=[], total=0, limit=limit, offset=offset)

    can_cust, can_int = _check_permissions(actor)
    include_cust = can_cust and scope in ('ALL', 'CUSTOMER')
    include_int = can_int and scope in ('ALL', 'INTERNAL')

    if not include_cust and not include_int:
        if (scope == 'CUSTOMER' and not can_cust) or (scope == 'INTERNAL' and not can_int):
            raise HTTPException(403, 'No autorizado para consultar este tipo de tickets')
        return MyTicketsListResponse(items=[], total=0, limit=limit, offset=offset)

    # 1. Find all active source positions that have destination = user.position_id
    dest_rows = session.execute(
        select(PositionEscalationDestination, Position)
        .join(Position, PositionEscalationDestination.position_id == Position.id)
        .where(
            PositionEscalationDestination.target_position_id == user.position_id,
            Position.active == True,
        )
    ).all()

    if not dest_rows:
        return MyTicketsListResponse(items=[], total=0, limit=limit, offset=offset)

    user_position = session.get(Position, user.position_id)
    user_position_name = user_position.name if user_position else ''

    # Threshold mapping by source position id
    threshold_by_source_pos: dict[int, int] = {}
    for dest, pos in dest_rows:
        if pos.escalation_mode == 'INDIVIDUAL':
            if dest.time_minutes and dest.time_minutes > 0:
                threshold_by_source_pos[pos.id] = dest.time_minutes
        elif pos.escalation_mode == 'GENERAL':
            if pos.general_escalation_time_minutes and pos.general_escalation_time_minutes > 0:
                threshold_by_source_pos[pos.id] = pos.general_escalation_time_minutes

    if not threshold_by_source_pos:
        return MyTicketsListResponse(items=[], total=0, limit=limit, offset=offset)

    now = datetime.now(timezone.utc)
    items: list[MyTicketItem] = []

    # 2. Evaluate Customer Tickets
    if include_cust:
        # Find active ACKs to exclude
        active_ack_ids = set(
            session.scalars(
                select(TicketEscalationAck.ticket_id).where(
                    TicketEscalationAck.active == True,
                    or_(TicketEscalationAck.expires_at == None, TicketEscalationAck.expires_at > now),
                )
            ).all()
        )

        stmt = (
            select(Ticket, Customer, Circuit, Sector, Department, IncidentType)
            .join(Customer, Ticket.customer_id == Customer.id)
            .join(Circuit, Ticket.circuit_id == Circuit.id)
            .join(Sector, Ticket.sector_id == Sector.id)
            .join(Department, Ticket.department_id == Department.id)
            .join(IncidentType, Ticket.incident_type_id == IncidentType.id)
            .outerjoin(Node, Ticket.node_id == Node.id)
            .outerjoin(Responsible, Ticket.responsible_id == Responsible.id)
            .where(Ticket.status == 'OPEN')
        )
        if active_ack_ids:
            stmt = stmt.where(Ticket.id.not_in(active_ack_ids))
        if search and search.strip():
            pat = f'%{search.strip()}%'
            stmt = stmt.where(
                or_(
                    Ticket.reference.ilike(pat),
                    Ticket.title.ilike(pat),
                    Ticket.description.ilike(pat),
                    Customer.name.ilike(pat),
                    Customer.customer_code.ilike(pat),
                    Circuit.circuit_code.ilike(pat),
                )
            )

        cust_open = session.execute(stmt).all()
        for row in cust_open:
            tk = row[0]
            stage_name, stage_started_at, ref_pos = get_ticket_stage(session, tk, TicketEscalation)
            if ref_pos and ref_pos.id in threshold_by_source_pos:
                raw_sec = (now - stage_started_at).total_seconds() - getattr(tk, 'closed_seconds', 0)
                elapsed_min = int(max(0.0, raw_sec) // 60)
                threshold = threshold_by_source_pos[ref_pos.id]
                if elapsed_min >= threshold:
                    rec_info = {
                        'stage_name': stage_name,
                        'elapsed_minutes': elapsed_min,
                        'threshold_minutes': threshold,
                        'overdue_minutes': max(0, elapsed_min - threshold),
                        'target_position_name': user_position_name,
                        'reference_position_name': ref_pos.name,
                    }
                    items.append(_customer_row_to_item(row, recommendation=rec_info))

    # 3. Evaluate Internal Tickets
    if include_int:
        active_int_ack_ids = set(
            session.scalars(
                select(InternalTicketEscalationAck.ticket_id).where(
                    InternalTicketEscalationAck.active == True,
                    or_(
                        InternalTicketEscalationAck.expires_at == None,
                        InternalTicketEscalationAck.expires_at > now,
                    ),
                )
            ).all()
        )

        stmt_int = select(InternalTicket).where(InternalTicket.status == 'OPEN')
        if active_int_ack_ids:
            stmt_int = stmt_int.where(InternalTicket.id.not_in(active_int_ack_ids))
        if search and search.strip():
            pat = f'%{search.strip()}%'
            stmt_int = stmt_int.where(
                or_(
                    InternalTicket.reference.ilike(pat),
                    InternalTicket.title.ilike(pat),
                    InternalTicket.description.ilike(pat),
                )
            )

        int_open = session.scalars(stmt_int).all()
        for it in int_open:
            stage_name, stage_started_at, ref_pos = get_ticket_stage(session, it, InternalEscalation)
            if ref_pos and ref_pos.id in threshold_by_source_pos:
                raw_sec = (now - stage_started_at).total_seconds() - getattr(it, 'closed_seconds', 0)
                elapsed_min = int(max(0.0, raw_sec) // 60)
                threshold = threshold_by_source_pos[ref_pos.id]
                if elapsed_min >= threshold:
                    rec_info = {
                        'stage_name': stage_name,
                        'elapsed_minutes': elapsed_min,
                        'threshold_minutes': threshold,
                        'overdue_minutes': max(0, elapsed_min - threshold),
                        'target_position_name': user_position_name,
                        'reference_position_name': ref_pos.name,
                    }
                    items.append(_internal_row_to_item(it, recommendation=rec_info))

    # Order by overdue minutes descending, then elapsed minutes descending
    items.sort(
        key=lambda x: (
            -(x.recommendation_overdue_minutes or 0),
            -(x.recommendation_elapsed_minutes or 0),
            -x.id,
        )
    )
    total = len(items)
    paginated = items[offset : offset + limit]
    return MyTicketsListResponse(items=paginated, total=total, limit=limit, offset=offset)


# --- 5. RESUMEN SUPERIOR ---
def get_my_tickets_summary(session: Session, actor) -> MyTicketsSummaryResponse:
    can_cust, can_int = _check_permissions(actor)
    user = session.get(Responsible, actor.id)

    # 1. Assigned open count
    assigned_count = 0
    if can_cust:
        assigned_count += session.scalar(
            select(func.count(Ticket.id)).where(Ticket.responsible_id == actor.id, Ticket.status == 'OPEN')
        ) or 0
    if can_int:
        assigned_count += session.scalar(
            select(func.count(InternalTicket.id)).where(
                InternalTicket.responsible_id == actor.id, InternalTicket.status == 'OPEN'
            )
        ) or 0

    # 2. Participated open count
    participated_count = 0
    if can_cust:
        has_update = select(1).where(TicketUpdate.ticket_id == Ticket.id, TicketUpdate.responsible_id == actor.id)
        has_esc = select(1).where(
            TicketEscalation.ticket_id == Ticket.id,
            or_(TicketEscalation.requester_id == actor.id, TicketEscalation.recipient_id == actor.id),
        )
        participated_count += session.scalar(
            select(func.count(Ticket.id)).where(Ticket.status == 'OPEN', or_(has_update.exists(), has_esc.exists()))
        ) or 0
    if can_int:
        has_int_update = select(1).where(
            InternalTicketUpdate.ticket_id == InternalTicket.id, InternalTicketUpdate.responsible_id == actor.id
        )
        has_int_esc = select(1).where(
            InternalEscalation.ticket_id == InternalTicket.id,
            or_(InternalEscalation.requester_id == actor.id, InternalEscalation.recipient_id == actor.id),
        )
        participated_count += session.scalar(
            select(func.count(InternalTicket.id)).where(
                InternalTicket.status == 'OPEN', or_(has_int_update.exists(), has_int_esc.exists())
            )
        ) or 0

    # 3. Escalations active count (assigned to user as recipient)
    escalations_count = 0
    if can_cust:
        escalations_count += session.scalar(
            select(func.count(TicketEscalation.id)).where(
                TicketEscalation.recipient_id == actor.id, TicketEscalation.status == 'ACTIVE'
            )
        ) or 0
    if can_int:
        escalations_count += session.scalar(
            select(func.count(InternalEscalation.id)).where(
                InternalEscalation.recipient_id == actor.id, InternalEscalation.status == 'ACTIVE'
            )
        ) or 0

    # 4. To verify count
    to_verify_count = 0
    if user and user.position_id:
        res = get_to_verify_tickets(session, actor, scope='ALL', limit=1000, offset=0)
        to_verify_count = res.total

    return MyTicketsSummaryResponse(
        assigned_count=assigned_count,
        participated_count=participated_count,
        escalations_count=escalations_count,
        to_verify_count=to_verify_count,
    )
