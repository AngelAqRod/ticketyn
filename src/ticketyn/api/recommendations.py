from sqlalchemy import select
from sqlalchemy.orm import lazyload
from typing import Annotated
from fastapi import APIRouter, Path, Request, Response, HTTPException
from ticketyn.api.crud import DBSession, get_or_404
from ticketyn.models import Ticket, InternalTicket, TicketEscalation, InternalEscalation
from ticketyn.models.ack import TicketEscalationAck, InternalTicketEscalationAck
from ticketyn.schemas.recommendation import (
    AckCreate,
    AckResponse,
    AckRevoke,
    TicketRecommendationsResponse,
)
from ticketyn.api.recommendation_data import (
    calculate_ticket_recommendations,
    create_ticket_ack,
    revoke_ticket_ack,
    list_ticket_acks,
)

router = APIRouter(tags=['recommendations'])


def recommendation_ticket(session, model, id):
    ticket = session.scalar(select(model).where(model.id == id).options(lazyload('*')))
    if ticket is None:
        raise HTTPException(404, f'{model.__name__} con id {id} no encontrado')
    return ticket


# --- Client Tickets ---

@router.get('/api/tickets/{id}/recommendations', response_model=TicketRecommendationsResponse)
def get_recommendations(id: Annotated[int, Path(gt=0)], session: DBSession, request: Request):
    ticket = recommendation_ticket(session, Ticket, id)
    actor = getattr(request.state, 'principal', None)
    return calculate_ticket_recommendations(session, ticket, TicketEscalation, TicketEscalationAck, actor)


@router.post('/api/tickets/{id}/ack', response_model=AckResponse, status_code=201)
def post_ack(id: Annotated[int, Path(gt=0)], payload: AckCreate, session: DBSession, request: Request):
    ticket = get_or_404(session, Ticket, id)
    actor = getattr(request.state, 'principal', None)
    if actor is None:
        raise HTTPException(401, 'No autenticado')
    return create_ticket_ack(session, ticket, TicketEscalationAck, payload, actor, TicketEscalation)


@router.post('/api/tickets/{id}/ack/revoke', response_model=AckResponse)
def post_revoke_ack(id: Annotated[int, Path(gt=0)], session: DBSession, request: Request, payload: AckRevoke = AckRevoke()):
    ticket = get_or_404(session, Ticket, id)
    actor = getattr(request.state, 'principal', None)
    if actor is None:
        raise HTTPException(401, 'No autenticado')
    return revoke_ticket_ack(session, ticket, TicketEscalationAck, payload, actor, TicketEscalation)


@router.get('/api/tickets/{id}/ack', response_model=AckResponse | None)
def get_active_ack(id: Annotated[int, Path(gt=0)], session: DBSession, response: Response):
    ticket = recommendation_ticket(session, Ticket, id)
    rec = calculate_ticket_recommendations(session, ticket, TicketEscalation, TicketEscalationAck)
    if not rec.active_ack:
        response.status_code = 204
        return None
    return rec.active_ack


@router.get('/api/tickets/{id}/acks', response_model=list[AckResponse])
def get_ack_history(id: Annotated[int, Path(gt=0)], session: DBSession):
    ticket = get_or_404(session, Ticket, id)
    return list_ticket_acks(session, ticket, TicketEscalationAck)


# --- Internal Tickets ---

@router.get('/api/internal-tickets/{id}/recommendations', response_model=TicketRecommendationsResponse)
def get_internal_recommendations(id: Annotated[int, Path(gt=0)], session: DBSession, request: Request):
    ticket = recommendation_ticket(session, InternalTicket, id)
    actor = getattr(request.state, 'principal', None)
    return calculate_ticket_recommendations(session, ticket, InternalEscalation, InternalTicketEscalationAck, actor)


@router.post('/api/internal-tickets/{id}/ack', response_model=AckResponse, status_code=201)
def post_internal_ack(id: Annotated[int, Path(gt=0)], payload: AckCreate, session: DBSession, request: Request):
    ticket = get_or_404(session, InternalTicket, id)
    actor = getattr(request.state, 'principal', None)
    if actor is None:
        raise HTTPException(401, 'No autenticado')
    return create_ticket_ack(session, ticket, InternalTicketEscalationAck, payload, actor, InternalEscalation)


@router.post('/api/internal-tickets/{id}/ack/revoke', response_model=AckResponse)
def post_internal_revoke_ack(id: Annotated[int, Path(gt=0)], session: DBSession, request: Request, payload: AckRevoke = AckRevoke()):
    ticket = get_or_404(session, InternalTicket, id)
    actor = getattr(request.state, 'principal', None)
    if actor is None:
        raise HTTPException(401, 'No autenticado')
    return revoke_ticket_ack(session, ticket, InternalTicketEscalationAck, payload, actor, InternalEscalation)


@router.get('/api/internal-tickets/{id}/ack', response_model=AckResponse | None)
def get_internal_active_ack(id: Annotated[int, Path(gt=0)], session: DBSession, response: Response):
    ticket = recommendation_ticket(session, InternalTicket, id)
    rec = calculate_ticket_recommendations(session, ticket, InternalEscalation, InternalTicketEscalationAck)
    if not rec.active_ack:
        response.status_code = 204
        return None
    return rec.active_ack


@router.get('/api/internal-tickets/{id}/acks', response_model=list[AckResponse])
def get_internal_ack_history(id: Annotated[int, Path(gt=0)], session: DBSession):
    ticket = get_or_404(session, InternalTicket, id)
    return list_ticket_acks(session, ticket, InternalTicketEscalationAck)
