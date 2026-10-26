from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, lazyload, joinedload
from ticketyn.models import Ticket, InternalTicket, TicketEscalation, InternalEscalation, Position, Responsible
from ticketyn.models.position import PositionEscalationDestination
from ticketyn.models.ack import TicketEscalationAck, InternalTicketEscalationAck
from ticketyn.schemas.recommendation import (
    AckCreate,
    AckResponse,
    AckRevoke,
    RecommendationItem,
    TicketRecommendationsResponse,
)


def stage_position(session, id):
    # The recommendation graph is loaded only for the current stage, never recursively.
    return session.scalar(select(Position).where(Position.id == id).options(lazyload('*')))


def get_ticket_stage(session: Session, ticket, escalation_model):
    current_esc = session.scalar(
        select(escalation_model)
        .where(escalation_model.ticket_id == ticket.id, escalation_model.status == 'ACTIVE')
        .order_by(escalation_model.started_at.desc(), escalation_model.id.desc()).limit(1)
        .options(lazyload('*'))
    )

    if current_esc:
        pos = None
        if current_esc.position_id:
            pos = stage_position(session, current_esc.position_id)
        elif current_esc.recipient_id and (position_id := session.scalar(select(Responsible.position_id).where(Responsible.id == current_esc.recipient_id))):
            pos = stage_position(session, position_id)
        elif current_esc.recipient_position_name:
            pos = session.scalar(
                select(Position).options(lazyload('*')).where(
                    Position.name == current_esc.recipient_position_name,
                    Position.department_id == current_esc.department_id,
                )
            )

        pos_name = pos.name if pos else (current_esc.recipient_position_name or 'Sin puesto')
        stage_name = f'Escalamiento activo — {pos_name}'
        return stage_name, current_esc.started_at, pos

    # No active escalations: check last finished
    last_finished = session.scalar(
        select(escalation_model)
        .where(escalation_model.ticket_id == ticket.id, escalation_model.status == 'FINISHED')
        .order_by(escalation_model.finished_at.desc(), escalation_model.id.desc()).limit(1)
        .options(lazyload('*'))
    )

    ref_pos = None
    if ticket.initial_position_id:
        ref_pos = stage_position(session, ticket.initial_position_id)
    elif ticket.responsible_id and (position_id := session.scalar(select(Responsible.position_id).where(Responsible.id == ticket.responsible_id))):
        ref_pos = stage_position(session, position_id)

    pos_name = ref_pos.name if ref_pos else 'Sin puesto'
    if last_finished and last_finished.finished_at:
        stage_name = f'Puesto original ({pos_name})'
        return stage_name, last_finished.finished_at, ref_pos
    else:
        stage_name = f'Etapa inicial — Puesto original ({pos_name})'
        return stage_name, ticket.start_at, ref_pos


def check_ack_authorization(session: Session, ticket, actor, ref_position: Position | None) -> bool:
    if actor is None:
        return False
    if actor.role in ('SUPERADMIN', 'ADMIN'):
        return True

    # Check permission
    is_internal = isinstance(ticket, InternalTicket)
    perm = 'internal_tickets.escalate' if is_internal else 'tickets.escalate'
    if perm not in actor.permissions:
        return False

    user_pos_id = session.scalar(select(Responsible.position_id).where(Responsible.id == actor.id))
    if not user_pos_id:
        return False
    enabled_positions = set()
    if ref_position:
        enabled_positions.add(ref_position.id)
        enabled_positions.update(session.scalars(select(PositionEscalationDestination.target_position_id).where(
            PositionEscalationDestination.position_id == ref_position.id)))

    if ticket.initial_position_id:
        enabled_positions.add(ticket.initial_position_id)
    if ticket.responsible_id:
        enabled_positions.add(session.scalar(select(Responsible.position_id).where(Responsible.id == ticket.responsible_id)))

    return user_pos_id in enabled_positions


def calculate_ticket_recommendations(session: Session, ticket, escalation_model, ack_model, actor=None) -> TicketRecommendationsResponse:
    if ticket.status != 'OPEN':
        return TicketRecommendationsResponse(ticket_id=ticket.id, ticket_status=ticket.status,
            stage_name='Ticket cerrado', reference_position_id=None, reference_position_name=None,
            stage_started_at=None, elapsed_minutes=0, has_active_ack=False, can_acknowledge=False,
            recommendations=[])

    stage_name, stage_started_at, ref_pos = get_ticket_stage(session, ticket, escalation_model)

    now = datetime.now(timezone.utc)
    raw_seconds = (now - stage_started_at).total_seconds()
    if getattr(ticket, 'closed_seconds', 0) > 0:
        raw_seconds -= ticket.closed_seconds
    effective_seconds = max(0.0, raw_seconds)
    elapsed_minutes = int(effective_seconds // 60)

    # Check active ACK
    active_ack = session.scalar(
        select(ack_model).where(ack_model.ticket_id == ticket.id, ack_model.active == True).options(
            lazyload('*'), joinedload(ack_model.acknowledged_by).lazyload('*'),
            joinedload(ack_model.acknowledged_by_position).lazyload('*'), joinedload(ack_model.revoked_by).lazyload('*'))
    )

    expired_ack = bool(active_ack and active_ack.expires_at and active_ack.expires_at <= now)
    if expired_ack:
        active_ack.active = False
        active_ack.revoked_reason = 'Vencimiento automático de plazo'
        active_ack = None

    has_active_ack = active_ack is not None
    can_ack = check_ack_authorization(session, ticket, actor, ref_pos)

    recommendations: list[RecommendationItem] = []
    if not has_active_ack and ref_pos and ref_pos.active and (
        ref_pos.escalation_mode == 'INDIVIDUAL' or (ref_pos.general_escalation_time_minutes is not None
        and elapsed_minutes >= ref_pos.general_escalation_time_minutes)
    ):
        destinations = session.scalars(select(PositionEscalationDestination).where(
            PositionEscalationDestination.position_id == ref_pos.id).order_by(PositionEscalationDestination.order_index).options(
                lazyload('*'), joinedload(PositionEscalationDestination.target_position).options(
                    lazyload('*'), joinedload(Position.department)))).all()
        if ref_pos.escalation_mode == 'GENERAL':
            threshold = ref_pos.general_escalation_time_minutes
            if threshold is not None and elapsed_minutes >= threshold:
                for dest in destinations:
                    target = dest.target_position
                    if target and target.active:
                        recommendations.append(
                            RecommendationItem(
                                target_position_id=target.id,
                                target_position_name=target.name,
                                target_department_name=target.department.name if target.department else '',
                                threshold_minutes=threshold,
                                elapsed_minutes=elapsed_minutes,
                                overdue_minutes=max(0, elapsed_minutes - threshold),
                            )
                        )
        elif ref_pos.escalation_mode == 'INDIVIDUAL':
            for dest in destinations:
                target = dest.target_position
                threshold = dest.time_minutes
                if target and target.active and threshold is not None and elapsed_minutes >= threshold:
                    recommendations.append(
                        RecommendationItem(
                            target_position_id=target.id,
                            target_position_name=target.name,
                            target_department_name=target.department.name if target.department else '',
                            threshold_minutes=threshold,
                            elapsed_minutes=elapsed_minutes,
                            overdue_minutes=max(0, elapsed_minutes - threshold),
                        )
                    )

    active_ack_dto = AckResponse.model_validate(active_ack) if active_ack else None

    result = TicketRecommendationsResponse(
        ticket_id=ticket.id,
        ticket_status=ticket.status,
        stage_name=stage_name,
        reference_position_id=ref_pos.id if ref_pos else None,
        reference_position_name=ref_pos.name if ref_pos else None,
        stage_started_at=stage_started_at,
        elapsed_minutes=elapsed_minutes,
        has_active_ack=has_active_ack,
        active_ack=active_ack_dto,
        can_acknowledge=can_ack,
        recommendations=recommendations,
    )
    if expired_ack:
        session.commit()
    return result


def create_ticket_ack(session: Session, ticket, ack_model, payload: AckCreate, actor, escalation_model) -> AckResponse:
    _, _, ref_pos = get_ticket_stage(session, ticket, escalation_model)
    if not check_ack_authorization(session, ticket, actor, ref_pos):
        raise HTTPException(403, 'No autorizado: el puesto del usuario no está habilitado en el flujo de escalamiento del ticket')

    # Lock ticket to prevent race condition
    ticket_model = type(ticket)
    session.scalar(select(ticket_model.id).where(ticket_model.id == ticket.id).with_for_update())

    # Check existing active ACK
    existing_ack = session.scalar(
        select(ack_model).where(ack_model.ticket_id == ticket.id, ack_model.active == True).with_for_update(of=ack_model)
    )
    if existing_ack:
        now = datetime.now(timezone.utc)
        if existing_ack.expires_at and existing_ack.expires_at <= now:
            existing_ack.active = False
            existing_ack.revoked_reason = 'Vencimiento automático de plazo'
            session.flush()
        else:
            raise HTTPException(409, 'Ya existe un reconocimiento (ACK) vigente para este ticket')

    now = datetime.now(timezone.utc)
    expires_at = None
    if payload.duration_type == '1H':
        expires_at = now + timedelta(hours=1)
    elif payload.duration_type == '4H':
        expires_at = now + timedelta(hours=4)
    elif payload.duration_type == '8H':
        expires_at = now + timedelta(hours=8)
    elif payload.duration_type == 'INDEFINITE':
        expires_at = None

    user_resp = session.get(Responsible, actor.id)
    user_pos_id = user_resp.position_id if user_resp else None

    item = ack_model(
        ticket_id=ticket.id,
        acknowledged_by_id=actor.id,
        acknowledged_by_position_id=user_pos_id,
        acknowledged_at=now,
        duration_type=payload.duration_type,
        expires_at=expires_at,
        reason=payload.reason.strip(),
        active=True,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return AckResponse.model_validate(item)


def revoke_ticket_ack(session: Session, ticket, ack_model, payload: AckRevoke, actor, escalation_model) -> AckResponse:
    _, _, ref_pos = get_ticket_stage(session, ticket, escalation_model)
    active_ack = session.scalar(
        select(ack_model).where(ack_model.ticket_id == ticket.id, ack_model.active == True).with_for_update(of=ack_model)
    )
    if not active_ack:
        raise HTTPException(404, 'No existe un reconocimiento (ACK) vigente para este ticket')

    # Check permission to revoke
    can_revoke = False
    if actor.role in ('SUPERADMIN', 'ADMIN') or actor.id == active_ack.acknowledged_by_id:
        can_revoke = True
    elif check_ack_authorization(session, ticket, actor, ref_pos):
        can_revoke = True

    if not can_revoke:
        raise HTTPException(403, 'No autorizado para retirar este reconocimiento (ACK)')

    now = datetime.now(timezone.utc)
    active_ack.active = False
    active_ack.revoked_by_id = actor.id
    active_ack.revoked_at = now
    active_ack.revoked_reason = (payload.reason.strip() if payload.reason else 'Retiro manual')

    session.commit()
    session.refresh(active_ack)
    return AckResponse.model_validate(active_ack)


def list_ticket_acks(session: Session, ticket, ack_model) -> list[AckResponse]:
    acks = session.scalars(
        select(ack_model).where(ack_model.ticket_id == ticket.id).order_by(ack_model.acknowledged_at.desc(), ack_model.id.desc())
    ).all()
    return [AckResponse.model_validate(a) for a in acks]
